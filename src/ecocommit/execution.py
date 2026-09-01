from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Literal, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._canonical import sha256_hex
from .commitment import CommitmentStateStore
from .idempotency import IdempotencyBackend, IdempotencyLedger, request_fingerprint
from .razorpay import RazorpayTestPaymentAdapter
from .razorpay_checkout import (
    RazorpayCheckoutCallback,
    RazorpayCheckoutHandoff,
    RazorpayLifecycleEvidence,
    complete_test_lifecycle,
    has_bound_lifecycle_state,
)


MAX_PREPARED_OPERATION_BYTES = 256 * 1024


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON keys are forbidden")
        value[key] = item
    return value


class TestExecutionError(RuntimeError):
    """Safe failure classification for the API boundary.

    ``provider_call_status`` deliberately distinguishes a rejection known to
    happen before provider dispatch from a failure where reconciliation is
    required. Provider exception bodies never cross this boundary.
    """

    def __init__(
        self,
        code: str,
        *,
        provider_call_status: Literal["NOT_STARTED", "STARTED_OR_UNKNOWN"],
    ) -> None:
        super().__init__(code)
        self.code = code
        self.provider_call_status = provider_call_status


class _PendingExecution(RuntimeError):
    def __init__(self, result: "TestExecutionResult") -> None:
        super().__init__("TEST_MODE_COMPENSATION_PENDING")
        self.result = result


class PreparedRazorpayTestOperation(BaseModel):
    """Startup-trusted operation; HTTP callers supply only its opaque id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["D.RAZORPAY.OPERATION.1"] = "D.RAZORPAY.OPERATION.1"
    operation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{16,128}$")
    handoff: RazorpayCheckoutHandoff
    callback: RazorpayCheckoutCallback
    operation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def binding_and_digest_are_valid(self):
        if self.callback.razorpay_order_id != self.handoff.order.order_id:
            raise ValueError("prepared callback belongs to another Checkout order")
        expected = sha256_hex(self.model_dump(exclude={"operation_sha256"}))
        if self.operation_sha256 != expected:
            raise ValueError("prepared Test operation digest is invalid")
        return self

    @classmethod
    def create(cls, **values) -> "PreparedRazorpayTestOperation":
        body = {"schema_version": "D.RAZORPAY.OPERATION.1", **values}
        return cls(**body, operation_sha256=sha256_hex(body))


def load_prepared_test_operation(
    path: str | Path,
    *,
    expected_file_sha256: str,
) -> PreparedRazorpayTestOperation:
    """Load the sensitive callback bundle only through an out-of-band file pin."""

    if len(expected_file_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in expected_file_sha256
    ):
        raise ValueError("prepared operation file SHA-256 is invalid")
    target = Path(path)
    if target.is_symlink():
        raise ValueError("symlinked prepared operation file is forbidden")
    try:
        raw = target.resolve().read_bytes()
    except OSError as exc:
        raise ValueError("prepared operation file is unavailable") from exc
    if not raw or len(raw) > MAX_PREPARED_OPERATION_BYTES:
        raise ValueError("prepared operation file size is invalid")
    if sha256(raw).hexdigest() != expected_file_sha256:
        raise ValueError("prepared operation file digest mismatch")
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("prepared operation file is invalid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("prepared operation file must contain one JSON object")
    try:
        return PreparedRazorpayTestOperation.model_validate(payload)
    except ValueError as exc:
        raise ValueError("prepared operation schema or digest is invalid") from exc


class TestExecutionResult(BaseModel):
    """Redacted result from one compensated Razorpay Test Mode product run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["D.TEST.EXECUTION.RESULT.1"] = (
        "D.TEST.EXECUTION.RESULT.1"
    )
    operation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{16,128}$")
    provider_mode: Literal["RAZORPAY_TEST_MODE"] = "RAZORPAY_TEST_MODE"
    simulated: Literal[False] = False
    provider_called: Literal[True] = True
    real_money_moved: Literal[False] = False
    counts_as_checkpoint_d_pass: Literal[False] = False
    lifecycle: RazorpayLifecycleEvidence
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def digest_is_valid(self):
        expected = sha256_hex(self.model_dump(exclude={"result_sha256"}))
        if self.result_sha256 != expected:
            raise ValueError("Test execution result digest is invalid")
        return self

    @classmethod
    def create(cls, **values) -> "TestExecutionResult":
        body = {
            "schema_version": "D.TEST.EXECUTION.RESULT.1",
            "provider_mode": "RAZORPAY_TEST_MODE",
            "simulated": False,
            "provider_called": True,
            "real_money_moved": False,
            "counts_as_checkpoint_d_pass": False,
            **values,
        }
        return cls(**body, result_sha256=sha256_hex(body))

    @property
    def outcome(self) -> str:
        if self.lifecycle.checkpoint_b8_lifecycle_passed:
            return "TEST_MODE_CAPTURED_AND_COMPENSATED"
        return "TEST_MODE_COMPENSATION_PENDING"


class TestExecutionAdapter(Protocol):
    def execute(
        self,
        *,
        operation_id: str,
        correlation_id: str,
    ) -> TestExecutionResult: ...


class RazorpayPreparedTestExecutionAdapter:
    """Execute only immutable operations installed by the server operator.

    Request bodies cannot supply transactions, evidence, callbacks, credentials,
    signing keys, or provider configuration. An optional durable idempotency
    backend may replay the completed redacted result after a process restart.
    The underlying payment adapter must independently use provider-side
    idempotency and durable payment state for its crash windows.
    """

    def __init__(
        self,
        operations: Mapping[str, PreparedRazorpayTestOperation],
        *,
        payment_adapter: RazorpayTestPaymentAdapter,
        signing_secret: bytes,
        commitment_store: CommitmentStateStore,
        idempotency: IdempotencyBackend | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if len(signing_secret) < 32:
            raise ValueError("Test execution signing secret must contain at least 32 bytes")
        copied: dict[str, PreparedRazorpayTestOperation] = {}
        for operation_id, operation in operations.items():
            if operation_id != operation.operation_id:
                raise ValueError("prepared operation key does not match its operation id")
            copied[operation_id] = operation.model_copy(deep=True)
        if not copied:
            raise ValueError("at least one prepared Test operation is required")
        self._operations = MappingProxyType(copied)
        self._payment_adapter = payment_adapter
        self._signing_secret = bytes(signing_secret)
        self._commitment_store = commitment_store
        self._idempotency = idempotency or IdempotencyLedger()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def execute(
        self,
        *,
        operation_id: str,
        correlation_id: str,
    ) -> TestExecutionResult:
        del correlation_id  # Correlation is retained by the audit boundary, not the provider.
        operation = self._operations.get(operation_id)
        if operation is None:
            raise TestExecutionError(
                "PREPARED_OPERATION_NOT_FOUND",
                provider_call_status="NOT_STARTED",
            )
        fingerprint = request_fingerprint({
            "operation_sha256": operation.operation_sha256,
            "provider_mode": "RAZORPAY_TEST_MODE",
        })

        def perform() -> TestExecutionResult:
            now = self._clock()
            if now.tzinfo is None or now.utcoffset() is None:
                raise TestExecutionError(
                    "EXECUTION_CLOCK_INVALID",
                    provider_call_status="NOT_STARTED",
                )
            if now > operation.handoff.expires_at and not has_bound_lifecycle_state(
                operation.handoff,
                operation.callback,
                adapter=self._payment_adapter,
                commitment_store=self._commitment_store,
            ):
                raise TestExecutionError(
                    "PREPARED_OPERATION_EXPIRED",
                    provider_call_status="NOT_STARTED",
                )
            try:
                lifecycle = complete_test_lifecycle(
                    operation.handoff,
                    operation.callback,
                    adapter=self._payment_adapter,
                    now=now,
                    signing_secret=self._signing_secret,
                    commitment_store=self._commitment_store,
                )
            except TestExecutionError:
                raise
            except Exception:
                # Once the lifecycle starts, a transport or process-boundary
                # failure must be reconciled; it is unsafe to claim no call ran.
                raise TestExecutionError(
                    "TEST_EXECUTION_FAILED_RECONCILIATION_REQUIRED",
                    provider_call_status="STARTED_OR_UNKNOWN",
                ) from None
            result = TestExecutionResult.create(
                operation_id=operation.operation_id,
                lifecycle=lifecycle,
            )
            if not lifecycle.checkpoint_b8_lifecycle_passed:
                # A pending refund is not a terminal idempotent result. Remove
                # the operation-level lease so a later webhook/reconciliation
                # update can be observed on retry.
                raise _PendingExecution(result)
            return result

        try:
            result = self._idempotency.execute(
                scope="CHECKPOINT_D_RAZORPAY_TEST_EXECUTION",
                key=operation.operation_id,
                fingerprint=fingerprint,
                operation=perform,
            )
        except _PendingExecution as pending:
            return pending.result
        except TestExecutionError:
            raise
        except Exception:
            raise TestExecutionError(
                "TEST_EXECUTION_LEDGER_FAILURE",
                provider_call_status="STARTED_OR_UNKNOWN",
            ) from None
        if not isinstance(result, TestExecutionResult):
            raise TestExecutionError(
                "TEST_EXECUTION_RESULT_INVALID",
                provider_call_status="STARTED_OR_UNKNOWN",
            )
        return result


# These are application types, not pytest test containers when imported into a
# regression module.
TestExecutionError.__test__ = False
TestExecutionResult.__test__ = False

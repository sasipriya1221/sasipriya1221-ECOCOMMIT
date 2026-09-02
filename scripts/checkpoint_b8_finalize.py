from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ecocommit._canonical import sha256_hex, strict_json_loads
from ecocommit.audit import AppendOnlyAuditLog
from ecocommit.checkpoint_a_evidence import CheckpointAEvidenceReceipt
from ecocommit.checkpoint_b_evidence import (
    CheckpointBEvidenceReceipt,
    RazorpayTestLifecycleEvidence,
)
from ecocommit.github_actions import (
    GitHubRunVerificationError,
    load_preflight_receipt,
)
from ecocommit.razorpay_checkout import (
    RazorpayCheckoutHandoff,
    RazorpayLifecycleEvidence,
)
from ecocommit.webhook import VerifiedRazorpayWebhookSet


MAX_JSON_ARTIFACT_BYTES = 2 * 1024 * 1024
MAX_AUDIT_BYTES = 8 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SOURCE_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
EVIDENCE_REFERENCE_PATTERN = re.compile(
    r"^github-actions://(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/"
    r"runs/(?P<run_id>[0-9]{1,20})/artifacts/"
    r"(?P<artifact>[A-Za-z0-9][A-Za-z0-9_.-]{0,127})$"
)

REQUIRED_SAFETY_GROUPS = {
    "CHECKPOINT_B",
    "DURABLE_STATE",
    "RAZORPAY_ADAPTER",
    "WEBHOOK_INGESTION",
    "WORKFLOW_SECURITY",
}
REQUIRED_DURABILITY_SCENARIOS = {
    "COMMITMENT_RESTART_REPLAY",
    "CROSS_PROCESS_IDEMPOTENCY",
    "HANDOFF_EXPIRY_RECONCILIATION",
    "PAYMENT_RESTART_REPLAY",
    "PENDING_REFUND_RETRY",
    "WEBHOOK_EVENT_DEDUPLICATION",
}


class B8FinalizationError(RuntimeError):
    """One or more retained B8 artifacts failed closed verification."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DeterministicSafetyManifest(_StrictModel):
    """Machine-readable test counts; the finalizer derives the pass decision."""

    schema_version: Literal["B8.DETERMINISTIC_SAFETY.1"]
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    collected_tests: int = Field(gt=0, strict=True)
    passed_tests: int = Field(ge=0, strict=True)
    failed_tests: int = Field(ge=0, strict=True)
    error_tests: int = Field(ge=0, strict=True)
    covered_groups: tuple[str, ...] = Field(min_length=1)
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def complete_pass_is_derived(self):
        if (
            self.passed_tests != self.collected_tests
            or self.failed_tests != 0
            or self.error_tests != 0
        ):
            raise ValueError("deterministic safety test counts are not a complete pass")
        if len(set(self.covered_groups)) != len(self.covered_groups):
            raise ValueError("deterministic safety groups must be unique")
        if set(self.covered_groups) != REQUIRED_SAFETY_GROUPS:
            raise ValueError("deterministic safety manifest omits a required group")
        return self


class DurabilityTestManifest(_StrictModel):
    """Required restart/concurrency scenarios without a caller pass boolean."""

    schema_version: Literal["B8.DURABILITY_TESTS.1"]
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    state_store_backend: Literal["SQLITE_WAL_FULL_SYNC"]
    completed_scenarios: tuple[str, ...] = Field(min_length=1)
    failed_scenarios: tuple[str, ...] = ()
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def required_scenarios_are_complete(self):
        if self.failed_scenarios:
            raise ValueError("durability manifest contains failed scenarios")
        if len(set(self.completed_scenarios)) != len(self.completed_scenarios):
            raise ValueError("durability scenarios must be unique")
        if set(self.completed_scenarios) != REQUIRED_DURABILITY_SCENARIOS:
            raise ValueError("durability manifest omits a required scenario")
        return self


class CertificateKeyBoundaryReference(_StrictModel):
    """Non-secret reference for the explicitly limited local HMAC boundary."""

    schema_version: Literal["B8.CERTIFICATE_KEY_REFERENCE.1"]
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    boundary: Literal["ENVIRONMENT_ONLY_HMAC_TEST_BOUNDARY"]
    key_reference_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    minimum_secret_bytes: int = Field(ge=32, strict=True)
    retained_material_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def no_key_material_is_retained(self):
        if self.retained_material_fields:
            raise ValueError("certificate-key reference retains key material")
        return self


class _DashboardConfigurationObservation(_StrictModel):
    """Non-secret binding to an independently retained Dashboard observation."""

    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    provider_account_binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_mode: Literal["TEST"]
    observed_at_utc: datetime
    observation_artifact_kind: Literal["RAZORPAY_TEST_DASHBOARD_SCREENSHOT"]
    observation_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verification_reference_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("observed_at_utc")
    @classmethod
    def observation_time_is_utc(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Dashboard observation time must be timezone-aware")
        if value.utcoffset().total_seconds() != 0:
            raise ValueError("Dashboard observation time must be expressed in UTC")
        return value.astimezone(UTC)


class ManualCaptureConfigurationAttestation(_DashboardConfigurationObservation):
    """Independent Test Dashboard evidence for the manual-capture boundary."""

    schema_version: Literal["B8.MANUAL_CAPTURE_CONFIGURATION.1"]
    capture_mode: Literal["MANUAL"]
    manual_capture_timeout_seconds: Literal[259200]
    capture_timeout_action: Literal["NORMAL_REFUND"]


class WebhookConfigurationAttestation(_DashboardConfigurationObservation):
    """Independent Test Dashboard evidence for the exact webhook subscription."""

    schema_version: Literal["B8.WEBHOOK_CONFIGURATION.1"]
    endpoint_scheme: Literal["HTTPS"]
    endpoint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    enabled_state: Literal["ENABLED"]
    enabled_events: tuple[
        Literal["payment.captured", "refund.processed"], ...
    ] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def exact_events_are_enabled(self):
        if self.enabled_events != ("payment.captured", "refund.processed"):
            raise ValueError("webhook attestation must enable the exact canonical events")
        return self


class _CredentialsEvidence(_StrictModel):
    injected_from_environment: Literal[True]
    test_prefix_validated: Literal[True]
    key_id_retained: Literal[False]
    key_secret_retained: Literal[False]


class _GitHubEvidence(_StrictModel):
    run_id: str = Field(pattern=r"^[0-9]{1,20}$")
    run_attempt: str = Field(pattern=r"^[0-9]{1,10}$")
    sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    ref_name: str = Field(min_length=1, max_length=256)
    credential_preflight_run_id: str = Field(pattern=r"^[0-9]{1,20}$")


class _AuthenticationEvidence(_StrictModel):
    credential_preflight_run_reference_present: Literal[True]
    credential_preflight_run_verified: Literal[True]
    preflight_response_body_retained: Literal[False]
    credentialed_order_api_succeeded: Literal[True]
    preflight_verification_source: Literal["GITHUB_ACTIONS_API"]
    preflight_reference_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preflight_source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")


class _ProviderCall(_StrictModel):
    method: Literal["GET", "POST"]
    path: str = Field(min_length=1, max_length=2048)

    @field_validator("path")
    @classmethod
    def path_is_origin_relative(cls, value: str):
        if not value.startswith("/") or "://" in value or "\\" in value:
            raise ValueError("provider-call path must remain origin-relative")
        return value


class _TransactionEvidence(_StrictModel):
    transaction_id: str = Field(min_length=1, max_length=256)
    transaction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    merchant_id: str = Field(min_length=1, max_length=256)
    amount_minor: int = Field(gt=0, strict=True)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class _OrderEvidence(_StrictModel):
    executed: Literal[True]
    order_id: str = Field(pattern=r"^order_[A-Za-z0-9]+$")
    receipt: str = Field(min_length=1, max_length=40)
    provider_status: Literal["created"]
    amount_minor: int = Field(gt=0, strict=True)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    transaction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_response_recovered: bool


class _IdempotencyEvidence(_StrictModel):
    validated: Literal[True]
    identical_replay_returned_same_order: Literal[True]
    provider_create_order_post_count: Literal[1]
    idempotency_key_retained: Literal[False]


class _PaymentsForOrderEvidence(_StrictModel):
    executed: Literal[True]
    count: Literal[0]
    payment_ids: tuple[()] = ()
    statuses: tuple[()] = ()


class _CheckoutHandoffEvidence(_StrictModel):
    generated: Literal[True]
    schema_version: Literal["B8.CHECKOUT.1"]
    handoff_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime
    public_key_id_retained_only_in_handoff: Literal[True]
    secret_key_retained: Literal[False]

    @field_validator("expires_at")
    @classmethod
    def expiry_is_aware(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Checkout handoff expiry must be timezone-aware")
        return value


class _NotExecutedEvidence(_StrictModel):
    executed: Literal[False]
    reason: str = Field(min_length=1)


class _ExternalBlocker(_StrictModel):
    code: Literal["RAZORPAY_CHECKOUT_AUTHORIZATION_REQUIRED"]
    boundary: Literal["RAZORPAY_PRODUCT_API"]
    detail: str = Field(min_length=1)


class OrderBoundaryEvidence(_StrictModel):
    schema_version: Literal["B8.1"]
    checkpoint: Literal["B8_RAZORPAY_TEST_MODE"]
    generated_at: datetime
    provider: Literal["RAZORPAY"]
    provider_mode: Literal["TEST"]
    credentials: _CredentialsEvidence
    github: _GitHubEvidence
    authentication: _AuthenticationEvidence
    provider_calls: tuple[_ProviderCall, ...] = Field(min_length=1)
    transaction: _TransactionEvidence
    order: _OrderEvidence
    checkout_handoff: _CheckoutHandoffEvidence
    idempotency: _IdempotencyEvidence
    payments_for_order: _PaymentsForOrderEvidence
    authorization: _NotExecutedEvidence
    capture: _NotExecutedEvidence
    refund: _NotExecutedEvidence
    settlement: _NotExecutedEvidence
    checkpoint_b8_passed: Literal[False]
    status: Literal["ORDER_API_VALIDATED_PAYMENT_LIFECYCLE_BLOCKED"]
    external_blocker: _ExternalBlocker

    @field_validator("generated_at")
    @classmethod
    def generated_time_is_aware(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("order evidence generation time must be timezone-aware")
        return value

    @model_validator(mode="after")
    def partial_order_boundary_is_coherent(self):
        if self.transaction.amount_minor != 100 or self.transaction.currency != "INR":
            raise ValueError("B8 finalization requires the bound INR 1.00 Test order")
        if (
            self.order.amount_minor != self.transaction.amount_minor
            or self.order.currency != self.transaction.currency
            or self.order.transaction_digest != self.transaction.transaction_digest
        ):
            raise ValueError("order evidence does not match its transaction")
        create_posts = sum(
            call.method == "POST" and call.path == "/orders"
            for call in self.provider_calls
        )
        if create_posts != 1:
            raise ValueError("order evidence must contain exactly one create-order call")
        if any(
            call.method == "POST" and call.path != "/orders"
            for call in self.provider_calls
        ):
            raise ValueError("order-boundary evidence contains a later provider mutation")
        exact_order_gets = sum(
            call.method == "GET" and call.path == f"/orders/{self.order.order_id}"
            for call in self.provider_calls
        )
        exact_payment_gets = sum(
            call.method == "GET"
            and call.path == f"/orders/{self.order.order_id}/payments"
            for call in self.provider_calls
        )
        if exact_order_gets < 2 or exact_payment_gets != 1:
            raise ValueError("order evidence omits exact order/payment revalidation")
        return self


def _read_raw(path: Path, label: str, *, maximum: int) -> bytes:
    if path.is_symlink():
        raise B8FinalizationError(f"{label} must not be a symlink")
    try:
        raw = path.resolve().read_bytes()
    except OSError:
        raise B8FinalizationError(f"{label} is unavailable") from None
    if not raw or len(raw) > maximum:
        raise B8FinalizationError(f"{label} size is invalid")
    return raw


def _read_json(path: Path, label: str) -> tuple[bytes, dict[str, object]]:
    raw = _read_raw(path, label, maximum=MAX_JSON_ARTIFACT_BYTES)
    try:
        decoded = strict_json_loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise B8FinalizationError(f"{label} is not strict UTF-8 JSON") from None
    if not isinstance(decoded, dict):
        raise B8FinalizationError(f"{label} must contain one JSON object")
    return raw, decoded


def _load_model(path: Path, label: str, model_type):
    raw, decoded = _read_json(path, label)
    try:
        model = model_type.model_validate(decoded)
    except ValueError:
        raise B8FinalizationError(f"{label} schema or digest is invalid") from None
    return raw, model


def _load_verified_preflight(path: Path):
    raw, decoded = _read_json(path, "preflight receipt")
    repository = decoded.get("repository")
    run_id = decoded.get("run_id")
    source_revision = decoded.get("head_sha")
    if (
        not isinstance(repository, str)
        or not REPOSITORY_PATTERN.fullmatch(repository)
        or not isinstance(run_id, int)
        or isinstance(run_id, bool)
        or run_id <= 0
        or not isinstance(source_revision, str)
        or not SOURCE_REVISION_PATTERN.fullmatch(source_revision)
    ):
        raise B8FinalizationError("preflight receipt identity is invalid")
    try:
        verified = load_preflight_receipt(
            path,
            repository=repository,
            run_id=run_id,
            expected_sha=source_revision,
        )
    except GitHubRunVerificationError:
        raise B8FinalizationError("preflight receipt verification failed") from None
    return raw, verified


def _file_sha256(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _same_revision(actual: str, expected: str, label: str) -> None:
    if actual != expected:
        raise B8FinalizationError(f"{label} source revision does not match preflight")


def _verify_external_configuration(
    *,
    manual_capture: ManualCaptureConfigurationAttestation,
    webhook_configuration: WebhookConfigurationAttestation,
    source_revision: str,
    handoff: RazorpayCheckoutHandoff,
    webhooks: VerifiedRazorpayWebhookSet,
    finalized_at: datetime,
) -> None:
    _same_revision(
        manual_capture.source_revision,
        source_revision,
        "manual-capture configuration attestation",
    )
    _same_revision(
        webhook_configuration.source_revision,
        source_revision,
        "webhook configuration attestation",
    )
    if (
        manual_capture.provider_account_binding_sha256
        != webhook_configuration.provider_account_binding_sha256
    ):
        raise B8FinalizationError(
            "Dashboard configuration attestations bind different provider accounts"
        )
    expected_account_binding = sha256(handoff.public_key_id.encode("utf-8")).hexdigest()
    if manual_capture.provider_account_binding_sha256 != expected_account_binding:
        raise B8FinalizationError(
            "Dashboard configuration account does not match the Checkout Test account"
        )
    if (
        manual_capture.observation_artifact_sha256
        == webhook_configuration.observation_artifact_sha256
    ):
        raise B8FinalizationError(
            "Dashboard configuration attestations require independent artifacts"
        )
    first_webhook_at = min(
        webhooks.captured.received_at_utc,
        webhooks.refund_processed.received_at_utc,
    ).astimezone(UTC)
    if manual_capture.observed_at_utc > webhooks.captured.received_at_utc.astimezone(UTC):
        raise B8FinalizationError(
            "manual-capture configuration was not observed before capture"
        )
    if webhook_configuration.observed_at_utc > first_webhook_at:
        raise B8FinalizationError(
            "webhook configuration was not observed before webhook delivery"
        )
    if (
        manual_capture.observed_at_utc > finalized_at
        or webhook_configuration.observed_at_utc > finalized_at
    ):
        raise B8FinalizationError(
            "Dashboard configuration observation occurs after finalization"
        )


def _verify_handoff(order: OrderBoundaryEvidence, handoff: RazorpayCheckoutHandoff) -> None:
    transaction = handoff.transaction
    retained = order.transaction
    if (
        transaction.transaction_id != retained.transaction_id
        or transaction.digest() != retained.transaction_digest
        or transaction.merchant_id != retained.merchant_id
        or transaction.amount_minor != retained.amount_minor
        or transaction.currency != retained.currency
        or transaction.contract_hash != retained.contract_hash
    ):
        raise B8FinalizationError("Checkout handoff transaction does not match order evidence")
    provider_order = handoff.order
    if (
        provider_order.order_id != order.order.order_id
        or provider_order.receipt != order.order.receipt
        or provider_order.transaction_id != retained.transaction_id
        or provider_order.transaction_digest != retained.transaction_digest
        or provider_order.amount_minor != retained.amount_minor
        or provider_order.currency != retained.currency
        or provider_order.provider_status != order.order.provider_status
        or provider_order.recovered != order.order.provider_response_recovered
    ):
        raise B8FinalizationError("Checkout handoff order does not match order evidence")
    if order.checkout_handoff.handoff_sha256 != handoff.handoff_sha256:
        raise B8FinalizationError("Checkout handoff digest does not match order evidence")
    if order.checkout_handoff.expires_at != handoff.expires_at:
        raise B8FinalizationError("Checkout handoff expiry does not match order evidence")


def _verify_lifecycle(
    handoff: RazorpayCheckoutHandoff,
    lifecycle: RazorpayLifecycleEvidence,
) -> None:
    if (
        lifecycle.handoff_sha256 != handoff.handoff_sha256
        or lifecycle.transaction_digest != handoff.transaction.digest()
        or lifecycle.order_id != handoff.order.order_id
    ):
        raise B8FinalizationError("lifecycle evidence is not bound to the Checkout handoff")
    if (
        not lifecycle.checkpoint_b8_lifecycle_passed
        or lifecycle.reserve_state != "RESERVED"
        or lifecycle.capture_state != "CAPTURED"
        or lifecycle.refund_state != "REFUNDED"
        or lifecycle.commitment_stage != "COMPENSATED"
        or not lifecycle.reconciliation_in_sync
        or lifecycle.durable_state_backend != "SQLITE_WAL_FULL_SYNC"
    ):
        raise B8FinalizationError("provider lifecycle is incomplete")


def _verify_webhooks(
    handoff: RazorpayCheckoutHandoff,
    lifecycle: RazorpayLifecycleEvidence,
    webhooks: VerifiedRazorpayWebhookSet,
) -> None:
    records = (webhooks.captured, webhooks.refund_processed)
    if (
        webhooks.transaction_id != handoff.transaction.transaction_id
        or webhooks.transaction_digest != handoff.transaction.digest()
        or any(record.order_id != lifecycle.order_id for record in records)
        or any(record.payment_id != lifecycle.payment_id for record in records)
        or webhooks.refund_processed.refund_id != lifecycle.refund_id
        or any(record.amount_minor != handoff.transaction.amount_minor for record in records)
        or any(record.currency != handoff.transaction.currency for record in records)
    ):
        raise B8FinalizationError("verified webhook set does not match the provider lifecycle")


def _verify_audit(path: Path, webhooks: VerifiedRazorpayWebhookSet):
    raw = _read_raw(path, "webhook audit log", maximum=MAX_AUDIT_BYTES)
    audit = AppendOnlyAuditLog(path)
    verification = audit.verify()
    if not verification.valid or verification.entries < 2:
        raise B8FinalizationError("webhook audit log integrity verification failed")
    required_records = {
        webhooks.captured.record_sha256,
        webhooks.refund_processed.record_sha256,
    }
    retained_records = {
        event.payload.get("record_sha256")
        for event in audit.events()
        if event.event_type == "razorpay.webhook.verified"
        and event.payload.get("signature_verified") is True
        and event.payload.get("binding_verified") is True
    }
    if not required_records.issubset(retained_records):
        raise B8FinalizationError("webhook audit log omits a verified lifecycle event")
    return raw, verification.head_hash


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_exclusive(path: Path, raw: bytes) -> None:
    """Publish complete bytes atomically without overwriting an existing file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise B8FinalizationError("finalization output parent must not be a symlink")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        os.chmod(temporary_name, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        descriptor = -1
        try:
            os.link(temporary_name, path)
        except FileExistsError:
            raise B8FinalizationError("finalization output already exists") from None
    finally:
        if descriptor != -1:
            os.close(descriptor)
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _write_or_verify(path: Path, raw: bytes, label: str) -> bool:
    """Write once, or accept the exact bytes left by a prior interrupted run."""

    if path.exists() or path.is_symlink():
        retained = _read_raw(path, label, maximum=MAX_JSON_ARTIFACT_BYTES)
        if retained != raw:
            raise B8FinalizationError(f"{label} conflicts with derived evidence")
        return False
    try:
        _write_exclusive(path, raw)
        return True
    except B8FinalizationError:
        if not path.exists() and not path.is_symlink():
            raise
        retained = _read_raw(path, label, maximum=MAX_JSON_ARTIFACT_BYTES)
        if retained != raw:
            raise B8FinalizationError(f"{label} conflicts with derived evidence") from None
        return False


def _validate_evidence_reference(value: str, repository: str) -> tuple[str, int]:
    match = EVIDENCE_REFERENCE_PATTERN.fullmatch(value)
    if match is None or match.group("repository").casefold() != repository.casefold():
        raise B8FinalizationError(
            "evidence reference must identify an exact artifact in the same repository"
        )
    return value, int(match.group("run_id"))


def finalize_b8(
    *,
    preflight_path: Path,
    order_evidence_path: Path,
    handoff_path: Path,
    lifecycle_path: Path,
    webhook_evidence_path: Path,
    checkpoint_a_receipt_path: Path,
    deterministic_safety_manifest_path: Path,
    durability_manifest_path: Path,
    certificate_key_reference_path: Path,
    manual_capture_attestation_path: Path,
    webhook_configuration_attestation_path: Path,
    audit_path: Path,
    evidence_reference: str,
    provider_manifest_output: Path,
    receipt_output: Path,
    generated_at: datetime | None = None,
) -> CheckpointBEvidenceReceipt:
    """Cross-check retained artifacts and emit one derived Checkpoint B receipt."""

    if provider_manifest_output.resolve() == receipt_output.resolve():
        raise B8FinalizationError("provider manifest and receipt outputs must differ")
    retained_receipt: CheckpointBEvidenceReceipt | None = None
    if receipt_output.exists() or receipt_output.is_symlink():
        _, retained_receipt = _load_model(
            receipt_output,
            "Checkpoint B receipt output",
            CheckpointBEvidenceReceipt,
        )
    if retained_receipt is not None and generated_at is not None:
        supplied_time = generated_at
        if supplied_time.tzinfo is None or supplied_time.utcoffset() is None:
            raise B8FinalizationError("finalization time must be timezone-aware")
        if supplied_time.astimezone(UTC) != retained_receipt.generated_at_utc:
            raise B8FinalizationError(
                "Checkpoint B receipt output conflicts with finalization time"
            )
    observed_at = (
        retained_receipt.generated_at_utc
        if retained_receipt is not None
        else generated_at or datetime.now(UTC)
    )
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise B8FinalizationError("finalization time must be timezone-aware")
    observed_at = observed_at.astimezone(UTC)

    preflight_raw, preflight = _load_verified_preflight(preflight_path)
    source_revision = preflight["head_sha"]
    evidence_reference, retention_run_id = _validate_evidence_reference(
        evidence_reference,
        preflight["repository"],
    )
    order_raw, order = _load_model(
        order_evidence_path,
        "order-boundary evidence",
        OrderBoundaryEvidence,
    )
    handoff_raw, handoff = _load_model(
        handoff_path,
        "Checkout handoff",
        RazorpayCheckoutHandoff,
    )
    lifecycle_raw, lifecycle = _load_model(
        lifecycle_path,
        "provider lifecycle evidence",
        RazorpayLifecycleEvidence,
    )
    webhook_raw, webhooks = _load_model(
        webhook_evidence_path,
        "webhook evidence",
        VerifiedRazorpayWebhookSet,
    )
    a_raw, a_receipt = _load_model(
        checkpoint_a_receipt_path,
        "Checkpoint A receipt",
        CheckpointAEvidenceReceipt,
    )
    safety_raw, safety = _load_model(
        deterministic_safety_manifest_path,
        "deterministic safety manifest",
        DeterministicSafetyManifest,
    )
    durability_raw, durability = _load_model(
        durability_manifest_path,
        "durability manifest",
        DurabilityTestManifest,
    )
    certificate_raw, certificate = _load_model(
        certificate_key_reference_path,
        "certificate-key boundary reference",
        CertificateKeyBoundaryReference,
    )
    manual_capture_raw, manual_capture = _load_model(
        manual_capture_attestation_path,
        "manual-capture configuration attestation",
        ManualCaptureConfigurationAttestation,
    )
    webhook_configuration_raw, webhook_configuration = _load_model(
        webhook_configuration_attestation_path,
        "webhook configuration attestation",
        WebhookConfigurationAttestation,
    )

    _same_revision(order.github.sha, source_revision, "order evidence")
    _same_revision(
        order.authentication.preflight_source_revision,
        source_revision,
        "order preflight binding",
    )
    _same_revision(a_receipt.source_revision, source_revision, "Checkpoint A receipt")
    _same_revision(safety.source_revision, source_revision, "safety manifest")
    _same_revision(durability.source_revision, source_revision, "durability manifest")
    _same_revision(certificate.source_revision, source_revision, "certificate reference")
    if a_receipt.verification_mode != "FROZEN_AGGREGATE":
        raise B8FinalizationError("Checkpoint A receipt is not authoritative frozen evidence")
    if order.github.credential_preflight_run_id != str(preflight["run_id"]):
        raise B8FinalizationError("order evidence references another preflight run")
    if (
        order.authentication.preflight_reference_receipt_sha256
        != preflight["receipt_sha256"]
    ):
        raise B8FinalizationError("order evidence references another preflight receipt")

    _verify_handoff(order, handoff)
    _verify_lifecycle(handoff, lifecycle)
    _verify_webhooks(handoff, lifecycle, webhooks)
    _verify_external_configuration(
        manual_capture=manual_capture,
        webhook_configuration=webhook_configuration,
        source_revision=source_revision,
        handoff=handoff,
        webhooks=webhooks,
        finalized_at=observed_at,
    )
    audit_raw, audit_head = _verify_audit(audit_path, webhooks)

    artifact_hashes = {
        "checkpoint_a_receipt": _file_sha256(a_raw),
        "certificate_key_reference": _file_sha256(certificate_raw),
        "checkout_handoff": _file_sha256(handoff_raw),
        "deterministic_safety_manifest": _file_sha256(safety_raw),
        "durability_manifest": _file_sha256(durability_raw),
        "manual_capture_configuration_attestation": _file_sha256(
            manual_capture_raw
        ),
        "order_boundary_evidence": _file_sha256(order_raw),
        "preflight_receipt": _file_sha256(preflight_raw),
        "provider_lifecycle_evidence": _file_sha256(lifecycle_raw),
        "webhook_configuration_attestation": _file_sha256(
            webhook_configuration_raw
        ),
        "webhook_audit_log": _file_sha256(audit_raw),
        "webhook_evidence": _file_sha256(webhook_raw),
    }
    provider_manifest: dict[str, object] = {
        "schema_version": "B8.FINALIZATION.MANIFEST.1",
        "source_revision": source_revision,
        "repository": preflight["repository"],
        "preflight_run_id": preflight["run_id"],
        "order_run_id": int(order.github.run_id),
        "evidence_reference": evidence_reference,
        "retention_run_id": retention_run_id,
        "transaction_id": handoff.transaction.transaction_id,
        "transaction_digest": handoff.transaction.digest(),
        "order_id": lifecycle.order_id,
        "payment_id": lifecycle.payment_id,
        "refund_id": lifecycle.refund_id,
        "amount_minor": handoff.transaction.amount_minor,
        "currency": handoff.transaction.currency,
        "handoff_sha256": handoff.handoff_sha256,
        "webhook_set_sha256": webhooks.set_sha256,
        "audit_head_sha256": audit_head,
        "external_configuration": {
            "provider_account_binding_sha256": (
                manual_capture.provider_account_binding_sha256
            ),
            "manual_capture": {
                "source_revision": manual_capture.source_revision,
                "provider_mode": manual_capture.provider_mode,
                "capture_mode": manual_capture.capture_mode,
                "manual_capture_timeout_seconds": (
                    manual_capture.manual_capture_timeout_seconds
                ),
                "capture_timeout_action": manual_capture.capture_timeout_action,
                "observed_at_utc": manual_capture.observed_at_utc.isoformat(),
                "observation_artifact_kind": (
                    manual_capture.observation_artifact_kind
                ),
                "observation_artifact_sha256": (
                    manual_capture.observation_artifact_sha256
                ),
                "verifier_identity_sha256": (
                    manual_capture.verifier_identity_sha256
                ),
                "verification_reference_sha256": (
                    manual_capture.verification_reference_sha256
                ),
            },
            "webhook": {
                "source_revision": webhook_configuration.source_revision,
                "provider_mode": webhook_configuration.provider_mode,
                "endpoint_scheme": webhook_configuration.endpoint_scheme,
                "endpoint_sha256": webhook_configuration.endpoint_sha256,
                "enabled_state": webhook_configuration.enabled_state,
                "enabled_events": list(webhook_configuration.enabled_events),
                "observed_at_utc": (
                    webhook_configuration.observed_at_utc.isoformat()
                ),
                "observation_artifact_kind": (
                    webhook_configuration.observation_artifact_kind
                ),
                "observation_artifact_sha256": (
                    webhook_configuration.observation_artifact_sha256
                ),
                "verifier_identity_sha256": (
                    webhook_configuration.verifier_identity_sha256
                ),
                "verification_reference_sha256": (
                    webhook_configuration.verification_reference_sha256
                ),
            },
        },
        "artifact_file_sha256": artifact_hashes,
    }
    provider_manifest["manifest_sha256"] = sha256_hex(provider_manifest)
    provider_manifest_raw = _json_bytes(provider_manifest)

    lifecycle_receipt = RazorpayTestLifecycleEvidence(
        order_id=lifecycle.order_id,
        payment_id=lifecycle.payment_id,
        refund_id=lifecycle.refund_id,
        amount_minor=handoff.transaction.amount_minor,
        captured_amount_minor=handoff.transaction.amount_minor,
        refunded_amount_minor=handoff.transaction.amount_minor,
        currency=handoff.transaction.currency,
        webhook_event_ids=(
            webhooks.captured.event_id,
            webhooks.refund_processed.event_id,
        ),
        checkout_lifecycle_result_sha256=_file_sha256(lifecycle_raw),
        webhook_set_sha256=webhooks.set_sha256,
        durability_test_manifest_sha256=_file_sha256(durability_raw),
        state_store_backend=lifecycle.durable_state_backend,
        audit_head_sha256=audit_head,
    )
    receipt = CheckpointBEvidenceReceipt.create(
        evidence_reference=evidence_reference,
        generated_at_utc=observed_at.astimezone(UTC),
        source_revision=source_revision,
        checkpoint_a_receipt_sha256=_file_sha256(a_raw),
        deterministic_safety_suite_sha256=_file_sha256(safety_raw),
        certificate_key_reference_sha256=_file_sha256(certificate_raw),
        provider_evidence_artifact_sha256=_file_sha256(provider_manifest_raw),
        lifecycle=lifecycle_receipt,
    )
    receipt_raw = _json_bytes(receipt.model_dump(mode="json"))

    _write_or_verify(
        provider_manifest_output,
        provider_manifest_raw,
        "provider manifest output",
    )
    _write_or_verify(receipt_output, receipt_raw, "Checkpoint B receipt output")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-check retained B8 Test artifacts and derive a fail-closed "
            "Checkpoint B receipt without accepting pass flags."
        )
    )
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--order-evidence", type=Path, required=True)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--lifecycle", type=Path, required=True)
    parser.add_argument("--webhook-evidence", type=Path, required=True)
    parser.add_argument("--checkpoint-a-receipt", type=Path, required=True)
    parser.add_argument("--deterministic-safety-manifest", type=Path, required=True)
    parser.add_argument("--durability-manifest", type=Path, required=True)
    parser.add_argument("--certificate-key-reference", type=Path, required=True)
    parser.add_argument("--manual-capture-attestation", type=Path, required=True)
    parser.add_argument(
        "--webhook-configuration-attestation",
        type=Path,
        required=True,
    )
    parser.add_argument("--audit-log", type=Path, required=True)
    parser.add_argument(
        "--evidence-reference",
        required=True,
        help=(
            "Exact retained artifact reference: "
            "github-actions://OWNER/REPO/runs/RUN_ID/artifacts/ARTIFACT"
        ),
    )
    parser.add_argument("--provider-manifest-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        receipt = finalize_b8(
            preflight_path=args.preflight,
            order_evidence_path=args.order_evidence,
            handoff_path=args.handoff,
            lifecycle_path=args.lifecycle,
            webhook_evidence_path=args.webhook_evidence,
            checkpoint_a_receipt_path=args.checkpoint_a_receipt,
            deterministic_safety_manifest_path=args.deterministic_safety_manifest,
            durability_manifest_path=args.durability_manifest,
            certificate_key_reference_path=args.certificate_key_reference,
            manual_capture_attestation_path=args.manual_capture_attestation,
            webhook_configuration_attestation_path=(
                args.webhook_configuration_attestation
            ),
            audit_path=args.audit_log,
            evidence_reference=args.evidence_reference,
            provider_manifest_output=args.provider_manifest_output,
            receipt_output=args.output,
        )
    except B8FinalizationError as exc:
        parser.error(str(exc))

    print(json.dumps({
        "finalized": True,
        "checkpoint_b_gate_passed": receipt.gate_passed,
        "source_revision": receipt.source_revision,
        "receipt_sha256": receipt.receipt_sha256,
        "provider_test_mode": receipt.provider_test_mode,
        "real_money_moved": receipt.real_money_moved,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

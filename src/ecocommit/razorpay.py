from __future__ import annotations

import base64
import hmac
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from threading import RLock
from typing import Any, Literal, Mapping, Protocol
from urllib import error, parse, request

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._canonical import sha256_hex
from .certificates import CertificateVerifier, CommitCertificate
from .commitment import CommitmentState
from .evidence import EvidenceRegistry
from .exposure import TransactionBinding
from .idempotency import IdempotencyBackend, IdempotencyLedger, request_fingerprint
from .payments import (
    InMemoryPaymentStateStore,
    PaymentOperation,
    PaymentProviderError,
    PaymentResult,
    PaymentSnapshot,
    PaymentState,
    PaymentStateError,
    PaymentStateStore,
    SimulatedPaymentAdapter,
)


_ORDER_ID = re.compile(r"^order_[A-Za-z0-9]+$")
_PAYMENT_ID = re.compile(r"^pay_[A-Za-z0-9]+$")
_REFUND_ID = re.compile(r"^rfnd_[A-Za-z0-9]+$")
_HEX_SIGNATURE = re.compile(r"^[0-9a-fA-F]{64}$")
_API_BASE_URL = "https://api.razorpay.com/v1"
_MAX_WEBHOOK_BODY_BYTES = 1024 * 1024


def _reject_provider_constant(value: str):
    raise ValueError(f"non-finite provider JSON constant is forbidden: {value}")


def _unique_provider_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate provider JSON keys are forbidden")
        value[key] = item
    return value


class RazorpayConfigurationError(ValueError):
    pass


class RazorpayTransportError(PaymentProviderError):
    """A response was not received or could not be validated."""


class RazorpayAPIError(PaymentProviderError):
    """Safe provider error metadata; response bodies and credentials are discarded."""

    def __init__(self, *, status_code: int, provider_code: str | None = None):
        self.status_code = status_code
        self.provider_code = provider_code
        suffix = f" provider_code={provider_code}" if provider_code else ""
        super().__init__(f"Razorpay API request failed with HTTP {status_code}{suffix}")


class RazorpayUnsupportedOperation(PaymentStateError):
    pass


@dataclass(frozen=True, repr=False)
class RazorpayTestCredentials:
    key_id: str
    key_secret: str

    def __post_init__(self) -> None:
        if not self.key_id or not self.key_secret:
            raise RazorpayConfigurationError("Razorpay key id and secret are required")
        if not self.key_id.startswith("rzp_test_"):
            raise RazorpayConfigurationError("Razorpay Test adapter refuses non-test credentials")
        if any(character.isspace() for character in self.key_id + self.key_secret):
            raise RazorpayConfigurationError("Razorpay credentials cannot contain whitespace")

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> RazorpayTestCredentials:
        source = os.environ if environ is None else environ
        return cls(
            key_id=source.get("RAZORPAY_KEY_ID", ""),
            key_secret=source.get("RAZORPAY_KEY_SECRET", ""),
        )

    def __repr__(self) -> str:
        return "RazorpayTestCredentials(key_id=<redacted>, key_secret=<redacted>)"


class RazorpayTransport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]: ...


class RazorpayHTTPTransport:
    """Small fail-closed HTTPS transport with no credential or body logging."""

    def __init__(
        self,
        credentials: RazorpayTestCredentials,
        *,
        timeout_seconds: float = 30.0,
        base_url: str = _API_BASE_URL,
    ):
        if timeout_seconds <= 0:
            raise ValueError("Razorpay timeout must be positive")
        if base_url != _API_BASE_URL:
            raise RazorpayConfigurationError("Razorpay credential transport requires the official API origin")
        token = base64.b64encode(
            f"{credentials.key_id}:{credentials.key_secret}".encode("utf-8")
        ).decode("ascii")
        self._authorization = f"Basic {token}"
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url

    def __repr__(self) -> str:
        return (
            "RazorpayHTTPTransport(base_url='https://api.razorpay.com/v1', "
            "credentials=<redacted>)"
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        method = method.upper()
        if method not in {"GET", "POST"}:
            raise ValueError("unsupported Razorpay HTTP method")
        if not path.startswith("/") or "://" in path or "\\" in path:
            raise ValueError("Razorpay API path must be origin-relative")

        encoded = None
        request_headers = {
            "Accept": "application/json",
            "User-Agent": "ECOCOMMIT-Razorpay-Test/1.0",
        }
        if payload is not None:
            encoded = json.dumps(
                payload,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        for name, value in (headers or {}).items():
            if name.lower() in {"authorization", "host", "content-length"}:
                raise ValueError("protected Razorpay HTTP header cannot be overridden")
            if not isinstance(value, str) or "\r" in value or "\n" in value:
                raise ValueError("Razorpay HTTP header value is invalid")
            request_headers[name] = value
        api_request = request.Request(
            self.base_url + path,
            data=encoded,
            headers=request_headers,
            method=method,
        )
        api_request.add_unredirected_header("Authorization", self._authorization)
        try:
            with request.urlopen(api_request, timeout=self.timeout_seconds) as response:
                final_url = (
                    response.geturl()
                    if hasattr(response, "geturl")
                    else api_request.full_url
                )
                if final_url != api_request.full_url:
                    raise RazorpayTransportError("Razorpay response URL was redirected")
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise RazorpayTransportError("Razorpay response exceeded the safety limit")
        except error.HTTPError as exc:
            raw_error = exc.read(65_537)
            provider_code = _safe_provider_code(raw_error)
            raise RazorpayAPIError(
                status_code=exc.code,
                provider_code=provider_code,
            ) from None
        except (error.URLError, TimeoutError, OSError):
            raise RazorpayTransportError("Razorpay request did not return a usable response") from None

        try:
            decoded = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_provider_object,
                parse_constant=_reject_provider_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise RazorpayTransportError("Razorpay returned invalid JSON") from None
        if not isinstance(decoded, dict):
            raise RazorpayTransportError("Razorpay returned a non-object response")
        return decoded


def _safe_provider_code(raw: bytes) -> str | None:
    if len(raw) > 65_536:
        return None
    try:
        decoded = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_provider_object,
            parse_constant=_reject_provider_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(decoded, dict) or not isinstance(decoded.get("error"), dict):
        return None
    code = decoded["error"].get("code")
    if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_]{1,80}", code):
        return None
    return code


class RazorpayOrderResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    simulated: Literal[False] = False
    adapter_name: Literal["RAZORPAY_TEST_MODE"] = "RAZORPAY_TEST_MODE"
    transaction_id: str
    transaction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    amount_minor: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    order_id: str = Field(pattern=r"^order_[A-Za-z0-9]+$")
    receipt: str = Field(min_length=1, max_length=40)
    provider_status: Literal["created", "attempted", "paid"]
    recovered: bool = False


class RazorpayPaymentResult(PaymentResult):
    model_config = ConfigDict(frozen=True, extra="forbid")

    simulated: Literal[False] = False
    adapter_name: Literal["RAZORPAY_TEST_MODE"] = "RAZORPAY_TEST_MODE"
    provider_status: str = Field(min_length=1)
    order_id: str = Field(pattern=r"^order_[A-Za-z0-9]+$")
    payment_id: str = Field(pattern=r"^pay_[A-Za-z0-9]+$")
    refund_id: str | None = Field(default=None, pattern=r"^rfnd_[A-Za-z0-9]+$")
    recovered: bool = False

    @model_validator(mode="after")
    def coherent_provider_reference(self):
        if self.operation == PaymentOperation.REFUND:
            if self.refund_id is None or self.provider_reference != self.refund_id:
                raise ValueError("Razorpay refund result must reference its refund id")
            if self.state not in {PaymentState.REFUND_PENDING, PaymentState.REFUNDED}:
                raise ValueError("Razorpay refund result has an invalid ECOCOMMIT state")
        elif self.refund_id is not None or self.provider_reference != self.payment_id:
            raise ValueError("Razorpay payment result must reference its payment id")
        return self


class _PendingRefund(RuntimeError):
    """Return a non-terminal result without committing an idempotency record."""

    def __init__(self, result: RazorpayPaymentResult) -> None:
        super().__init__("RAZORPAY_REFUND_PENDING")
        self.result = result


class RazorpayObservedPayment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: str = Field(pattern=r"^order_[A-Za-z0-9]+$")
    payment_id: str = Field(pattern=r"^pay_[A-Za-z0-9]+$")
    amount_minor: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    provider_status: Literal["created", "authorized", "captured", "refunded", "failed"]
    captured: bool
    amount_captured: int = Field(ge=0)
    amount_refunded: int = Field(ge=0)


class RazorpayTestPaymentAdapter:
    """Razorpay Test Mode adapter guarded by ECOCOMMIT's irreversible boundary.

    The provider's Orders API prepares Checkout but cannot collect a payment.
    ``reserve`` therefore binds an already-authorized Checkout payment only after
    validating its signature and fetching the exact order/payment from Razorpay.
    """

    is_simulation: Literal[False] = False
    adapter_name: Literal["RAZORPAY_TEST_MODE"] = "RAZORPAY_TEST_MODE"

    def __init__(
        self,
        *,
        credentials: RazorpayTestCredentials,
        transport: RazorpayTransport | None = None,
        idempotency: IdempotencyBackend | None = None,
        state_store: PaymentStateStore | None = None,
    ):
        self._credentials = credentials
        self._transport = transport or RazorpayHTTPTransport(credentials)
        self._idempotency = idempotency or IdempotencyLedger()
        self._orders: dict[str, RazorpayOrderResult] = {}
        self._state_store = state_store or InMemoryPaymentStateStore()
        self._lock = RLock()

    @classmethod
    def from_environment(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        timeout_seconds: float = 30.0,
        idempotency: IdempotencyBackend | None = None,
        state_store: PaymentStateStore | None = None,
    ) -> RazorpayTestPaymentAdapter:
        credentials = RazorpayTestCredentials.from_environment(environ)
        return cls(
            credentials=credentials,
            transport=RazorpayHTTPTransport(
                credentials,
                timeout_seconds=timeout_seconds,
            ),
            idempotency=idempotency,
            state_store=state_store,
        )

    def __repr__(self) -> str:
        return "RazorpayTestPaymentAdapter(mode='test', credentials=<redacted>)"

    def verify_credentials(self) -> bool:
        """Perform a read-only authenticated Test Mode preflight.

        The response body is validated in memory and never returned, logged, or
        retained as evidence by this method. Callers must separately audit only
        the boolean outcome and Test Mode boundary.
        """

        response = self._transport.request("GET", "/orders?count=1")
        if (
            response.get("entity") != "collection"
            or not isinstance(response.get("items"), list)
            or not isinstance(response.get("count"), int)
            or isinstance(response.get("count"), bool)
            or response["count"] < 0
        ):
            raise RazorpayTransportError(
                "Razorpay credential preflight returned an invalid collection"
            )
        return True

    def create_order(
        self,
        transaction: TransactionBinding,
        *,
        idempotency_key: str,
    ) -> RazorpayOrderResult:
        receipt = _provider_idempotency_token(
            "order",
            transaction=transaction,
            idempotency_key=idempotency_key,
            max_length=40,
        )
        fingerprint = request_fingerprint(
            {
                "operation": "CREATE_ORDER",
                "transaction": transaction,
                "receipt": receipt,
            }
        )

        def perform() -> RazorpayOrderResult:
            with self._lock:
                existing = self._orders.get(transaction.transaction_id)
                if existing is not None:
                    if existing.transaction_digest != transaction.digest():
                        raise PaymentStateError("transaction binding changed after order creation")
                    raise PaymentStateError(
                        "transaction already has a Razorpay order under a different idempotency key"
                    )

                recovered = self._find_order_by_receipt(receipt)
                if recovered is not None:
                    result = self._validate_order(
                        recovered,
                        transaction=transaction,
                        expected_receipt=receipt,
                        recovered=True,
                    )
                    self._orders[transaction.transaction_id] = result
                    return result

                payload = {
                    "amount": transaction.amount_minor,
                    "currency": transaction.currency,
                    "receipt": receipt,
                    "notes": _binding_notes(transaction),
                }
                try:
                    created = self._transport.request("POST", "/orders", payload=payload)
                except (RazorpayAPIError, RazorpayTransportError):
                    # A timeout or duplicate-receipt response can be ambiguous.
                    # Recover only an exact provider-side receipt+binding match.
                    recovered = self._find_order_by_receipt(receipt)
                    if recovered is None:
                        raise
                    result = self._validate_order(
                        recovered,
                        transaction=transaction,
                        expected_receipt=receipt,
                        recovered=True,
                    )
                else:
                    result = self._validate_order(
                        created,
                        transaction=transaction,
                        expected_receipt=receipt,
                        recovered=False,
                    )
                self._orders[transaction.transaction_id] = result
                return result

        return self._idempotency.execute(
            scope=f"RAZORPAY_TEST_MODE:{transaction.transaction_id}:CREATE_ORDER",
            key=idempotency_key,
            fingerprint=fingerprint,
            operation=perform,
        )

    def fetch_order(
        self,
        transaction: TransactionBinding,
        *,
        order_id: str,
    ) -> RazorpayOrderResult:
        _require_identifier(order_id, _ORDER_ID, "order")
        order = self._transport.request("GET", f"/orders/{order_id}")
        return self._validate_order(
            order,
            transaction=transaction,
            expected_order_id=order_id,
        )

    def fetch_payments_for_order(
        self,
        transaction: TransactionBinding,
        *,
        order_id: str,
    ) -> tuple[RazorpayObservedPayment, ...]:
        # Revalidate the order binding first; a caller-supplied order id is never
        # sufficient authority to observe or bind a payment.
        self.fetch_order(transaction, order_id=order_id)
        collection = self._transport.request("GET", f"/orders/{order_id}/payments")
        if collection.get("entity") != "collection" or not isinstance(collection.get("items"), list):
            raise RazorpayTransportError("Razorpay returned an invalid payment collection")
        observed: list[RazorpayObservedPayment] = []
        for payment in collection["items"]:
            if not isinstance(payment, dict):
                raise RazorpayTransportError("Razorpay returned an invalid payment item")
            payment_id = payment.get("id")
            _require_identifier(payment_id, _PAYMENT_ID, "payment")
            status = payment.get("status")
            allowed = {"created", "authorized", "captured", "refunded", "failed"}
            self._validate_payment(
                payment,
                transaction=transaction,
                order_id=order_id,
                payment_id=payment_id,
                allowed_statuses=allowed,
                require_full_capture=status in {"captured", "refunded"},
            )
            observed.append(
                RazorpayObservedPayment(
                    order_id=order_id,
                    payment_id=payment_id,
                    amount_minor=transaction.amount_minor,
                    currency=transaction.currency,
                    provider_status=status,
                    captured=payment.get("captured") is True,
                    amount_captured=_strict_int(
                        payment.get("amount_captured", 0),
                        "captured amount",
                    ),
                    amount_refunded=_strict_int(
                        payment.get("amount_refunded", 0),
                        "refunded amount",
                    ),
                )
            )
        return tuple(observed)

    def reserve(
        self,
        transaction: TransactionBinding,
        *,
        order_id: str,
        payment_id: str,
        checkout_signature: str,
        idempotency_key: str,
    ) -> RazorpayPaymentResult:
        """Bind a real Test Mode ``authorized`` payment as the reversible hold."""

        _require_identifier(order_id, _ORDER_ID, "order")
        _require_identifier(payment_id, _PAYMENT_ID, "payment")
        fingerprint = request_fingerprint(
            {
                "operation": PaymentOperation.RESERVE.value,
                "transaction": transaction,
                "order_id": order_id,
                "payment_id": payment_id,
                "checkout_signature": checkout_signature,
            }
        )

        def perform() -> RazorpayPaymentResult:
            self._verify_checkout_signature(
                order_id=order_id,
                payment_id=payment_id,
                checkout_signature=checkout_signature,
            )
            with self._lock:
                current = self._state_store.get(transaction.transaction_id)
                if current is not None and current.state != PaymentState.NONE:
                    SimulatedPaymentAdapter._assert_transaction_unchanged(current, transaction)
                    if (
                        current.order_id == order_id
                        and current.payment_id == payment_id
                        and current.state
                        in {
                            PaymentState.RESERVED,
                            PaymentState.CAPTURED,
                            PaymentState.REFUND_PENDING,
                            PaymentState.REFUNDED,
                        }
                    ):
                        return self._payment_result(
                            transaction,
                            operation=PaymentOperation.RESERVE,
                            state=PaymentState.RESERVED,
                            provider_reference=payment_id,
                            provider_status="authorized",
                            order_id=order_id,
                            payment_id=payment_id,
                            recovered=True,
                        )
                    raise PaymentStateError("transaction already has bound payment activity")

                order = self._transport.request("GET", f"/orders/{order_id}")
                self._validate_order(
                    order,
                    transaction=transaction,
                    expected_order_id=order_id,
                    allowed_statuses={"attempted"},
                )
                payment = self._transport.request("GET", f"/payments/{payment_id}")
                self._validate_payment(
                    payment,
                    transaction=transaction,
                    order_id=order_id,
                    payment_id=payment_id,
                    allowed_statuses={"authorized"},
                )
                snapshot = PaymentSnapshot(
                    simulated=False,
                    adapter_name="RAZORPAY_TEST_MODE",
                    transaction_id=transaction.transaction_id,
                    state=PaymentState.RESERVED,
                    amount_minor=transaction.amount_minor,
                    currency=transaction.currency,
                    transaction_digest=transaction.digest(),
                    last_reference=payment_id,
                    order_id=order_id,
                    payment_id=payment_id,
                )
                self._state_store.compare_and_set(
                    transaction.transaction_id,
                    expected=current,
                    updated=snapshot,
                )
                return self._payment_result(
                    transaction,
                    operation=PaymentOperation.RESERVE,
                    state=PaymentState.RESERVED,
                    provider_reference=payment_id,
                    provider_status="authorized",
                    order_id=order_id,
                    payment_id=payment_id,
                )

        return self._idempotency.execute(
            scope=f"RAZORPAY_TEST_MODE:{transaction.transaction_id}:RESERVE",
            key=idempotency_key,
            fingerprint=fingerprint,
            operation=perform,
        )

    bind_authorized_payment = reserve

    def capture(
        self,
        transaction: TransactionBinding,
        *,
        commitment: CommitmentState,
        certificate: CommitCertificate,
        verifier: CertificateVerifier,
        registry: EvidenceRegistry,
        now: datetime,
        idempotency_key: str,
    ) -> RazorpayPaymentResult:
        with self._lock:
            current = self._state_store.get(transaction.transaction_id)
            if current is None or current.order_id is None or current.payment_id is None:
                raise PaymentStateError("Razorpay capture requires a bound authorized payment")
            order_id = current.order_id
            payment_id = current.payment_id
        fingerprint = request_fingerprint(
            {
                "operation": PaymentOperation.CAPTURE.value,
                "transaction": transaction,
                "commitment": commitment,
                "certificate": certificate,
                "order_id": order_id,
                "payment_id": payment_id,
            }
        )

        def perform() -> RazorpayPaymentResult:
            with registry.hold_snapshot_current(certificate.evidence_snapshot, now=now):
                with self._lock:
                    current = self._state_store.get(transaction.transaction_id)
                    if current is None:
                        raise PaymentStateError(
                            "Razorpay capture lost its bound authorized payment state"
                        )
                    SimulatedPaymentAdapter._assert_transaction_unchanged(current, transaction)
                    if (
                        current.order_id == order_id
                        and current.payment_id == payment_id
                        and current.state
                        in {
                            PaymentState.CAPTURED,
                            PaymentState.REFUND_PENDING,
                            PaymentState.REFUNDED,
                        }
                    ):
                        if (
                            commitment.transaction != transaction
                            or commitment.certificate_id != certificate.certificate_id
                            or commitment.reservation_reference != payment_id
                        ):
                            raise PaymentStateError(
                                "recovered capture authority does not match durable payment state"
                            )
                        verifier.verify(
                            certificate,
                            expected_transaction=transaction,
                            expected_contract_hash=transaction.contract_hash,
                            registry=registry,
                            now=now,
                        )
                        return self._payment_result(
                            transaction,
                            operation=PaymentOperation.CAPTURE,
                            state=PaymentState.CAPTURED,
                            provider_reference=payment_id,
                            provider_status="captured",
                            order_id=order_id,
                            payment_id=payment_id,
                            recovered=True,
                        )
                    SimulatedPaymentAdapter._assert_capture_authority(
                        commitment,
                        transaction=transaction,
                        certificate=certificate,
                        current=current,
                    )
                    verifier.verify(
                        certificate,
                        expected_transaction=transaction,
                        expected_contract_hash=transaction.contract_hash,
                        registry=registry,
                        now=now,
                    )
                    payment = self._transport.request("GET", f"/payments/{payment_id}")
                    self._validate_payment(
                        payment,
                        transaction=transaction,
                        order_id=order_id,
                        payment_id=payment_id,
                        allowed_statuses={"authorized"},
                    )
                    try:
                        captured = self._transport.request(
                            "POST",
                            f"/payments/{payment_id}/capture",
                            payload={
                                "amount": transaction.amount_minor,
                                "currency": transaction.currency,
                            },
                        )
                        recovered = False
                    except (RazorpayAPIError, RazorpayTransportError):
                        captured = self._transport.request("GET", f"/payments/{payment_id}")
                        if captured.get("status") != "captured":
                            raise
                        recovered = True
                    self._validate_payment(
                        captured,
                        transaction=transaction,
                        order_id=order_id,
                        payment_id=payment_id,
                        allowed_statuses={"captured"},
                        require_full_capture=True,
                    )
                    updated = current.model_copy(
                        update={
                            "state": PaymentState.CAPTURED,
                            "last_reference": payment_id,
                        }
                    )
                    self._state_store.compare_and_set(
                        transaction.transaction_id,
                        expected=current,
                        updated=updated,
                    )
                    return self._payment_result(
                        transaction,
                        operation=PaymentOperation.CAPTURE,
                        state=PaymentState.CAPTURED,
                        provider_reference=payment_id,
                        provider_status="captured",
                        order_id=order_id,
                        payment_id=payment_id,
                        recovered=recovered,
                    )

        return self._idempotency.execute(
            scope=f"RAZORPAY_TEST_MODE:{transaction.transaction_id}:CAPTURE",
            key=idempotency_key,
            fingerprint=fingerprint,
            operation=perform,
        )

    def void(
        self,
        transaction: TransactionBinding,
        *,
        idempotency_key: str,
    ) -> RazorpayPaymentResult:
        del transaction, idempotency_key
        raise RazorpayUnsupportedOperation(
            "Razorpay exposes no immediate void API for an authorized payment; "
            "uncaptured authorizations must follow the configured auto-refund timeout"
        )

    def refund(
        self,
        transaction: TransactionBinding,
        *,
        idempotency_key: str,
    ) -> RazorpayPaymentResult:
        with self._lock:
            current = self._state_store.get(transaction.transaction_id)
            if current is None or current.order_id is None or current.payment_id is None:
                raise PaymentStateError("Razorpay refund requires a captured bound payment")
            order_id = current.order_id
            payment_id = current.payment_id
        refund_token = _provider_idempotency_token(
            "refund",
            transaction=transaction,
            idempotency_key=idempotency_key,
            max_length=40,
        )
        fingerprint = request_fingerprint(
            {
                "operation": PaymentOperation.REFUND.value,
                "transaction": transaction,
                "order_id": order_id,
                "payment_id": payment_id,
                "refund_token": refund_token,
            }
        )

        def perform() -> RazorpayPaymentResult:
            with self._lock:
                current = self._state_store.get(transaction.transaction_id)
                if current is None:
                    raise PaymentStateError("Razorpay refund lost its captured payment state")
                SimulatedPaymentAdapter._assert_transaction_unchanged(current, transaction)
                if (
                    current.order_id == order_id
                    and current.payment_id == payment_id
                    and current.state == PaymentState.REFUNDED
                    and current.refund_id is not None
                ):
                    return self._payment_result(
                        transaction,
                        operation=PaymentOperation.REFUND,
                        state=PaymentState.REFUNDED,
                        provider_reference=current.refund_id,
                        provider_status="processed",
                        order_id=order_id,
                        payment_id=payment_id,
                        refund_id=current.refund_id,
                        recovered=True,
                    )
                if (
                    current.order_id == order_id
                    and current.payment_id == payment_id
                    and current.state == PaymentState.REFUND_PENDING
                    and current.refund_id is not None
                ):
                    refund = self._transport.request(
                        "GET",
                        f"/refunds/{current.refund_id}",
                    )
                    refund_id, provider_status, state = self._validate_refund(
                        refund,
                        transaction=transaction,
                        payment_id=payment_id,
                    )
                    if refund_id != current.refund_id:
                        raise PaymentStateError(
                            "Razorpay refund lookup returned another refund"
                        )
                    result = self._payment_result(
                        transaction,
                        operation=PaymentOperation.REFUND,
                        state=state,
                        provider_reference=refund_id,
                        provider_status=provider_status,
                        order_id=order_id,
                        payment_id=payment_id,
                        refund_id=refund_id,
                        recovered=True,
                    )
                    if state == PaymentState.REFUND_PENDING:
                        raise _PendingRefund(result)
                    updated = current.model_copy(
                        update={
                            "state": PaymentState.REFUNDED,
                            "last_reference": refund_id,
                        }
                    )
                    self._state_store.compare_and_set(
                        transaction.transaction_id,
                        expected=current,
                        updated=updated,
                    )
                    return result
                if current.state != PaymentState.CAPTURED:
                    raise PaymentStateError(
                        f"cannot REFUND Razorpay payment from {current.state.value}"
                    )
                payment = self._transport.request("GET", f"/payments/{payment_id}")
                self._validate_payment(
                    payment,
                    transaction=transaction,
                    order_id=order_id,
                    payment_id=payment_id,
                    allowed_statuses={"captured"},
                    require_full_capture=True,
                )
                refund = self._transport.request(
                    "POST",
                    f"/payments/{payment_id}/refund",
                    payload={
                        "amount": transaction.amount_minor,
                        "receipt": refund_token,
                        "notes": _binding_notes(transaction),
                    },
                    headers={"X-Refund-Idempotency": refund_token},
                )
                refund_id, provider_status, state = self._validate_refund(
                    refund,
                    transaction=transaction,
                    payment_id=payment_id,
                )
                updated = current.model_copy(
                    update={
                        "state": state,
                        "last_reference": refund_id,
                        "refund_id": refund_id,
                    }
                )
                self._state_store.compare_and_set(
                    transaction.transaction_id,
                    expected=current,
                    updated=updated,
                )
                result = self._payment_result(
                    transaction,
                    operation=PaymentOperation.REFUND,
                    state=state,
                    provider_reference=refund_id,
                    provider_status=provider_status,
                    order_id=order_id,
                    payment_id=payment_id,
                    refund_id=refund_id,
                )
                if state == PaymentState.REFUND_PENDING:
                    raise _PendingRefund(result)
                return result

        try:
            return self._idempotency.execute(
                # V2 deliberately does not retain a pending response as a
                # completed operation. Retrying polls the exact bound refund.
                # The ledger key is provider-payment scoped rather than caller
                # supplied, so two different local keys cannot race two full
                # refund submissions for one payment.
                scope=f"RAZORPAY_TEST_MODE:{transaction.transaction_id}:REFUND_V2",
                key=f"FULL_REFUND:{payment_id}",
                fingerprint=fingerprint,
                operation=perform,
            )
        except _PendingRefund as pending:
            return pending.result

    def snapshot(self, transaction_id: str) -> PaymentSnapshot:
        with self._lock:
            current = self._state_store.get(transaction_id)
            return (
                current
                if current is not None
                else PaymentSnapshot(
                    simulated=False,
                    adapter_name="RAZORPAY_TEST_MODE",
                    transaction_id=transaction_id,
                    state=PaymentState.NONE,
                )
            ).model_copy(deep=True)

    def _find_order_by_receipt(self, receipt: str) -> Mapping[str, Any] | None:
        query = parse.urlencode({"receipt": receipt, "count": 100})
        collection = self._transport.request("GET", f"/orders?{query}")
        if collection.get("entity") != "collection" or not isinstance(collection.get("items"), list):
            raise RazorpayTransportError("Razorpay returned an invalid order collection")
        matches = [
            item
            for item in collection["items"]
            if isinstance(item, dict) and item.get("receipt") == receipt
        ]
        if len(matches) > 1:
            raise PaymentStateError("multiple Razorpay orders share the idempotency receipt")
        return matches[0] if matches else None

    def _validate_order(
        self,
        order: Mapping[str, Any],
        *,
        transaction: TransactionBinding,
        expected_receipt: str | None = None,
        expected_order_id: str | None = None,
        allowed_statuses: set[str] | None = None,
        recovered: bool = False,
    ) -> RazorpayOrderResult:
        order_id = order.get("id")
        _require_identifier(order_id, _ORDER_ID, "order")
        if expected_order_id is not None and order_id != expected_order_id:
            raise PaymentStateError("Razorpay order identifier does not match the boundary")
        if order.get("entity") != "order":
            raise PaymentStateError("Razorpay response is not an order")
        if _strict_int(order.get("amount"), "order amount") != transaction.amount_minor:
            raise PaymentStateError("Razorpay order amount does not match the transaction")
        if order.get("currency") != transaction.currency:
            raise PaymentStateError("Razorpay order currency does not match the transaction")
        receipt = order.get("receipt")
        if not isinstance(receipt, str) or not receipt:
            raise PaymentStateError("Razorpay order is missing its receipt binding")
        if expected_receipt is not None and receipt != expected_receipt:
            raise PaymentStateError("Razorpay order receipt does not match the idempotency boundary")
        if order.get("notes") != _binding_notes(transaction):
            raise PaymentStateError("Razorpay order notes do not match the transaction binding")
        provider_status = order.get("status")
        valid_statuses = allowed_statuses or {"created", "attempted", "paid"}
        if provider_status not in valid_statuses:
            raise PaymentStateError("Razorpay order is in an unexpected state")
        return RazorpayOrderResult(
            transaction_id=transaction.transaction_id,
            transaction_digest=transaction.digest(),
            amount_minor=transaction.amount_minor,
            currency=transaction.currency,
            order_id=order_id,
            receipt=receipt,
            provider_status=provider_status,
            recovered=recovered,
        )

    @staticmethod
    def _validate_payment(
        payment: Mapping[str, Any],
        *,
        transaction: TransactionBinding,
        order_id: str,
        payment_id: str,
        allowed_statuses: set[str],
        require_full_capture: bool = False,
        require_no_refund: bool = False,
    ) -> None:
        if payment.get("entity") != "payment" or payment.get("id") != payment_id:
            raise PaymentStateError("Razorpay payment identifier does not match the boundary")
        if payment.get("order_id") != order_id:
            raise PaymentStateError("Razorpay payment belongs to another order")
        if _strict_int(payment.get("amount"), "payment amount") != transaction.amount_minor:
            raise PaymentStateError("Razorpay payment amount does not match the transaction")
        if payment.get("currency") != transaction.currency:
            raise PaymentStateError("Razorpay payment currency does not match the transaction")
        status = payment.get("status")
        if status not in allowed_statuses:
            raise PaymentStateError("Razorpay payment is in an unexpected state")
        if status == "authorized" and payment.get("captured") not in {False, None}:
            raise PaymentStateError("Razorpay payment was captured outside ECOCOMMIT")
        if require_full_capture:
            if payment.get("captured") is not True:
                raise PaymentStateError("Razorpay did not confirm capture")
            if _strict_int(payment.get("amount_captured"), "captured amount") != transaction.amount_minor:
                raise PaymentStateError("Razorpay captured amount does not match the transaction")
        if require_no_refund and _strict_int(
            payment.get("amount_refunded", 0),
            "refunded amount",
        ) != 0:
            raise PaymentStateError("Razorpay payment already contains a refund")

    @staticmethod
    def _validate_refund(
        refund: Mapping[str, Any],
        *,
        transaction: TransactionBinding,
        payment_id: str,
    ) -> tuple[str, str, PaymentState]:
        refund_id = refund.get("id")
        _require_identifier(refund_id, _REFUND_ID, "refund")
        if refund.get("entity") != "refund" or refund.get("payment_id") != payment_id:
            raise PaymentStateError("Razorpay refund does not match the bound payment")
        if _strict_int(refund.get("amount"), "refund amount") != transaction.amount_minor:
            raise PaymentStateError("Razorpay refund amount does not match the transaction")
        if refund.get("currency") != transaction.currency:
            raise PaymentStateError("Razorpay refund currency does not match the transaction")
        provider_status = refund.get("status")
        if provider_status == "processed":
            return refund_id, provider_status, PaymentState.REFUNDED
        if provider_status in {"pending", "created"}:
            return refund_id, provider_status, PaymentState.REFUND_PENDING
        raise PaymentStateError("Razorpay refund is in an unexpected state")

    def _verify_checkout_signature(
        self,
        *,
        order_id: str,
        payment_id: str,
        checkout_signature: str,
    ) -> None:
        if not isinstance(checkout_signature, str) or not _HEX_SIGNATURE.fullmatch(
            checkout_signature
        ):
            raise PaymentStateError("Razorpay Checkout signature format is invalid")
        expected = hmac.new(
            self._credentials.key_secret.encode("utf-8"),
            f"{order_id}|{payment_id}".encode("utf-8"),
            sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, checkout_signature.lower()):
            raise PaymentStateError("Razorpay Checkout signature is invalid")

    @staticmethod
    def _payment_result(
        transaction: TransactionBinding,
        *,
        operation: PaymentOperation,
        state: PaymentState,
        provider_reference: str,
        provider_status: str,
        order_id: str,
        payment_id: str,
        refund_id: str | None = None,
        recovered: bool = False,
    ) -> RazorpayPaymentResult:
        return RazorpayPaymentResult(
            transaction_id=transaction.transaction_id,
            operation=operation,
            state=state,
            amount_minor=transaction.amount_minor,
            currency=transaction.currency,
            provider_reference=provider_reference,
            provider_status=provider_status,
            order_id=order_id,
            payment_id=payment_id,
            refund_id=refund_id,
            recovered=recovered,
        )


class RazorpayWebhookVerifier:
    """Verify the raw webhook body before parsing it."""

    def __init__(self, secret: str):
        if not secret or any(character in secret for character in "\r\n"):
            raise RazorpayConfigurationError("Razorpay webhook secret is required")
        self._secret = secret.encode("utf-8")

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> RazorpayWebhookVerifier:
        source = os.environ if environ is None else environ
        return cls(source.get("RAZORPAY_WEBHOOK_SECRET", ""))

    def __repr__(self) -> str:
        return "RazorpayWebhookVerifier(secret=<redacted>)"

    def verify_and_decode(
        self,
        raw_body: bytes,
        signature: str,
    ) -> Mapping[str, Any]:
        if not isinstance(raw_body, bytes) or not isinstance(signature, str):
            raise PaymentStateError("Razorpay webhook body and signature are required")
        if not raw_body or len(raw_body) > _MAX_WEBHOOK_BODY_BYTES:
            raise PaymentStateError("Razorpay webhook body size is invalid")
        if not _HEX_SIGNATURE.fullmatch(signature):
            raise PaymentStateError("Razorpay webhook signature format is invalid")
        expected = hmac.new(self._secret, raw_body, sha256).hexdigest()
        if not hmac.compare_digest(expected, signature.lower()):
            raise PaymentStateError("Razorpay webhook signature is invalid")
        try:
            event = json.loads(
                raw_body.decode("utf-8"),
                object_pairs_hook=_unique_provider_object,
                parse_constant=_reject_provider_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise PaymentStateError("Razorpay webhook body is invalid JSON") from None
        if not isinstance(event, dict):
            raise PaymentStateError("Razorpay webhook body must be an object")
        return event


def _binding_notes(transaction: TransactionBinding) -> dict[str, str]:
    return {
        "ecocommit_transaction_digest": transaction.digest(),
        "ecocommit_contract_hash": transaction.contract_hash,
        "ecocommit_merchant_digest": sha256_hex(transaction.merchant_id),
    }


def _provider_idempotency_token(
    prefix: str,
    *,
    transaction: TransactionBinding,
    idempotency_key: str,
    max_length: int,
) -> str:
    if not idempotency_key:
        raise ValueError("idempotency key is required")
    digest = sha256_hex(
        {
            "prefix": prefix,
            "transaction_digest": transaction.digest(),
            "idempotency_key": idempotency_key,
        }
    )
    return f"ec_{prefix}_{digest}"[:max_length]


def _require_identifier(value: Any, pattern: re.Pattern[str], label: str) -> None:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise PaymentStateError(f"Razorpay {label} identifier is invalid")


def _strict_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PaymentStateError(f"Razorpay {label} is invalid")
    return value

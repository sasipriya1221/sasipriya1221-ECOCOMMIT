from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ._canonical import sha256_hex
from .audit import AppendOnlyAuditLog, AuditIntegrityError
from .durable import DurableStateConflict, SQLiteJSONStateStore
from .execution import PreparedRazorpayTestOperation
from .payments import PaymentStateError
from .razorpay import RazorpayWebhookVerifier


class WebhookProcessingError(RuntimeError):
    def __init__(self, code: str, *, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def _utc(value: datetime, field_name: str) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be expressed in UTC")
    return value


class RazorpayWebhookRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["B8.WEBHOOK.EVENT.1"] = "B8.WEBHOOK.EVENT.1"
    event_id: str = Field(min_length=1, max_length=256)
    event_type: Literal["payment.captured", "refund.processed"]
    received_at_utc: datetime
    raw_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_id: str = Field(min_length=1)
    transaction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    order_id: str = Field(pattern=r"^order_[A-Za-z0-9]+$")
    payment_id: str = Field(pattern=r"^pay_[A-Za-z0-9]+$")
    refund_id: str | None = Field(default=None, pattern=r"^rfnd_[A-Za-z0-9]+$")
    amount_minor: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    signature_verified: Literal[True] = True
    binding_verified: Literal[True] = True
    operation_key_mode: Literal["RAZORPAY_TEST_MODE"] = "RAZORPAY_TEST_MODE"
    webhook_endpoint_mode_independently_verified: Literal[False] = False
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("event_id")
    @classmethod
    def event_id_is_safe(cls, value: str):
        if any(ord(character) < 33 or ord(character) > 126 for character in value):
            raise ValueError("webhook event id must contain visible ASCII characters")
        return value

    @field_validator("received_at_utc")
    @classmethod
    def received_in_utc(cls, value: datetime):
        return _utc(value, "received_at_utc")

    @model_validator(mode="after")
    def event_shape_and_digest_are_valid(self):
        if self.event_type == "payment.captured" and self.refund_id is not None:
            raise ValueError("payment.captured cannot contain a refund id")
        if self.event_type == "refund.processed" and self.refund_id is None:
            raise ValueError("refund.processed requires a refund id")
        expected = sha256_hex(self.model_dump(exclude={"record_sha256"}))
        if self.record_sha256 != expected:
            raise ValueError("webhook record digest is invalid")
        return self

    @classmethod
    def create(cls, **values) -> "RazorpayWebhookRecord":
        body = {
            "schema_version": "B8.WEBHOOK.EVENT.1",
            "signature_verified": True,
            "binding_verified": True,
            "operation_key_mode": "RAZORPAY_TEST_MODE",
            "webhook_endpoint_mode_independently_verified": False,
            **values,
        }
        return cls(**body, record_sha256=sha256_hex(body))


class VerifiedRazorpayWebhookSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["B8.WEBHOOK.SET.1"] = "B8.WEBHOOK.SET.1"
    transaction_id: str = Field(min_length=1)
    transaction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    captured: RazorpayWebhookRecord
    refund_processed: RazorpayWebhookRecord
    signature_verified: Literal[True] = True
    bindings_verified: Literal[True] = True
    duplicate_safe: Literal[True] = True
    out_of_order_safe: Literal[True] = True
    raw_webhook_bodies_retained: Literal[False] = False
    set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def records_and_digest_are_valid(self):
        records = (self.captured, self.refund_processed)
        if self.captured.event_type != "payment.captured":
            raise ValueError("captured webhook record has the wrong event type")
        if self.refund_processed.event_type != "refund.processed":
            raise ValueError("refund webhook record has the wrong event type")
        if any(
            record.transaction_id != self.transaction_id
            or record.transaction_digest != self.transaction_digest
            for record in records
        ):
            raise ValueError("webhook set records belong to another transaction")
        if self.captured.payment_id != self.refund_processed.payment_id:
            raise ValueError("webhook set payment identifiers disagree")
        if self.captured.order_id != self.refund_processed.order_id:
            raise ValueError("webhook set order identifiers disagree")
        if (
            self.captured.amount_minor != self.refund_processed.amount_minor
            or self.captured.currency != self.refund_processed.currency
        ):
            raise ValueError("webhook set amount or currency disagrees")
        if self.captured.event_id == self.refund_processed.event_id:
            raise ValueError("webhook set event identifiers must be distinct")
        expected = sha256_hex(self.model_dump(exclude={"set_sha256"}))
        if self.set_sha256 != expected:
            raise ValueError("webhook set digest is invalid")
        return self

    @classmethod
    def create(cls, **values) -> "VerifiedRazorpayWebhookSet":
        body = {
            "schema_version": "B8.WEBHOOK.SET.1",
            "signature_verified": True,
            "bindings_verified": True,
            "duplicate_safe": True,
            "out_of_order_safe": True,
            "raw_webhook_bodies_retained": False,
            **values,
        }
        return cls(**body, set_sha256=sha256_hex(body))


class WebhookIngestResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: Literal[True] = True
    duplicate: bool
    event_type: Literal["payment.captured", "refund.processed"]
    event_id_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_key_mode: Literal["RAZORPAY_TEST_MODE"] = "RAZORPAY_TEST_MODE"
    webhook_endpoint_mode_independently_verified: Literal[False] = False
    real_money_moved: Literal[False] = False


class SQLiteWebhookEvidenceStore:
    _EVENT_NAMESPACE = "razorpay-webhook-events-v1"
    _INDEX_NAMESPACE = "razorpay-webhook-index-v1"

    def __init__(self, path_or_store: str | Path | SQLiteJSONStateStore) -> None:
        self._store = (
            path_or_store
            if isinstance(path_or_store, SQLiteJSONStateStore)
            else SQLiteJSONStateStore(path_or_store)
        )

    @staticmethod
    def _event_key(event_id: str) -> str:
        return sha256(event_id.encode("utf-8")).hexdigest()

    def record(
        self,
        record: RazorpayWebhookRecord,
    ) -> tuple[bool, RazorpayWebhookRecord]:
        key = self._event_key(record.event_id)
        payload = record.model_dump(mode="json")
        existing = self._store.load(self._EVENT_NAMESPACE, key)
        if existing is None:
            try:
                self._store.create(self._EVENT_NAMESPACE, key, payload)
                self._add_to_index(record.transaction_id, key)
                return False, record
            except DurableStateConflict:
                existing = self._store.load(self._EVENT_NAMESPACE, key)
        if existing is None:
            raise WebhookProcessingError(
                "WEBHOOK_STORE_CONCURRENT_CREATE_LOST",
                status_code=503,
            )
        try:
            stored = RazorpayWebhookRecord.model_validate(existing.value)
        except ValueError as exc:
            raise WebhookProcessingError(
                "WEBHOOK_STORE_INTEGRITY_FAILURE",
                status_code=503,
            ) from exc
        stable_fields = {"received_at_utc", "record_sha256"}
        if stored.model_dump(exclude=stable_fields) != record.model_dump(
            exclude=stable_fields
        ):
            raise WebhookProcessingError(
                "WEBHOOK_EVENT_ID_COLLISION",
                status_code=409,
            )
        self._add_to_index(stored.transaction_id, key)
        return True, stored

    def _add_to_index(self, transaction_id: str, event_key: str) -> None:
        for _ in range(8):
            document = self._store.load(self._INDEX_NAMESPACE, transaction_id)
            if document is None:
                try:
                    self._store.create(
                        self._INDEX_NAMESPACE,
                        transaction_id,
                        {"event_keys": [event_key]},
                    )
                    return
                except DurableStateConflict:
                    continue
            value = document.value
            keys = value.get("event_keys") if isinstance(value, dict) else None
            if (
                not isinstance(keys, list)
                or not all(_valid_event_key(item) for item in keys)
            ):
                raise WebhookProcessingError(
                    "WEBHOOK_INDEX_INTEGRITY_FAILURE",
                    status_code=503,
                )
            if event_key in keys:
                return
            try:
                self._store.compare_and_swap(
                    self._INDEX_NAMESPACE,
                    transaction_id,
                    expected_version=document.version,
                    expected_sha256=document.payload_sha256,
                    value={"event_keys": [*keys, event_key]},
                )
                return
            except DurableStateConflict:
                continue
        raise WebhookProcessingError(
            "WEBHOOK_INDEX_CONCURRENT_UPDATE_LIMIT",
            status_code=503,
        )

    def records(self, transaction_id: str) -> tuple[RazorpayWebhookRecord, ...]:
        index = self._store.load(self._INDEX_NAMESPACE, transaction_id)
        if index is None:
            return ()
        keys = index.value.get("event_keys") if isinstance(index.value, dict) else None
        if not isinstance(keys, list) or not all(_valid_event_key(item) for item in keys):
            raise WebhookProcessingError(
                "WEBHOOK_INDEX_INTEGRITY_FAILURE",
                status_code=503,
            )
        records: list[RazorpayWebhookRecord] = []
        for key in keys:
            document = self._store.load(self._EVENT_NAMESPACE, key)
            if document is None:
                raise WebhookProcessingError(
                    "WEBHOOK_INDEX_EVENT_MISSING",
                    status_code=503,
                )
            try:
                record = RazorpayWebhookRecord.model_validate(document.value)
            except ValueError as exc:
                raise WebhookProcessingError(
                    "WEBHOOK_STORE_INTEGRITY_FAILURE",
                    status_code=503,
                ) from exc
            if record.transaction_id != transaction_id:
                raise WebhookProcessingError(
                    "WEBHOOK_INDEX_BINDING_FAILURE",
                    status_code=503,
                )
            records.append(record)
        return tuple(sorted(records, key=lambda item: (item.received_at_utc, item.event_id)))

    def verified_set(self, transaction_id: str) -> VerifiedRazorpayWebhookSet:
        records = self.records(transaction_id)
        captured = [item for item in records if item.event_type == "payment.captured"]
        refunds = [item for item in records if item.event_type == "refund.processed"]
        if len(captured) != 1 or len(refunds) != 1:
            raise WebhookProcessingError(
                "COMPLETE_CAPTURE_AND_REFUND_WEBHOOK_SET_NOT_AVAILABLE",
                status_code=409,
            )
        return VerifiedRazorpayWebhookSet.create(
            transaction_id=transaction_id,
            transaction_digest=captured[0].transaction_digest,
            captured=captured[0],
            refund_processed=refunds[0],
        )


class BoundRazorpayWebhookProcessor:
    """Verify raw events and bind them to one startup-pinned Test operation."""

    def __init__(
        self,
        operation: PreparedRazorpayTestOperation,
        *,
        verifier: RazorpayWebhookVerifier,
        store: SQLiteWebhookEvidenceStore,
        audit_log: AppendOnlyAuditLog,
        clock=None,
    ) -> None:
        if not operation.handoff.public_key_id.startswith("rzp_test_"):
            raise ValueError("webhook processor refuses non-test operations")
        self.operation = operation.model_copy(deep=True)
        self.verifier = verifier
        self.store = store
        self.audit_log = audit_log
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def ingest(
        self,
        *,
        raw_body: bytes,
        signature: str,
        event_id: str,
    ) -> WebhookIngestResult:
        try:
            event = self.verifier.verify_and_decode(raw_body, signature)
        except PaymentStateError:
            raise WebhookProcessingError(
                "WEBHOOK_SIGNATURE_OR_BODY_INVALID",
                status_code=401,
            ) from None
        received_at = self.clock()
        if received_at.tzinfo is None or received_at.utcoffset() is None:
            raise WebhookProcessingError("WEBHOOK_CLOCK_INVALID", status_code=503)
        received_at = received_at.astimezone(timezone.utc)
        try:
            record = self._bind_event(
                event,
                event_id=event_id,
                raw_body_sha256=sha256(raw_body).hexdigest(),
                received_at=received_at,
            )
        except (KeyError, TypeError, ValueError):
            raise WebhookProcessingError(
                "WEBHOOK_EVENT_BINDING_INVALID",
                status_code=400,
            ) from None
        duplicate, record = self.store.record(record)
        event_id_sha256 = sha256(record.event_id.encode("utf-8")).hexdigest()
        try:
            self.audit_log.append(
                "razorpay.webhook.verified",
                f"webhook-{event_id_sha256[:24]}",
                {
                    "event_id_sha256": event_id_sha256,
                    "event_type": record.event_type,
                    "raw_body_sha256": record.raw_body_sha256,
                    "record_sha256": record.record_sha256,
                    "duplicate": duplicate,
                    "signature_verified": True,
                    "binding_verified": True,
                    "operation_key_mode": "RAZORPAY_TEST_MODE",
                    "webhook_endpoint_mode_independently_verified": False,
                    "real_money_moved": False,
                },
            )
        except (AuditIntegrityError, OSError):
            raise WebhookProcessingError(
                "WEBHOOK_AUDIT_UNAVAILABLE",
                status_code=503,
            ) from None
        return WebhookIngestResult(
            duplicate=duplicate,
            event_type=record.event_type,
            event_id_sha256=event_id_sha256,
            raw_body_sha256=record.raw_body_sha256,
            record_sha256=record.record_sha256,
        )

    def _bind_event(
        self,
        event,
        *,
        event_id: str,
        raw_body_sha256: str,
        received_at: datetime,
    ) -> RazorpayWebhookRecord:
        if event.get("entity") != "event":
            raise ValueError("not a Razorpay event")
        event_type = event.get("event")
        if event_type not in {"payment.captured", "refund.processed"}:
            raise ValueError("event type is outside the retained lifecycle set")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("event payload is invalid")
        payment_wrapper = payload.get("payment")
        payment = (
            payment_wrapper.get("entity")
            if isinstance(payment_wrapper, dict)
            else None
        )
        if not isinstance(payment, dict):
            raise ValueError("payment entity is required")

        transaction = self.operation.handoff.transaction
        callback = self.operation.callback
        if (
            payment.get("entity") != "payment"
            or payment.get("id") != callback.razorpay_payment_id
            or payment.get("order_id") != self.operation.handoff.order.order_id
            or _positive_int(payment.get("amount")) != transaction.amount_minor
            or payment.get("currency") != transaction.currency
        ):
            raise ValueError("payment webhook binding is invalid")

        refund_id = None
        if event_type == "payment.captured":
            if payment.get("status") != "captured" or payment.get("captured") is not True:
                raise ValueError("payment was not captured")
        else:
            refund_wrapper = payload.get("refund")
            refund = (
                refund_wrapper.get("entity")
                if isinstance(refund_wrapper, dict)
                else None
            )
            if not isinstance(refund, dict):
                raise ValueError("refund entity is required")
            refund_id = refund.get("id")
            if (
                refund.get("entity") != "refund"
                or not isinstance(refund_id, str)
                or not refund_id.startswith("rfnd_")
                or refund.get("payment_id") != callback.razorpay_payment_id
                or _positive_int(refund.get("amount")) != transaction.amount_minor
                or refund.get("currency") not in {"", transaction.currency}
                or refund.get("status") != "processed"
            ):
                raise ValueError("refund webhook binding is invalid")

        return RazorpayWebhookRecord.create(
            event_id=event_id,
            event_type=event_type,
            received_at_utc=received_at,
            raw_body_sha256=raw_body_sha256,
            transaction_id=transaction.transaction_id,
            transaction_digest=transaction.digest(),
            order_id=self.operation.handoff.order.order_id,
            payment_id=callback.razorpay_payment_id,
            refund_id=refund_id,
            amount_minor=transaction.amount_minor,
            currency=transaction.currency,
        )


def _positive_int(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("positive integer required")
    return value


def _valid_event_key(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )

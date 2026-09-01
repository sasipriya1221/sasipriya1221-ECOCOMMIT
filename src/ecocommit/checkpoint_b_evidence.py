from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ._canonical import sha256_hex


def _utc(value: datetime, field_name: str) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be expressed in UTC")
    return value


class RazorpayTestLifecycleEvidence(BaseModel):
    """Complete provider facts required before a Test Mode B receipt can exist."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: str = Field(pattern=r"^order_[A-Za-z0-9]+$")
    payment_id: str = Field(pattern=r"^pay_[A-Za-z0-9]+$")
    refund_id: str = Field(pattern=r"^rfnd_[A-Za-z0-9]+$")
    amount_minor: int = Field(gt=0)
    captured_amount_minor: int = Field(gt=0)
    refunded_amount_minor: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    checkout_signature_verified: Literal[True] = True
    order_binding_verified: Literal[True] = True
    authorization_verified: Literal[True] = True
    capture_verified: Literal[True] = True
    compensation_completed: Literal[True] = True
    refund_processed: Literal[True] = True
    webhook_signature_verified: Literal[True] = True
    webhook_capture_observed: Literal[True] = True
    webhook_refund_observed: Literal[True] = True
    reconciliation_verified: Literal[True] = True
    idempotency_replay_verified: Literal[True] = True
    cross_process_replay_verified: Literal[True] = True
    webhook_event_ids: tuple[str, ...] = Field(min_length=2)
    checkout_lifecycle_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    webhook_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    durability_test_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    state_store_backend: Literal[
        "SQLITE_WAL_FULL_SYNC",
        "EXTERNAL_DURABLE_STORE",
    ]
    audit_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def lifecycle_is_complete(self):
        if self.captured_amount_minor != self.amount_minor:
            raise ValueError("captured amount must equal the bound transaction amount")
        if self.refunded_amount_minor != self.amount_minor:
            raise ValueError("processed refund must compensate the full captured amount")
        if len(set(self.webhook_event_ids)) != len(self.webhook_event_ids):
            raise ValueError("webhook event ids must be unique")
        if any(
            not item.strip()
            or len(item) > 256
            or any(ord(character) < 33 or ord(character) > 126 for character in item)
            for item in self.webhook_event_ids
        ):
            raise ValueError("webhook event ids must be visible ASCII and at most 256 bytes")
        return self


class CheckpointBEvidenceReceipt(BaseModel):
    """Digest-bound proof shape for a complete Checkpoint B Test Mode gate.

    Constructing this model is not authority by itself. Runtime consumers must
    also verify the receipt file against an out-of-band trusted SHA-256 pin.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["B.RECEIPT.1"] = "B.RECEIPT.1"
    verification_mode: Literal["RAZORPAY_TEST_LIFECYCLE"] = (
        "RAZORPAY_TEST_LIFECYCLE"
    )
    evidence_reference: str = Field(min_length=1)
    generated_at_utc: datetime
    source_revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    checkpoint_a_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    deterministic_safety_suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    deterministic_safety_suite_passed: Literal[True] = True
    certificate_key_boundary_verified: Literal[True] = True
    certificate_key_reference_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_evidence_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_test_mode: Literal[True] = True
    real_money_moved: Literal[False] = False
    lifecycle: RazorpayTestLifecycleEvidence
    gate_passed: Literal[True] = True
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("generated_at_utc")
    @classmethod
    def generated_in_utc(cls, value: datetime):
        return _utc(value, "generated_at_utc")

    @model_validator(mode="after")
    def digest_is_valid(self):
        expected = sha256_hex(self.model_dump(exclude={"receipt_sha256"}))
        if self.receipt_sha256 != expected:
            raise ValueError("Checkpoint B receipt digest is invalid")
        return self

    @classmethod
    def create(cls, **values) -> "CheckpointBEvidenceReceipt":
        body = {
            "schema_version": "B.RECEIPT.1",
            "verification_mode": "RAZORPAY_TEST_LIFECYCLE",
            "deterministic_safety_suite_passed": True,
            "certificate_key_boundary_verified": True,
            "provider_test_mode": True,
            "real_money_moved": False,
            "gate_passed": True,
            **values,
        }
        return cls(**body, receipt_sha256=sha256_hex(body))

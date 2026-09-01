from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ._canonical import canonical_bytes, sha256_hex
from .evidence import EvidenceRegistry, EvidenceSnapshot
from .exposure import ExposureCalculator, ExposureDecision, ExposurePolicy, TransactionBinding


class CertificateError(ValueError):
    pass


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


class CommitCertificate(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["B.1"] = "B.1"
    certificate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    key_id: str = Field(min_length=1)
    issued_at: datetime
    expires_at: datetime
    authorized_stage: Literal["CAPTURE_ALLOWED"] = "CAPTURE_ALLOWED"
    transaction: TransactionBinding
    evidence_snapshot: EvidenceSnapshot
    exposure_decision: ExposureDecision
    nonce: str = Field(min_length=32)
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def aware_datetimes(cls, value: datetime, info):
        return _aware(value, info.field_name)

    @model_validator(mode="after")
    def valid_window(self):
        if self.expires_at <= self.issued_at:
            raise ValueError("certificate expiry must be after issue time")
        return self

    def payload_without_signature(self) -> dict:
        return self.model_dump(mode="python", exclude={"signature"})

    def id_source_payload(self) -> dict:
        return self.model_dump(mode="python", exclude={"certificate_id", "signature"})


class VerifiedCommitCertificate(BaseModel):
    """Result token returned only after full certificate and TOCTOU verification."""

    model_config = ConfigDict(frozen=True)

    certificate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    verified_at: datetime
    expires_at: datetime
    authorized_stage: Literal["CAPTURE_ALLOWED"] = "CAPTURE_ALLOWED"

    @field_validator("verified_at", "expires_at")
    @classmethod
    def aware_datetimes(cls, value: datetime, info):
        return _aware(value, info.field_name)


class CertificateSigner:
    """HMAC signer for local B scaffolding; production keys must live in a KMS."""

    def __init__(
        self,
        *,
        key_id: str,
        secret: bytes,
        trusted_policy: ExposurePolicy,
        max_ttl_seconds: int = 300,
        max_decision_age_seconds: int = 30,
    ):
        if not key_id:
            raise ValueError("key_id is required")
        if len(secret) < 32:
            raise ValueError("certificate signing secret must contain at least 32 bytes")
        if max_ttl_seconds <= 0 or max_decision_age_seconds < 0:
            raise ValueError("certificate time bounds are invalid")
        self.key_id = key_id
        self._secret = bytes(secret)
        # Take a private immutable copy: issuance authority is configured here,
        # never supplied through an individual certificate request.
        self._exposure_calculator = ExposureCalculator(trusted_policy.model_copy(deep=True))
        self.max_ttl_seconds = max_ttl_seconds
        self.max_decision_age_seconds = max_decision_age_seconds

    def issue(
        self,
        *,
        transaction: TransactionBinding,
        snapshot: EvidenceSnapshot,
        decision: ExposureDecision,
        registry: EvidenceRegistry,
        now: datetime,
        ttl_seconds: int = 60,
        nonce: str | None = None,
    ) -> CommitCertificate:
        now = _aware(now, "now")
        if ttl_seconds <= 0 or ttl_seconds > self.max_ttl_seconds:
            raise CertificateError("requested certificate TTL exceeds configured bounds")
        if not decision.allowed:
            raise CertificateError("a denied exposure decision cannot authorize capture")
        if decision.transaction_digest != transaction.digest():
            raise CertificateError("exposure decision is bound to a different transaction")
        if decision.evidence_snapshot_digest != snapshot.digest():
            raise CertificateError("exposure decision is bound to different evidence")
        if decision.requested_amount_minor != transaction.amount_minor or decision.currency != transaction.currency:
            raise CertificateError("exposure decision amount or currency does not match transaction")
        if decision.max_irreversible_minor < transaction.amount_minor:
            raise CertificateError("transaction exceeds exposure decision")
        if decision.evaluated_at > now:
            raise CertificateError("exposure decision cannot be from the future")
        if now - decision.evaluated_at > timedelta(seconds=self.max_decision_age_seconds):
            raise CertificateError("exposure decision is too old")

        registry.assert_snapshot_current(snapshot, now=now)
        trusted_decision = self._exposure_calculator.calculate(
            transaction,
            snapshot,
            now=decision.evaluated_at,
        )
        if decision != trusted_decision:
            raise CertificateError("exposure decision does not match the signer's trusted policy")
        expires_at = min(now + timedelta(seconds=ttl_seconds), snapshot.expires_at)
        if expires_at <= now:
            raise CertificateError("evidence expires before a certificate can be issued")

        body = {
            "schema_version": "B.1",
            "key_id": self.key_id,
            "issued_at": now,
            "expires_at": expires_at,
            "authorized_stage": "CAPTURE_ALLOWED",
            "transaction": transaction,
            "evidence_snapshot": snapshot,
            "exposure_decision": decision,
            "nonce": nonce or secrets.token_hex(16),
        }
        certificate_id = sha256_hex(body)
        unsigned = {**body, "certificate_id": certificate_id}
        signature = hmac.new(self._secret, canonical_bytes(unsigned), sha256).hexdigest()
        return CommitCertificate(**unsigned, signature=signature)


class CertificateVerifier:
    def __init__(self, keys: Mapping[str, bytes], *, future_skew_seconds: int = 5):
        if future_skew_seconds < 0:
            raise ValueError("future_skew_seconds cannot be negative")
        self._keys = {key_id: bytes(secret) for key_id, secret in keys.items()}
        if any(not key_id or len(secret) < 32 for key_id, secret in self._keys.items()):
            raise ValueError("all verification keys need an id and at least 32 bytes")
        self.future_skew_seconds = future_skew_seconds

    def verify(
        self,
        certificate: CommitCertificate,
        *,
        expected_transaction: TransactionBinding,
        expected_contract_hash: str,
        registry: EvidenceRegistry,
        now: datetime,
    ) -> VerifiedCommitCertificate:
        now = _aware(now, "now")
        secret = self._keys.get(certificate.key_id)
        if secret is None:
            raise CertificateError("certificate key id is not trusted")

        expected_id = sha256_hex(certificate.id_source_payload())
        if not hmac.compare_digest(certificate.certificate_id, expected_id):
            raise CertificateError("certificate id does not match its payload")
        expected_signature = hmac.new(
            secret,
            canonical_bytes(certificate.payload_without_signature()),
            sha256,
        ).hexdigest()
        if not hmac.compare_digest(certificate.signature, expected_signature):
            raise CertificateError("certificate signature is invalid")

        if certificate.issued_at > now + timedelta(seconds=self.future_skew_seconds):
            raise CertificateError("certificate was issued in the future")
        if now >= certificate.expires_at:
            raise CertificateError("certificate is expired")
        if certificate.expires_at > certificate.evidence_snapshot.expires_at:
            raise CertificateError("certificate outlives its evidence")
        if certificate.transaction != expected_transaction:
            raise CertificateError("certificate transaction binding does not match")
        if certificate.transaction.contract_hash != expected_contract_hash:
            raise CertificateError("certificate contract hash does not match")

        decision = certificate.exposure_decision
        if not decision.allowed or decision.max_irreversible_minor < expected_transaction.amount_minor:
            raise CertificateError("certificate does not contain sufficient exposure authority")
        if decision.transaction_digest != expected_transaction.digest():
            raise CertificateError("exposure decision transaction binding does not match")
        if decision.evidence_snapshot_digest != certificate.evidence_snapshot.digest():
            raise CertificateError("exposure decision evidence binding does not match")
        if decision.evaluated_at > certificate.issued_at:
            raise CertificateError("certificate predates its exposure decision")

        # This catches revocation, expiry, content changes, and superseding versions
        # after issuance instead of trusting the certificate's historical snapshot.
        registry.assert_snapshot_current(certificate.evidence_snapshot, now=now)
        return VerifiedCommitCertificate(
            certificate_id=certificate.certificate_id,
            transaction_digest=expected_transaction.digest(),
            verified_at=now,
            expires_at=certificate.expires_at,
        )

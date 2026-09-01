from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from enum import Enum
from threading import RLock
from typing import Iterable, Iterator

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from ._canonical import sha256_hex


class EvidenceError(ValueError):
    pass


class EvidenceAuthorityError(EvidenceError):
    pass


class EvidenceFreshnessError(EvidenceError):
    pass


class EvidenceVersionError(EvidenceError):
    pass


class EvidenceSnapshotError(EvidenceError):
    pass


class EvidenceKind(str, Enum):
    PRICE_QUOTE = "PRICE_QUOTE"
    INVENTORY_ATTESTATION = "INVENTORY_ATTESTATION"
    COUNTERPARTY_VERIFICATION = "COUNTERPARTY_VERIFICATION"
    CERTIFICATION = "CERTIFICATION"
    USER_AUTHORIZATION = "USER_AUTHORIZATION"
    PAYMENT_RESERVATION = "PAYMENT_RESERVATION"


def _require_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


class EvidenceAuthority(BaseModel):
    model_config = ConfigDict(frozen=True)

    authority_id: str = Field(min_length=1)
    issuer: str = Field(min_length=1)
    permitted_kinds: frozenset[EvidenceKind] = Field(min_length=1)
    max_age_seconds: int = Field(gt=0)
    future_skew_seconds: int = Field(default=30, ge=0, le=300)


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str = Field(min_length=1)
    authority_id: str = Field(min_length=1)
    issuer: str = Field(min_length=1)
    kind: EvidenceKind
    subject: str = Field(min_length=1)
    version: int = Field(ge=1)
    observed_at: datetime
    expires_at: datetime | None = None
    claims: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("observed_at", "expires_at")
    @classmethod
    def aware_datetimes(cls, value: datetime | None, info):
        if value is None:
            return value
        return _require_aware(value, info.field_name)

    @model_validator(mode="after")
    def expiry_after_observation(self):
        if self.expires_at is not None and self.expires_at <= self.observed_at:
            raise ValueError("expires_at must be later than observed_at")
        return self

    def digest(self) -> str:
        return sha256_hex(self)


class EvidenceClaimBinding(BaseModel):
    """Immutable digest of one authoritative claim value.

    Exposure policy compares these digests with exact values from trusted system
    configuration. Raw evidence payloads therefore cannot inject policy rules or
    monetary caps.
    """

    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1)
    value_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class EvidenceBinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str
    authority_id: str
    kind: EvidenceKind
    subject: str
    version: int = Field(ge=1)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime
    effective_expires_at: datetime
    claims: tuple[EvidenceClaimBinding, ...] = ()

    @field_validator("observed_at", "effective_expires_at")
    @classmethod
    def aware_datetimes(cls, value: datetime, info):
        return _require_aware(value, info.field_name)

    @model_validator(mode="after")
    def claims_are_unique_and_sorted(self):
        keys = [claim.key for claim in self.claims]
        if len(keys) != len(set(keys)):
            raise ValueError("evidence claim bindings must have unique keys")
        if keys != sorted(keys):
            raise ValueError("evidence claim bindings must be sorted by key")
        return self


class EvidenceSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    subject: str = Field(min_length=1)
    bindings: tuple[EvidenceBinding, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def consistent_and_unique(self):
        ids = [binding.evidence_id for binding in self.bindings]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence snapshot contains duplicate evidence ids")
        if any(binding.subject != self.subject for binding in self.bindings):
            raise ValueError("all evidence bindings must match the snapshot subject")
        if tuple(sorted(ids)) != tuple(ids):
            raise ValueError("evidence bindings must be sorted by evidence id")
        return self

    def digest(self) -> str:
        return sha256_hex(self)

    @property
    def expires_at(self) -> datetime:
        return min(binding.effective_expires_at for binding in self.bindings)


class EvidenceRegistry:
    """In-memory authority and latest-version registry for deterministic tests.

    Production persistence can implement the same checks. This registry never
    interprets free-form claims as monetary authority.
    """

    def __init__(self, authorities: Iterable[EvidenceAuthority]):
        authority_list = tuple(authorities)
        ids = [authority.authority_id for authority in authority_list]
        if len(ids) != len(set(ids)):
            raise EvidenceAuthorityError("authority ids must be unique")
        self._authorities = {authority.authority_id: authority for authority in authority_list}
        self._latest: dict[str, EvidenceRecord] = {}
        self._revoked: set[tuple[str, int]] = set()
        self._lock = RLock()

    def register(self, record: EvidenceRecord, *, now: datetime) -> EvidenceRecord:
        now = _require_aware(now, "now")
        with self._lock:
            authority = self._authorities.get(record.authority_id)
            if authority is None:
                raise EvidenceAuthorityError(f"unknown evidence authority: {record.authority_id}")
            if record.issuer != authority.issuer:
                raise EvidenceAuthorityError("record issuer does not match configured authority")
            if record.kind not in authority.permitted_kinds:
                raise EvidenceAuthorityError("authority is not permitted to issue this evidence kind")
            self._assert_fresh(record, authority, now)

            # Keep a private deep copy so mutable nested JSON claims cannot alter
            # a registered version without a new monotonic version number.
            stored = record.model_copy(deep=True)
            prior = self._latest.get(stored.evidence_id)
            if prior is not None:
                prior_identity = (
                    prior.authority_id,
                    prior.issuer,
                    prior.kind,
                    prior.subject,
                )
                stored_identity = (
                    stored.authority_id,
                    stored.issuer,
                    stored.kind,
                    stored.subject,
                )
                if stored_identity != prior_identity:
                    raise EvidenceVersionError(
                        "evidence identity metadata cannot change across versions"
                    )
                if stored.version < prior.version:
                    raise EvidenceVersionError("evidence version replayed below the latest version")
                if stored.version == prior.version:
                    if stored.digest() == prior.digest():
                        return prior.model_copy(deep=True)
                    raise EvidenceVersionError("same evidence version has conflicting content")
                if stored.observed_at < prior.observed_at:
                    raise EvidenceVersionError(
                        "evidence observation time cannot move backwards across versions"
                    )
            self._latest[stored.evidence_id] = stored
            return stored.model_copy(deep=True)

    def revoke(self, evidence_id: str, version: int) -> None:
        with self._lock:
            current = self._latest.get(evidence_id)
            if current is None or current.version != version:
                raise EvidenceVersionError("only the current evidence version can be revoked")
            self._revoked.add((evidence_id, version))

    def get_fresh(self, evidence_id: str, *, now: datetime) -> EvidenceRecord:
        now = _require_aware(now, "now")
        with self._lock:
            record = self._latest.get(evidence_id)
            if record is None:
                raise EvidenceSnapshotError(f"unknown evidence id: {evidence_id}")
            if (record.evidence_id, record.version) in self._revoked:
                raise EvidenceSnapshotError("evidence version has been revoked")
            authority = self._authorities[record.authority_id]
            self._assert_fresh(record, authority, now)
            return record.model_copy(deep=True)

    def snapshot(
        self,
        evidence_ids: Iterable[str],
        *,
        subject: str,
        now: datetime,
    ) -> EvidenceSnapshot:
        ids = tuple(evidence_ids)
        if not ids:
            raise EvidenceSnapshotError("at least one evidence id is required")
        if len(ids) != len(set(ids)):
            raise EvidenceSnapshotError("evidence ids must be unique")

        bindings: list[EvidenceBinding] = []
        for evidence_id in sorted(ids):
            record = self.get_fresh(evidence_id, now=now)
            if record.subject != subject:
                raise EvidenceSnapshotError("evidence is not bound to the requested subject")
            authority = self._authorities[record.authority_id]
            bindings.append(
                EvidenceBinding(
                    evidence_id=record.evidence_id,
                    authority_id=record.authority_id,
                    kind=record.kind,
                    subject=record.subject,
                    version=record.version,
                    digest=record.digest(),
                    observed_at=record.observed_at,
                    effective_expires_at=self._effective_expiry(record, authority),
                    claims=self._claim_bindings(record),
                )
            )
        return EvidenceSnapshot(subject=subject, bindings=tuple(bindings))

    def assert_snapshot_current(self, snapshot: EvidenceSnapshot, *, now: datetime) -> None:
        now = _require_aware(now, "now")
        for binding in snapshot.bindings:
            current = self.get_fresh(binding.evidence_id, now=now)
            authority = self._authorities[current.authority_id]
            if current.subject != snapshot.subject:
                raise EvidenceSnapshotError("evidence subject changed")
            if (
                current.version != binding.version
                or current.digest() != binding.digest
                or current.authority_id != binding.authority_id
                or current.kind != binding.kind
                or current.observed_at != binding.observed_at
                or self._effective_expiry(current, authority) != binding.effective_expires_at
                or self._claim_bindings(current) != binding.claims
            ):
                raise EvidenceSnapshotError("evidence snapshot is no longer current")

    @contextmanager
    def hold_snapshot_current(
        self,
        snapshot: EvidenceSnapshot,
        *,
        now: datetime,
    ) -> Iterator[None]:
        """Hold the registry version lock across an irreversible local boundary.

        A normal verification proves freshness at an instant. Capture additionally
        needs to prevent a concurrent revoke or superseding version from landing
        between that check and the side effect. The simulator uses this guard for
        that small critical section.
        """

        now = _require_aware(now, "now")
        with self._lock:
            self.assert_snapshot_current(snapshot, now=now)
            yield

    @staticmethod
    def _claim_bindings(record: EvidenceRecord) -> tuple[EvidenceClaimBinding, ...]:
        return tuple(
            EvidenceClaimBinding(key=key, value_digest=sha256_hex(record.claims[key]))
            for key in sorted(record.claims)
        )

    @staticmethod
    def _effective_expiry(record: EvidenceRecord, authority: EvidenceAuthority) -> datetime:
        authority_expiry = record.observed_at + timedelta(seconds=authority.max_age_seconds)
        return min(authority_expiry, record.expires_at) if record.expires_at else authority_expiry

    def _assert_fresh(
        self,
        record: EvidenceRecord,
        authority: EvidenceAuthority,
        now: datetime,
    ) -> None:
        if record.observed_at > now + timedelta(seconds=authority.future_skew_seconds):
            raise EvidenceFreshnessError("evidence observation is too far in the future")
        if now >= self._effective_expiry(record, authority):
            raise EvidenceFreshnessError("evidence is stale or expired")

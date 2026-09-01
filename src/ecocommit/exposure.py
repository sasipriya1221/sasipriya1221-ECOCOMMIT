from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from ._canonical import sha256_hex
from .evidence import EvidenceKind, EvidenceSnapshot


class ExposurePolicyError(ValueError):
    pass


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


class TransactionBinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    transaction_id: str = Field(min_length=1)
    merchant_id: str = Field(min_length=1)
    amount_minor: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    def digest(self) -> str:
        return sha256_hex(self)


class EvidenceClaimRequirement(BaseModel):
    """Exact authoritative claim value required by trusted exposure policy."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1)
    expected_value: JsonValue

    @field_validator("expected_value")
    @classmethod
    def finite_json_value(cls, value: JsonValue):
        if isinstance(value, (dict, list)):
            raise ValueError("evidence claim expectations must be immutable JSON scalars")
        # Canonicalization rejects NaN/Infinity.
        sha256_hex(value)
        return value

    @property
    def expected_digest(self) -> str:
        return sha256_hex(self.expected_value)


class EvidenceRequirement(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: EvidenceKind
    authority_ids: frozenset[str] = Field(min_length=1)
    claims: tuple[EvidenceClaimRequirement, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_claim_keys(self):
        keys = [claim.key for claim in self.claims]
        if len(keys) != len(set(keys)):
            raise ValueError("an evidence requirement may contain each claim key only once")
        return self


class ExposureTier(BaseModel):
    model_config = ConfigDict(frozen=True)

    tier_id: str = Field(min_length=1)
    requirements: tuple[EvidenceRequirement, ...] = Field(min_length=1)
    max_irreversible_minor: int = Field(ge=0)

    @model_validator(mode="after")
    def unique_requirement_kinds(self):
        kinds = [requirement.kind for requirement in self.requirements]
        if len(kinds) != len(set(kinds)):
            raise ValueError("a tier may contain only one requirement per evidence kind")
        return self


class ExposurePolicy(BaseModel):
    """Trusted, versioned configuration; never constructed from contract text."""

    model_config = ConfigDict(frozen=True)

    source: Literal["TRUSTED_SYSTEM_CONFIG"] = "TRUSTED_SYSTEM_CONFIG"
    policy_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    tiers: tuple[ExposureTier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_tiers(self):
        tier_ids = [tier.tier_id for tier in self.tiers]
        if len(tier_ids) != len(set(tier_ids)):
            raise ValueError("exposure tier ids must be unique")
        return self

    def digest(self) -> str:
        return sha256_hex(self)


class ExposureReason(str, Enum):
    ALLOWED = "ALLOWED"
    NO_SATISFIED_TIER = "NO_SATISFIED_TIER"
    EXCEEDS_POLICY_CAP = "EXCEEDS_POLICY_CAP"
    CURRENCY_NOT_PERMITTED = "CURRENCY_NOT_PERMITTED"
    EVIDENCE_SUBJECT_MISMATCH = "EVIDENCE_SUBJECT_MISMATCH"
    EVIDENCE_EXPIRED = "EVIDENCE_EXPIRED"


class ExposureDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_id: str
    policy_version: int
    policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_amount_minor: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    max_irreversible_minor: int = Field(ge=0)
    satisfied_tier_id: str | None = None
    allowed: bool
    reason: ExposureReason
    evaluated_at: datetime
    decision_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("evaluated_at")
    @classmethod
    def aware_evaluated_at(cls, value: datetime):
        return _aware(value, "evaluated_at")

    @model_validator(mode="after")
    def internally_consistent(self):
        should_allow = self.requested_amount_minor <= self.max_irreversible_minor
        if self.allowed != should_allow:
            raise ValueError("allowed flag is inconsistent with the deterministic cap")
        if self.allowed != (self.reason == ExposureReason.ALLOWED):
            raise ValueError("allowed decision must use reason ALLOWED and vice versa")
        expected = sha256_hex(self.model_dump(exclude={"decision_hash"}))
        if self.decision_hash != expected:
            raise ValueError("exposure decision hash is invalid")
        return self

    @classmethod
    def create(cls, **values) -> "ExposureDecision":
        decision_hash = sha256_hex(values)
        return cls(**values, decision_hash=decision_hash)


class ExposureCalculator:
    """Calculates authority exclusively from trusted policy caps and metadata.

    Evidence claims and contract-normalized values are intentionally absent from
    this API, so neither can inject a monetary ceiling.
    """

    def __init__(self, policy: ExposurePolicy):
        # Do not retain mutable nested values from the caller's configuration.
        self.policy = policy.model_copy(deep=True)

    def calculate(
        self,
        transaction: TransactionBinding,
        snapshot: EvidenceSnapshot,
        *,
        now: datetime,
    ) -> ExposureDecision:
        now = _aware(now, "now")
        tier: ExposureTier | None = None
        reason: ExposureReason

        if transaction.currency != self.policy.currency:
            reason = ExposureReason.CURRENCY_NOT_PERMITTED
        elif snapshot.subject != transaction.transaction_id:
            reason = ExposureReason.EVIDENCE_SUBJECT_MISMATCH
        elif now >= snapshot.expires_at:
            reason = ExposureReason.EVIDENCE_EXPIRED
        else:
            satisfied = [candidate for candidate in self.policy.tiers if self._satisfied(candidate, snapshot)]
            if satisfied:
                tier = max(satisfied, key=lambda candidate: (candidate.max_irreversible_minor, candidate.tier_id))
                reason = (
                    ExposureReason.ALLOWED
                    if transaction.amount_minor <= tier.max_irreversible_minor
                    else ExposureReason.EXCEEDS_POLICY_CAP
                )
            else:
                reason = ExposureReason.NO_SATISFIED_TIER

        cap = tier.max_irreversible_minor if tier is not None else 0
        return ExposureDecision.create(
            policy_id=self.policy.policy_id,
            policy_version=self.policy.version,
            policy_digest=self.policy.digest(),
            transaction_digest=transaction.digest(),
            evidence_snapshot_digest=snapshot.digest(),
            requested_amount_minor=transaction.amount_minor,
            currency=transaction.currency,
            max_irreversible_minor=cap,
            satisfied_tier_id=tier.tier_id if tier else None,
            allowed=transaction.amount_minor <= cap,
            reason=reason,
            evaluated_at=now,
        )

    @staticmethod
    def _satisfied(tier: ExposureTier, snapshot: EvidenceSnapshot) -> bool:
        return all(
            any(
                binding.kind == requirement.kind
                and binding.authority_id in requirement.authority_ids
                and all(
                    any(
                        claim.key == expected.key
                        and claim.value_digest == expected.expected_digest
                        for claim in binding.claims
                    )
                    for expected in requirement.claims
                )
                for binding in snapshot.bindings
            )
            for requirement in tier.requirements
        )

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ._canonical import sha256_hex
from .checkpoint_a_evidence import CheckpointAEvidenceReceipt
from .checkpoint_b_evidence import CheckpointBEvidenceReceipt
from .checkpoint_c_final import (
    MAX_FINAL_INPUT_BYTES,
    CheckpointCFinalHeldOutEvidence,
)
from .checkpoint_status import (
    ExecutionMode,
    GateReport,
    GateState,
    ProviderStatus,
    SafetyStatus,
)


MAX_EVIDENCE_FILE_BYTES = 2 * 1024 * 1024
EXPECTED_EVIDENCE_REPOSITORY = "sasipriya1221/sasipriya1221-ECOCOMMIT"


class AuthoritativeEvidenceError(ValueError):
    pass


def _utc(value: datetime, field_name: str) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be expressed in UTC")
    return value


class EvidenceFilePin(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    filename: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,126}\.json$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CheckpointDIntegrationReceipt(BaseModel):
    """Proof shape for a completed hosted Test Mode D integration boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["D.INTEGRATION.RECEIPT.1"] = (
        "D.INTEGRATION.RECEIPT.1"
    )
    generated_at_utc: datetime
    source_revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    checkpoint_a_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_b_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_c_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    hosted_base_url: str = Field(min_length=1)
    hosted_tls_verified: Literal[True] = True
    api_authentication_verified: Literal[True] = True
    api_authorization_verified: Literal[True] = True
    rate_limit_verified: Literal[True] = True
    durable_state_backend: Literal[
        "SQLITE_WAL_FULL_SYNC_SINGLE_HOST",
        "EXTERNAL_DURABLE_STORE",
    ]
    audit_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    audit_entries: int = Field(gt=0)
    audit_tamper_test_passed: Literal[True] = True
    end_to_end_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    operational_test_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_test_mode_only: Literal[True] = True
    real_money_disabled: Literal[True] = True
    final_integration_passed: Literal[True] = True
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("generated_at_utc")
    @classmethod
    def generated_in_utc(cls, value: datetime):
        return _utc(value, "generated_at_utc")

    @field_validator("hosted_base_url")
    @classmethod
    def hosted_url_is_safe_https(cls, value: str):
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("hosted_base_url must be a credential-free HTTPS origin")
        return value.rstrip("/")

    @model_validator(mode="after")
    def digest_is_valid(self):
        expected = sha256_hex(self.model_dump(exclude={"receipt_sha256"}))
        if self.receipt_sha256 != expected:
            raise ValueError("Checkpoint D integration receipt digest is invalid")
        return self

    @classmethod
    def create(cls, **values) -> "CheckpointDIntegrationReceipt":
        body = {
            "schema_version": "D.INTEGRATION.RECEIPT.1",
            "hosted_tls_verified": True,
            "api_authentication_verified": True,
            "api_authorization_verified": True,
            "rate_limit_verified": True,
            "audit_tamper_test_passed": True,
            "provider_test_mode_only": True,
            "real_money_disabled": True,
            "final_integration_passed": True,
            **values,
        }
        return cls(**body, receipt_sha256=sha256_hex(body))


class AuthoritativeEvidencePins(BaseModel):
    """Operator-trusted pin set; its file hash must be supplied out-of-band."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["D.EVIDENCE.PINS.2"]
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    integrated_revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    checkpoint_a: EvidenceFilePin
    checkpoint_b: EvidenceFilePin
    checkpoint_c: EvidenceFilePin
    checkpoint_c_schema_version: Literal["C.FINAL.HELD_OUT.EVIDENCE.1"]
    checkpoint_d: EvidenceFilePin | None = None
    pin_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def pins_are_unique_and_digest_is_valid(self):
        pins = [self.checkpoint_a, self.checkpoint_b, self.checkpoint_c]
        if self.checkpoint_d is not None:
            pins.append(self.checkpoint_d)
        filenames = [item.filename for item in pins]
        if len(filenames) != len(set(filenames)):
            raise ValueError("evidence pin filenames must be unique")
        expected = sha256_hex(self.model_dump(exclude={"pin_set_sha256"}))
        if self.pin_set_sha256 != expected:
            raise ValueError("authoritative evidence pin-set digest is invalid")
        return self

    @classmethod
    def create(cls, **values) -> "AuthoritativeEvidencePins":
        body = {
            "schema_version": "D.EVIDENCE.PINS.2",
            "checkpoint_c_schema_version": "C.FINAL.HELD_OUT.EVIDENCE.1",
            **values,
        }
        return cls(**body, pin_set_sha256=sha256_hex(body))


class LoadedAuthoritativeEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    pins: AuthoritativeEvidencePins
    checkpoint_a: CheckpointAEvidenceReceipt
    checkpoint_b: CheckpointBEvidenceReceipt
    checkpoint_c: CheckpointCFinalHeldOutEvidence
    checkpoint_d: CheckpointDIntegrationReceipt | None = None
    file_sha256: Mapping[str, str]

    @model_validator(mode="after")
    def file_hashes_are_immutable_and_complete(self):
        expected_keys = {"A", "B", "C"}
        if self.checkpoint_d is not None:
            expected_keys.add("D")
        if set(self.file_sha256) != expected_keys:
            raise ValueError("loaded evidence file hash set is incomplete")
        if any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in self.file_sha256.values()
        ):
            raise ValueError("loaded evidence file hash is invalid")
        object.__setattr__(
            self,
            "file_sha256",
            MappingProxyType(dict(self.file_sha256)),
        )
        return self

    def safety_status(
        self,
        *,
        provider_credentials_verified: bool = False,
        provider_calls_enabled: bool = False,
    ) -> SafetyStatus:
        d_passed = self.checkpoint_d is not None
        gates = {
            "A": GateReport(
                "A",
                GateState.PASSED,
                evidence=f"sha256:{self.pins.checkpoint_a.sha256}",
                detail="FROZEN_AGGREGATE_RECEIPT_PIN_VERIFIED",
            ),
            "B": GateReport(
                "B",
                GateState.PASSED,
                evidence=f"sha256:{self.pins.checkpoint_b.sha256}",
                detail="RAZORPAY_TEST_LIFECYCLE_RECEIPT_PIN_VERIFIED",
            ),
            "C": GateReport(
                "C",
                GateState.PASSED,
                evidence=f"sha256:{self.pins.checkpoint_c.sha256}",
                detail="FINAL_HELD_OUT_RAW_ROW_EVIDENCE_PIN_VERIFIED",
            ),
            "D": GateReport(
                "D",
                GateState.PASSED if d_passed else GateState.BLOCKED,
                evidence=(
                    f"sha256:{self.pins.checkpoint_d.sha256}"
                    if self.pins.checkpoint_d is not None
                    else None
                ),
                detail=(
                    "HOSTED_INTEGRATION_RECEIPT_PIN_VERIFIED"
                    if d_passed
                    else "HOSTED_INTEGRATION_RECEIPT_NOT_SUPPLIED"
                ),
            ),
            "E": GateReport(
                "E",
                GateState.BLOCKED,
                detail="FINAL_SUBMISSION_EVIDENCE_NOT_LOADED_BY_RUNTIME",
            ),
        }
        return SafetyStatus(
            gates=gates,
            mode=ExecutionMode.REAL_PROVIDER_TEST,
            provider_status=ProviderStatus.RAZORPAY_TEST_MODE,
            provider_credentials_verified=provider_credentials_verified,
            provider_calls_enabled=provider_calls_enabled,
            final_integration_verified=d_passed,
        )


def _reject_constant(value: str):
    raise AuthoritativeEvidenceError(f"non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AuthoritativeEvidenceError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _decode_json(raw: bytes, *, label: str) -> dict[str, object]:
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuthoritativeEvidenceError(f"{label} is not UTF-8 JSON") from exc
    try:
        payload = json.loads(
            decoded,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise AuthoritativeEvidenceError(f"{label} is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise AuthoritativeEvidenceError(f"{label} must contain one JSON object")
    return payload


def _read_pinned(
    root: Path,
    pin: EvidenceFilePin,
    *,
    max_bytes: int = MAX_EVIDENCE_FILE_BYTES,
) -> tuple[dict[str, object], str]:
    candidate = root / pin.filename
    if candidate.is_symlink():
        raise AuthoritativeEvidenceError(f"symlinked evidence file is forbidden: {pin.filename}")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise AuthoritativeEvidenceError("evidence path escapes the configured root") from exc
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        raise AuthoritativeEvidenceError(f"evidence file is unavailable: {pin.filename}") from exc
    if not raw or len(raw) > max_bytes:
        raise AuthoritativeEvidenceError(f"evidence file size is invalid: {pin.filename}")
    digest = sha256(raw).hexdigest()
    if digest != pin.sha256:
        raise AuthoritativeEvidenceError(f"evidence file digest mismatch: {pin.filename}")
    return _decode_json(raw, label=pin.filename), digest


def load_authoritative_evidence(
    evidence_root: str | Path,
    pins_path: str | Path,
    *,
    expected_pins_file_sha256: str,
) -> LoadedAuthoritativeEvidence:
    """Load A/B/final-held-out-C[/D] through an out-of-band pin.

    Request data is never consulted. Every receipt is hashed before parsing and
    the semantic cross-links are revalidated after strict schema validation. A
    legacy aggregate-only C receipt is never authoritative at this boundary.
    """

    if len(expected_pins_file_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in expected_pins_file_sha256
    ):
        raise AuthoritativeEvidenceError("expected pin-set file SHA-256 is invalid")
    root = Path(evidence_root).resolve()
    if not root.is_dir():
        raise AuthoritativeEvidenceError("evidence root is not a directory")
    pins_file = Path(pins_path)
    if pins_file.is_symlink():
        raise AuthoritativeEvidenceError("symlinked pin-set file is forbidden")
    try:
        raw_pins = pins_file.resolve().read_bytes()
    except OSError as exc:
        raise AuthoritativeEvidenceError("pin-set file is unavailable") from exc
    if not raw_pins or len(raw_pins) > MAX_EVIDENCE_FILE_BYTES:
        raise AuthoritativeEvidenceError("pin-set file size is invalid")
    if sha256(raw_pins).hexdigest() != expected_pins_file_sha256:
        raise AuthoritativeEvidenceError("pin-set file digest mismatch")

    try:
        pins = AuthoritativeEvidencePins.model_validate(
            _decode_json(raw_pins, label="pin-set")
        )
    except AuthoritativeEvidenceError:
        raise
    except (TypeError, ValueError) as exc:
        raise AuthoritativeEvidenceError(
            "authoritative evidence pin-set schema validation failed"
        ) from exc
    if pins.repository != EXPECTED_EVIDENCE_REPOSITORY:
        raise AuthoritativeEvidenceError(
            "evidence pin set belongs to another repository"
        )

    try:
        a_payload, a_sha = _read_pinned(root, pins.checkpoint_a)
        b_payload, b_sha = _read_pinned(root, pins.checkpoint_b)
        checkpoint_a = CheckpointAEvidenceReceipt.model_validate(a_payload)
        checkpoint_b = CheckpointBEvidenceReceipt.model_validate(b_payload)
    except AuthoritativeEvidenceError:
        raise
    except (TypeError, ValueError) as exc:
        raise AuthoritativeEvidenceError(
            "authoritative A/B evidence schema validation failed"
        ) from exc
    if checkpoint_a.verification_mode != "FROZEN_AGGREGATE":
        raise AuthoritativeEvidenceError("Checkpoint A fixture evidence is forbidden")
    if checkpoint_a.source_revision != pins.integrated_revision:
        raise AuthoritativeEvidenceError("Checkpoint A source revision is not integrated")
    if checkpoint_b.source_revision != pins.integrated_revision:
        raise AuthoritativeEvidenceError("Checkpoint B source revision is not integrated")
    if checkpoint_b.checkpoint_a_receipt_sha256 != a_sha:
        raise AuthoritativeEvidenceError("Checkpoint B does not bind the pinned A receipt")

    try:
        c_payload, c_sha = _read_pinned(
            root,
            pins.checkpoint_c,
            max_bytes=MAX_FINAL_INPUT_BYTES,
        )
        c_schema = c_payload.get("schema_version")
        if c_schema == "C.FINAL.EVIDENCE.1":
            raise AuthoritativeEvidenceError(
                "legacy caller-metric Checkpoint C evidence is forbidden"
            )
        if c_schema != pins.checkpoint_c_schema_version:
            raise AuthoritativeEvidenceError(
                "Checkpoint C evidence is not the pinned final held-out schema"
            )
        checkpoint_c = CheckpointCFinalHeldOutEvidence.model_validate(c_payload)
    except AuthoritativeEvidenceError:
        raise
    except (TypeError, ValueError) as exc:
        raise AuthoritativeEvidenceError(
            "authoritative final held-out C evidence schema validation failed"
        ) from exc

    if checkpoint_c.source_revision != pins.integrated_revision:
        raise AuthoritativeEvidenceError("Checkpoint C source revision is not integrated")
    if (
        checkpoint_c.registration.upstream.integrated_candidate_revision
        != pins.integrated_revision
    ):
        raise AuthoritativeEvidenceError(
            "Checkpoint C registration source revision is not integrated"
        )
    if checkpoint_c.checkpoint_a_receipt_file_sha256 != a_sha:
        raise AuthoritativeEvidenceError("Checkpoint C does not bind the pinned A receipt")
    if checkpoint_c.checkpoint_b_receipt_file_sha256 != b_sha:
        raise AuthoritativeEvidenceError("Checkpoint C does not bind the pinned B receipt")
    if checkpoint_c.checkpoint_a_receipt != checkpoint_a:
        raise AuthoritativeEvidenceError(
            "Checkpoint C embeds a different Checkpoint A receipt"
        )
    if checkpoint_c.checkpoint_b_receipt != checkpoint_b:
        raise AuthoritativeEvidenceError(
            "Checkpoint C embeds a different Checkpoint B receipt"
        )
    if not checkpoint_c.decision.passed:
        raise AuthoritativeEvidenceError("Checkpoint C final decision did not pass")

    checkpoint_d = None
    file_hashes = {"A": a_sha, "B": b_sha, "C": c_sha}
    if pins.checkpoint_d is not None:
        try:
            d_payload, d_sha = _read_pinned(root, pins.checkpoint_d)
            checkpoint_d = CheckpointDIntegrationReceipt.model_validate(d_payload)
            file_hashes["D"] = d_sha
        except AuthoritativeEvidenceError:
            raise
        except (TypeError, ValueError) as exc:
            raise AuthoritativeEvidenceError(
                "authoritative D evidence schema validation failed"
            ) from exc
    if checkpoint_d is not None:
        if checkpoint_d.source_revision != pins.integrated_revision:
            raise AuthoritativeEvidenceError("Checkpoint D source revision is not integrated")
        if checkpoint_d.checkpoint_a_receipt_sha256 != a_sha:
            raise AuthoritativeEvidenceError("Checkpoint D does not bind the pinned A receipt")
        if checkpoint_d.checkpoint_b_receipt_sha256 != b_sha:
            raise AuthoritativeEvidenceError("Checkpoint D does not bind the pinned B receipt")
        if checkpoint_d.checkpoint_c_evidence_sha256 != c_sha:
            raise AuthoritativeEvidenceError("Checkpoint D does not bind the pinned C evidence")

    return LoadedAuthoritativeEvidence(
        pins=pins,
        checkpoint_a=checkpoint_a,
        checkpoint_b=checkpoint_b,
        checkpoint_c=checkpoint_c,
        checkpoint_d=checkpoint_d,
        file_sha256=file_hashes,
    )


@dataclass(frozen=True)
class AuthoritativeEvidenceStatusSource:
    """Reload the pinned bundle on every call so post-start tampering fails closed."""

    evidence_root: Path
    pins_path: Path
    expected_pins_file_sha256: str
    provider_credentials_verified: bool
    provider_calls_enabled: bool

    def __init__(
        self,
        evidence_root: str | Path,
        pins_path: str | Path,
        expected_pins_file_sha256: str,
        *,
        provider_credentials_verified: bool = False,
        provider_calls_enabled: bool = False,
    ) -> None:
        if provider_calls_enabled and not provider_credentials_verified:
            raise ValueError("provider calls require a completed credential preflight")
        object.__setattr__(self, "evidence_root", Path(evidence_root).resolve())
        # Preserve the configured path identity so each reload can still reject
        # a symlink instead of silently validating only its resolved target.
        object.__setattr__(self, "pins_path", Path(pins_path).absolute())
        object.__setattr__(
            self,
            "expected_pins_file_sha256",
            expected_pins_file_sha256,
        )
        object.__setattr__(
            self,
            "provider_credentials_verified",
            provider_credentials_verified,
        )
        object.__setattr__(self, "provider_calls_enabled", provider_calls_enabled)

    def __call__(self) -> SafetyStatus:
        return load_authoritative_evidence(
            self.evidence_root,
            self.pins_path,
            expected_pins_file_sha256=self.expected_pins_file_sha256,
        ).safety_status(
            provider_credentials_verified=self.provider_credentials_verified,
            provider_calls_enabled=self.provider_calls_enabled,
        )

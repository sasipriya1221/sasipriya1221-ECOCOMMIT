from __future__ import annotations

import hmac
import re
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._canonical import sha256_hex
from .exposure import TransactionBinding


_SOURCE_REVISION = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID = re.compile(r"^[0-9]{6,20}$")
_RUN_ATTEMPT = re.compile(r"^[0-9]{1,10}$")


class CertificateKeyBoundaryReference(BaseModel):
    """Non-secret proof that the certificate-key boundary existed before Checkout."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["B8.CERTIFICATE_KEY_REFERENCE.1"] = (
        "B8.CERTIFICATE_KEY_REFERENCE.1"
    )
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    boundary: Literal["ENVIRONMENT_ONLY_HMAC_TEST_BOUNDARY"] = (
        "ENVIRONMENT_ONLY_HMAC_TEST_BOUNDARY"
    )
    key_reference_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    minimum_secret_bytes: int = Field(default=32, ge=32, strict=True)
    retained_material_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def no_key_material_is_retained(self):
        if self.retained_material_fields:
            raise ValueError("certificate-key reference retains key material")
        return self


def b8_run_identity(run_id: str, run_attempt: str) -> str:
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("B8 GitHub run id is invalid")
    if not _RUN_ATTEMPT.fullmatch(run_attempt):
        raise ValueError("B8 GitHub run attempt is invalid")
    return f"{run_id}-{run_attempt}"


def b8_transaction_for_run(run_id: str, run_attempt: str) -> TransactionBinding:
    run_identity = b8_run_identity(run_id, run_attempt)
    return TransactionBinding(
        transaction_id=f"tx-b8-{run_identity}",
        merchant_id="razorpay-test-mode-boundary",
        amount_minor=100,
        currency="INR",
        contract_hash=sha256(
            f"ECOCOMMIT-B8-RAZORPAY-TEST:{run_identity}".encode("utf-8")
        ).hexdigest(),
    )


def _reference_digest(
    *,
    source_revision: str,
    run_id: str,
    run_attempt: str,
    transaction_digest: str,
) -> str:
    return sha256_hex(
        {
            "schema_version": "B8.CERTIFICATE_KEY_REFERENCE.1",
            "source_revision": source_revision,
            "boundary": "ENVIRONMENT_ONLY_HMAC_TEST_BOUNDARY",
            "github_run_id": run_id,
            "github_run_attempt": run_attempt,
            "transaction_digest": transaction_digest,
            "purpose": "B8_PRE_AUTHORIZATION_CERTIFICATE_KEY_BOUNDARY",
            "minimum_secret_bytes": 32,
            "retained_material_fields": [],
        }
    )


def create_certificate_key_boundary_reference(
    *,
    source_revision: str,
    run_id: str,
    run_attempt: str,
) -> CertificateKeyBoundaryReference:
    if not _SOURCE_REVISION.fullmatch(source_revision):
        raise ValueError("B8 source revision is invalid")
    transaction = b8_transaction_for_run(run_id, run_attempt)
    return CertificateKeyBoundaryReference(
        source_revision=source_revision,
        key_reference_sha256=_reference_digest(
            source_revision=source_revision,
            run_id=run_id,
            run_attempt=run_attempt,
            transaction_digest=transaction.digest(),
        ),
    )


def verify_certificate_key_boundary_reference(
    reference: CertificateKeyBoundaryReference,
    *,
    source_revision: str,
    run_id: str,
    run_attempt: str,
    transaction_digest: str,
) -> None:
    if not _SOURCE_REVISION.fullmatch(source_revision):
        raise ValueError("B8 source revision is invalid")
    if reference.source_revision != source_revision:
        raise ValueError("certificate-key reference belongs to another source revision")
    expected_transaction = b8_transaction_for_run(run_id, run_attempt)
    if expected_transaction.digest() != transaction_digest:
        raise ValueError("certificate-key reference transaction binding changed")
    expected = _reference_digest(
        source_revision=source_revision,
        run_id=run_id,
        run_attempt=run_attempt,
        transaction_digest=transaction_digest,
    )
    if not hmac.compare_digest(reference.key_reference_sha256, expected):
        raise ValueError("certificate-key reference digest is invalid")

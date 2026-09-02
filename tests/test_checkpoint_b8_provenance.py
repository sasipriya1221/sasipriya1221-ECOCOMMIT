from __future__ import annotations

import pytest

from ecocommit.b8_provenance import (
    CertificateKeyBoundaryReference,
    b8_transaction_for_run,
    create_certificate_key_boundary_reference,
    verify_certificate_key_boundary_reference,
)


SOURCE = "1" * 40
RUN_ID = "33645687964"
RUN_ATTEMPT = "1"


def test_certificate_key_reference_is_source_and_transaction_bound():
    transaction = b8_transaction_for_run(RUN_ID, RUN_ATTEMPT)
    reference = create_certificate_key_boundary_reference(
        source_revision=SOURCE,
        run_id=RUN_ID,
        run_attempt=RUN_ATTEMPT,
    )

    verify_certificate_key_boundary_reference(
        reference,
        source_revision=SOURCE,
        run_id=RUN_ID,
        run_attempt=RUN_ATTEMPT,
        transaction_digest=transaction.digest(),
    )
    assert reference.retained_material_fields == ()
    assert reference.minimum_secret_bytes == 32


def test_certificate_key_reference_rejects_source_rebinding():
    reference = create_certificate_key_boundary_reference(
        source_revision=SOURCE,
        run_id=RUN_ID,
        run_attempt=RUN_ATTEMPT,
    )
    transaction = b8_transaction_for_run(RUN_ID, RUN_ATTEMPT)

    with pytest.raises(ValueError, match="another source revision"):
        verify_certificate_key_boundary_reference(
            reference,
            source_revision="2" * 40,
            run_id=RUN_ID,
            run_attempt=RUN_ATTEMPT,
            transaction_digest=transaction.digest(),
        )


def test_certificate_key_reference_rejects_digest_tampering():
    reference = create_certificate_key_boundary_reference(
        source_revision=SOURCE,
        run_id=RUN_ID,
        run_attempt=RUN_ATTEMPT,
    )
    tampered = CertificateKeyBoundaryReference(
        **{
            **reference.model_dump(),
            "key_reference_sha256": "0" * 64,
        }
    )
    transaction = b8_transaction_for_run(RUN_ID, RUN_ATTEMPT)

    with pytest.raises(ValueError, match="digest is invalid"):
        verify_certificate_key_boundary_reference(
            tampered,
            source_revision=SOURCE,
            run_id=RUN_ID,
            run_attempt=RUN_ATTEMPT,
            transaction_digest=transaction.digest(),
        )

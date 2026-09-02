from __future__ import annotations

import argparse
import json
from pathlib import Path

from ecocommit.checkpoint_c_final import (
    build_final_held_out_evidence,
    load_checkpoint_c_upstream_receipts,
    load_final_decision_manifest,
    load_final_decision_receipt,
    load_final_metric_specification,
    load_final_registration,
    load_final_suite,
    write_final_held_out_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a Checkpoint C final-held-out artifact from an already frozen "
            "registration and complete raw candidate/comparator decision rows."
        )
    )
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument(
        "--expected-registration-sha256",
        required=True,
        help="Out-of-band SHA-256 digest recorded when the registration was frozen.",
    )
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--metric-specification", type=Path, required=True)
    parser.add_argument("--candidate-rows", type=Path, required=True)
    parser.add_argument("--comparator-rows", type=Path, required=True)
    parser.add_argument("--candidate-receipt", type=Path, required=True)
    parser.add_argument("--comparator-receipt", type=Path, required=True)
    parser.add_argument("--checkpoint-a-receipt", type=Path, required=True)
    parser.add_argument("--checkpoint-b-receipt", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    registration = load_final_registration(args.registration)
    if len(args.expected_registration_sha256) != 64 or any(
        character not in "0123456789abcdef"
        for character in args.expected_registration_sha256
    ):
        raise ValueError("out-of-band final registration digest pin is invalid")
    if args.expected_registration_sha256 != registration.registration_sha256:
        raise ValueError("final registration does not match the out-of-band digest pin")
    if args.execution_id != registration.final_execution_id:
        raise ValueError("final execution id does not match its preregistration")
    suite = load_final_suite(args.suite)
    metric_specification = load_final_metric_specification(args.metric_specification)
    candidate_manifest = load_final_decision_manifest(args.candidate_rows)
    comparator_manifest = load_final_decision_manifest(args.comparator_rows)
    candidate_receipt = load_final_decision_receipt(args.candidate_receipt)
    comparator_receipt = load_final_decision_receipt(args.comparator_receipt)
    (
        checkpoint_a,
        checkpoint_a_sha256,
        checkpoint_b,
        checkpoint_b_sha256,
    ) = load_checkpoint_c_upstream_receipts(
        registration,
        args.checkpoint_a_receipt,
        args.checkpoint_b_receipt,
    )

    evidence = build_final_held_out_evidence(
        execution_id=args.execution_id,
        generated_at_utc=max(
            candidate_receipt.generated_at_utc,
            comparator_receipt.generated_at_utc,
        ),
        source_revision=args.source_revision,
        registration=registration,
        suite=suite,
        metric_specification=metric_specification,
        checkpoint_a_receipt=checkpoint_a,
        checkpoint_a_receipt_file_sha256=checkpoint_a_sha256,
        checkpoint_b_receipt=checkpoint_b,
        checkpoint_b_receipt_file_sha256=checkpoint_b_sha256,
        candidate_manifest=candidate_manifest,
        comparator_manifest=comparator_manifest,
        candidate_receipt=candidate_receipt,
        comparator_receipt=comparator_receipt,
    )
    destination, artifact_sha256 = write_final_held_out_evidence(
        evidence,
        args.output,
    )
    print(json.dumps({
        "artifact": str(destination),
        "artifact_sha256": artifact_sha256,
        "schema_version": evidence.schema_version,
        "execution_id": evidence.execution_id,
        "registration_sha256": evidence.registration.registration_sha256,
        "source_revision": evidence.source_revision,
        "passed": evidence.decision.passed,
        "blockers": list(evidence.decision.blockers),
        "caller_supplied_aggregate_metrics": False,
        "raw_candidate_rows": len(evidence.candidate_case_results),
        "raw_comparator_rows": len(evidence.comparator_case_results),
        "candidate_receipt_sha256": evidence.candidate_receipt.receipt_sha256,
        "comparator_receipt_sha256": evidence.comparator_receipt.receipt_sha256,
        "deterministic_exact_replay": True,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

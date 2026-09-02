from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from checkpoint_a_aggregate import compute_gate
from checkpoint_a_constants import (
    CANDIDATE_VERSION,
    CRITERIA,
    EVIDENCE_SCHEMA_VERSION,
    FROZEN_DATASET_SHA256,
)
from checkpoint_a_live import _ambiguous_cases, _clear_cases
from checkpoint_a_protocol import canonical_sha256, load_evidence_object, verify_row
from ecocommit.validator import FidelityValidator


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SOURCE_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
RUN_ID_PATTERN = re.compile(r"^[0-9]{1,20}$")


def _terminal_category(row: dict[str, Any]) -> str:
    error_kind = row.get("error_kind")
    error_code = row.get("error_code")
    if isinstance(error_kind, str) and isinstance(error_code, str):
        return f"{error_kind}:{error_code}"[:160]
    if isinstance(error_kind, str):
        return error_kind[:160]
    return "semantic_failure"


def _semantic_categories(row: dict[str, Any]) -> list[str]:
    detail = row.get("detail")
    if not isinstance(detail, dict):
        return []
    categories: list[str] = []
    if detail.get("validator_status") != detail.get("expected_status"):
        categories.append("status_mismatch")
    required_checks = detail.get("required_checks")
    if isinstance(required_checks, list) and not all(required_checks):
        categories.append("required_clause_miss")
    if detail.get("exception_ok") is False:
        categories.append("exception_structure_miss")
    if detail.get("dependency_ok") is False:
        categories.append("dependency_structure_miss")
    findings = detail.get("findings")
    if isinstance(findings, list):
        for finding in findings:
            if isinstance(finding, dict) and isinstance(finding.get("code"), str):
                categories.append(f"finding:{finding['code'][:120]}")
    return categories


def _verify_frozen_manifest(
    manifest: object,
    *,
    expected_manifest_sha256: str | None,
    expected_source_revision: str | None,
    expected_run_id: str | None,
) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise ValueError("manifest is not an object")
    claimed_sha256 = manifest.get("manifest_sha256")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if claimed_sha256 != canonical_sha256(unsigned):
        raise ValueError("manifest digest is invalid")
    if expected_manifest_sha256 and claimed_sha256 != expected_manifest_sha256:
        raise ValueError("manifest does not match the out-of-band digest pin")
    if manifest.get("evidence_schema_version") != EVIDENCE_SCHEMA_VERSION:
        raise ValueError("evidence schema is not the frozen Candidate 3 schema")
    if manifest.get("candidate_version") != CANDIDATE_VERSION:
        raise ValueError("candidate version is not Candidate 3")
    dataset = manifest.get("dataset")
    if dataset != {"count": 80, "sha256": FROZEN_DATASET_SHA256}:
        raise ValueError("dataset identity is not frozen")
    if manifest.get("criteria") != CRITERIA:
        raise ValueError("acceptance criteria changed")
    if manifest.get("criteria_sha256") != canonical_sha256(CRITERIA):
        raise ValueError("acceptance criteria digest is invalid")
    source_revision = manifest.get("source_revision")
    if not isinstance(source_revision, str) or not SOURCE_REVISION_PATTERN.fullmatch(
        source_revision
    ):
        raise ValueError("source revision is invalid")
    workflow = manifest.get("workflow")
    if not isinstance(workflow, dict):
        raise ValueError("workflow identity is invalid")
    run_id = workflow.get("run_id")
    if run_id is not None and (
        not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id)
    ):
        raise ValueError("workflow run id is invalid")
    if expected_source_revision and source_revision != expected_source_revision:
        raise ValueError("source revision does not match the out-of-band pin")
    if expected_run_id and run_id != expected_run_id:
        raise ValueError("workflow run id does not match the out-of-band pin")
    return deepcopy(manifest)


def _retry_readiness(
    *,
    full_run: bool,
    gate_passed: bool,
    passed_cases: int,
    unresolved_cases: int,
    run_status: str,
    provider_condition: str,
    provider_health_observed_at: datetime | None,
    provider_health_reference_sha256: str | None,
) -> dict[str, object]:
    maximum_possible_passes = passed_cases + unresolved_cases
    threshold_passes = int(CRITERIA["case_pass_rate_min"] * 80)
    if gate_passed:
        decision = "NO_RETRY_NEEDED_GATE_PASSED"
    elif full_run or maximum_possible_passes < threshold_passes:
        decision = "NOT_READY_TERMINAL_RESULT"
    elif run_status in {"queued", "in_progress"}:
        decision = "NOT_READY_CONFLICTING_ATTEMPT_ACTIVE"
    elif run_status == "unknown":
        decision = "NOT_READY_RUN_STATUS_UNVERIFIED"
    elif provider_condition == "throttled":
        decision = "NOT_READY_PROVIDER_BLOCKER_PERSISTS"
    elif provider_condition != "healthy":
        decision = "NOT_READY_PROVIDER_CONDITION_UNVERIFIED"
    elif provider_health_observed_at is None or provider_health_reference_sha256 is None:
        decision = "NOT_READY_PROVIDER_HEALTH_UNPINNED"
    else:
        decision = "READY_TO_REQUEST_AUTHORIZED_RETRY"
    return {
        "decision": decision,
        "eligible": decision == "READY_TO_REQUEST_AUTHORIZED_RETRY",
        "authorization_required": decision == "READY_TO_REQUEST_AUTHORIZED_RETRY",
        "retry_action_performed": False,
        "run_status": run_status,
        "provider_condition": provider_condition,
        "provider_health_observed_at_utc": (
            provider_health_observed_at.isoformat()
            if provider_health_observed_at is not None
            else None
        ),
        "provider_health_reference_sha256": provider_health_reference_sha256,
        "maximum_possible_passes_if_all_unresolved_pass": maximum_possible_passes,
        "minimum_passes_required": threshold_passes,
    }


def diagnose(
    paths: list[Path],
    *,
    expected_manifest_sha256: str | None = None,
    expected_source_revision: str | None = None,
    expected_run_id: str | None = None,
    run_status: str = "unknown",
    provider_condition: str = "unknown",
    provider_health_observed_at: datetime | None = None,
    provider_health_reference_sha256: str | None = None,
) -> dict[str, object]:
    if not paths:
        raise ValueError("at least one artifact is required")
    frozen = _clear_cases() + _ambiguous_cases()
    frozen_by_id = {gold.case_id: gold for gold in frozen}
    validator = FidelityValidator()
    retained_manifest: dict[str, Any] | None = None
    by_id: dict[str, dict[str, Any]] = {}
    infrastructure_reports = Counter()

    for path in paths:
        payload = load_evidence_object(path)
        manifest = _verify_frozen_manifest(
            payload.get("manifest"),
            expected_manifest_sha256=expected_manifest_sha256,
            expected_source_revision=expected_source_revision,
            expected_run_id=expected_run_id,
        )
        if retained_manifest is None:
            retained_manifest = manifest
        elif retained_manifest != manifest:
            raise ValueError("artifacts do not share one exact manifest")
        rows = payload.get("cases", [])
        if not isinstance(rows, list):
            raise ValueError("artifact cases must be an array")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("artifact case row must be an object")
            case_id = row.get("id")
            gold = frozen_by_id.get(case_id)
            if gold is None:
                raise ValueError("artifact contains an unknown case id")
            verified = verify_row(row, gold, manifest, validator)
            previous = by_id.get(case_id)
            if previous is not None and previous.get("row_sha256") != verified.get(
                "row_sha256"
            ):
                raise ValueError("artifacts contain conflicting terminal rows")
            by_id[case_id] = verified
        infrastructure = payload.get("infrastructure_error")
        if infrastructure is not None:
            if not isinstance(infrastructure, dict):
                raise ValueError("infrastructure error report must be an object")
            kind = infrastructure.get("kind")
            code = infrastructure.get("code")
            case_id = infrastructure.get("case_id")
            if (
                not isinstance(kind, str)
                or not isinstance(code, str)
                or case_id not in frozen_by_id
            ):
                raise ValueError("infrastructure error report identity is invalid")
            infrastructure_reports[f"{kind}:{code}"[:160]] += 1

    assert retained_manifest is not None
    ordered, missing, metrics, full_run, passed = compute_gate(frozen, by_id)
    terminal = Counter()
    semantic = Counter()
    failed_cases: list[dict[str, object]] = []
    for row in ordered:
        if row.get("passed") is True:
            continue
        categories = _semantic_categories(row)
        for category in categories:
            semantic[category] += 1
        category = _terminal_category(row)
        terminal[category] += 1
        failed_cases.append(
            {
                "id": row["id"],
                "kind": "semantic" if row.get("detail") is not None else "terminal_error",
                "category": category,
                "semantic_categories": categories,
            }
        )

    retry = _retry_readiness(
        full_run=full_run,
        gate_passed=passed,
        passed_cases=metrics["passed_cases"],
        unresolved_cases=len(missing),
        run_status=run_status,
        provider_condition=provider_condition,
        provider_health_observed_at=provider_health_observed_at,
        provider_health_reference_sha256=provider_health_reference_sha256,
    )
    return {
        "schema_version": "A.DIAGNOSTICS.2",
        "candidate_version": CANDIDATE_VERSION,
        "source_revision": retained_manifest["source_revision"],
        "run_id": retained_manifest["workflow"]["run_id"],
        "manifest_sha256": retained_manifest["manifest_sha256"],
        "identity_pins": {
            "manifest_sha256": expected_manifest_sha256,
            "source_revision": expected_source_revision,
            "run_id": expected_run_id,
            "out_of_band_identity_fully_pinned": all(
                (expected_manifest_sha256, expected_source_revision, expected_run_id)
            ),
        },
        "status": (
            "PASSED"
            if passed
            else "FAILED_NOT_PASSED"
            if full_run
            else "BLOCKED_NOT_PASSED"
        ),
        "gate_passed": passed,
        "complete_receipt_possible": passed,
        "terminal_rows": len(ordered),
        "passed_rows": metrics["passed_cases"],
        "failed_rows": len(failed_cases),
        "unresolved_case_count": len(missing),
        "unresolved_case_ids": missing,
        "unresolved_cases_classification": "UNRESOLVED_NOT_ASSUMED_PROVIDER_DEFERRED",
        "metrics": metrics,
        "terminal_categories": dict(terminal),
        "semantic_categories": dict(semantic),
        "reported_infrastructure_categories": dict(infrastructure_reports),
        "failed_cases": failed_cases,
        "retry_readiness": retry,
        "frozen_contract_unchanged": True,
    }


def _utc_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("must be timezone-aware")
    return parsed.astimezone(UTC)


def _sha256(value: str) -> str:
    if not SHA256_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError("must be a lowercase SHA-256 digest")
    return value


def _source_revision(value: str) -> str:
    if not SOURCE_REVISION_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError("must be a lowercase 40-character revision")
    return value


def _run_id(value: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError("must be a numeric workflow run id")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify and summarize frozen Checkpoint A artifacts without "
            "launching or authorizing a retry."
        )
    )
    parser.add_argument("artifact", nargs="+", type=Path)
    parser.add_argument("--expected-manifest-sha256", type=_sha256)
    parser.add_argument("--expected-source-revision", type=_source_revision)
    parser.add_argument("--expected-run-id", type=_run_id)
    parser.add_argument(
        "--run-status",
        choices=("queued", "in_progress", "completed", "cancelled", "unknown"),
        default="unknown",
    )
    parser.add_argument(
        "--provider-condition",
        choices=("healthy", "throttled", "unknown"),
        default="unknown",
    )
    parser.add_argument("--provider-health-observed-at", type=_utc_datetime)
    parser.add_argument("--provider-health-reference-sha256", type=_sha256)
    args = parser.parse_args()
    if bool(args.provider_health_observed_at) != bool(
        args.provider_health_reference_sha256
    ):
        parser.error(
            "provider health observation time and reference digest are required together"
        )
    try:
        report = diagnose(
            args.artifact,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_source_revision=args.expected_source_revision,
            expected_run_id=args.expected_run_id,
            run_status=args.run_status,
            provider_condition=args.provider_condition,
            provider_health_observed_at=args.provider_health_observed_at,
            provider_health_reference_sha256=(
                args.provider_health_reference_sha256
            ),
        )
    except (OSError, ValueError):
        print(
            json.dumps(
                {
                    "schema_version": "A.DIAGNOSTICS.2",
                    "status": "INVALID_EVIDENCE",
                    "gate_passed": False,
                    "retry_action_performed": False,
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

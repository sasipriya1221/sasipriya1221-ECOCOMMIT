from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def _error_class(message: str) -> str:
    lower = message.lower()
    if "http 429" in lower:
        return "provider_http_429"
    if "http 5" in lower:
        return "provider_http_5xx"
    if "timeout" in lower or "timed out" in lower:
        return "provider_timeout"
    if "validationerror" in lower:
        return "contract_validation"
    if "json" in lower:
        return "provider_json"
    return message.split(":", 1)[0][:80] or "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="Print compact, non-secret diagnostics for a Checkpoint A artifact")
    parser.add_argument("artifact")
    args = parser.parse_args()

    path = Path(args.artifact)
    if not path.exists():
        print(json.dumps({"diagnostics": "artifact_missing", "path": str(path)}))
        return 0

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("cases", [])
    errors = Counter()
    semantic = Counter()
    failed = []

    for row in rows:
        if row.get("passed"):
            continue
        case_id = row.get("id", "?")
        if row.get("error"):
            category = _error_class(str(row["error"]))
            errors[category] += 1
            failed.append({"id": case_id, "kind": "error", "category": category})
            continue

        detail = row.get("detail") or {}
        finding_codes = [f.get("code") for f in detail.get("findings", []) if f.get("code")]
        if detail.get("validator_status") != detail.get("expected_status"):
            semantic["status_mismatch"] += 1
        if not all(detail.get("required_checks", [])):
            semantic["required_clause_miss"] += 1
        if not detail.get("exception_ok", True):
            semantic["exception_structure_miss"] += 1
        if not detail.get("dependency_ok", True):
            semantic["dependency_structure_miss"] += 1
        for code in finding_codes:
            semantic[f"finding:{code}"] += 1

        failed.append({
            "id": case_id,
            "kind": "semantic",
            "validator_status": detail.get("validator_status"),
            "expected_status": detail.get("expected_status"),
            "required_checks": detail.get("required_checks", []),
            "exception_ok": detail.get("exception_ok"),
            "dependency_ok": detail.get("dependency_ok"),
            "finding_codes": finding_codes,
        })

    print(json.dumps({
        "checkpoint_a_diagnostics": {
            "failed_count": len(failed),
            "error_categories": dict(errors),
            "semantic_categories": dict(semantic),
            "failed_cases": failed,
        }
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

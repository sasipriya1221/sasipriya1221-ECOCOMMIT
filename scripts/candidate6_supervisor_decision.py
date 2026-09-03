from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _valid_receipt_envelope(receipt: dict[str, Any]) -> bool:
    expected = receipt.get("receipt_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        return False
    unsigned = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    return expected == canonical_sha256(unsigned)


def _typed_stage(receipt: dict[str, Any], stage: str) -> bool:
    declared = receipt.get("stage")
    if declared is None:
        return stage in {"development", "holdout"}
    return declared == stage


def decide(stage: str, receipt: dict[str, Any] | None) -> Decision:
    if receipt is None:
        return Decision("STOP", "MISSING_RECEIPT")
    if not isinstance(receipt, dict) or not _valid_receipt_envelope(receipt):
        return Decision("STOP", "INVALID_RECEIPT_HASH")
    if not _typed_stage(receipt, stage):
        return Decision("STOP", "RECEIPT_STAGE_MISMATCH")
    if receipt.get("human_action_required") is True:
        return Decision("STOP_HUMAN", "HUMAN_ACTION_REQUIRED")
    status = str(receipt.get("status", receipt.get("qualification_state", ""))).upper()
    if status in {"FAILED", "BLOCKED", "SEMANTICALLY_UNREACHABLE"}:
        return Decision("STOP", status)

    if stage == "development":
        qstate = str(receipt.get("qualification_state", "")).upper()
        if qstate == "PROVIDER_INCOMPLETE":
            return Decision("WAIT", "PROVIDER_INCOMPLETE")
        if qstate == "COMPLETE" and receipt.get("passed") is True and receipt.get("terminal_semantic_cases") == 60 and receipt.get("provider_deferred_cases") == 0:
            return Decision("FREEZE", "DEVELOPMENT_PASS")
        return Decision("STOP", "DEVELOPMENT_NOT_PROVEN_PASS")

    if stage == "holdout":
        if receipt.get("qualification_state") != "COMPLETE" or receipt.get("passed") is not True:
            return Decision("STOP", "INTERNAL_QUALIFICATION_NOT_PASS")
        counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
        for key in ("fail_open", "dropped_guards", "dropped_exceptions", "conservation_failures", "unknown_authorized"):
            if counts.get(key) != 0:
                return Decision("STOP", f"NONZERO_{key.upper()}")
        metrics = receipt.get("metrics") if isinstance(receipt.get("metrics"), dict) else {}
        if not (
            metrics.get("case_pass_rate", 0) >= 0.95
            and metrics.get("selective_semantic_reliability", 0) >= 0.97
            and metrics.get("autonomous_coverage", 0) >= 0.60
            and metrics.get("ambiguous_clarification_accuracy", 0) >= 0.90
        ):
            return Decision("STOP", "INTERNAL_THRESHOLD_NOT_MET")
        if receipt.get("terminal_semantic_cases") != 60 or receipt.get("provider_deferred_cases") != 0:
            return Decision("STOP", "INTERNAL_RUN_INCOMPLETE")
        return Decision("PREREGISTER_A", "INTERNAL_QUALIFICATION_PASS")

    if stage == "checkpoint_a":
        return Decision("ADVANCE_B", "A_PASS") if status == "PASS" else Decision("STOP", "A_NOT_PASS")
    if stage == "checkpoint_b":
        return Decision("ADVANCE_C", "B_PASS") if status == "PASS" else Decision("STOP", "B_NOT_PASS")
    if stage == "checkpoint_c":
        return Decision("ADVANCE_D", "C_PASS") if status == "PASS" else Decision("STOP", "C_NOT_PASS")
    if stage == "checkpoint_d":
        return Decision("ADVANCE_E", "D_PASS") if status == "PASS" else Decision("STOP", "D_NOT_PASS")
    if stage == "checkpoint_e":
        return Decision("COMPLETE", "E_PASS") if status == "PASS" else Decision("STOP", "E_NOT_PASS")
    return Decision("STOP", "UNKNOWN_STAGE")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text(encoding="utf-8")) if args.receipt.exists() else None
    decision = decide(args.stage, receipt)
    print(json.dumps({"action": decision.action, "reason": decision.reason}, sort_keys=True))


if __name__ == "__main__":
    main()

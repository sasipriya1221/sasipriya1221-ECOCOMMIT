from __future__ import annotations

from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class OfficialThresholds:
    case_pass: float = 0.90
    selective_reliability: float = 0.95
    autonomous_coverage: float = 0.55
    clarification_accuracy: float = 0.80


@dataclass(frozen=True)
class OfficialCounts:
    total: int
    clear_total: int
    ambiguous_total: int
    processed: int
    clear_processed: int
    ambiguous_processed: int
    case_passes: int
    autonomous: int
    correct_autonomous: int
    ambiguous_correct: int


def _valid(c: OfficialCounts) -> bool:
    return (
        c.total == c.clear_total + c.ambiguous_total
        and c.processed == c.clear_processed + c.ambiguous_processed
        and 0 <= c.clear_processed <= c.clear_total
        and 0 <= c.ambiguous_processed <= c.ambiguous_total
        and 0 <= c.processed <= c.total
        and 0 <= c.case_passes <= c.processed
        and 0 <= c.correct_autonomous <= c.autonomous <= c.processed
        and 0 <= c.ambiguous_correct <= c.ambiguous_processed
    )


def optimistic_completion(c: OfficialCounts, t: OfficialThresholds = OfficialThresholds()) -> OfficialCounts | None:
    """Return the best jointly feasible completion, or None when thresholds are unreachable.

    Clear gold cases are optimistically completed as correct autonomous responses.
    Ambiguous gold cases are optimistically completed as correct clarifications. If the
    coverage threshold still cannot be met, the minimum number of remaining ambiguous
    cases is converted to autonomous responses. Those conversions necessarily lose a
    case pass and an ambiguity-correct result and cannot be correct autonomous results.
    This yields the exact optimistic joint bound for the four frozen Checkpoint-A metrics.
    """
    if not _valid(c):
        return None
    clear_remaining = c.clear_total - c.clear_processed
    ambiguous_remaining = c.ambiguous_total - c.ambiguous_processed

    required_autonomous = ceil(t.autonomous_coverage * c.total)
    autonomous_if_all_clear_correct = c.autonomous + clear_remaining
    ambiguous_autonomous_needed = max(0, required_autonomous - autonomous_if_all_clear_correct)
    if ambiguous_autonomous_needed > ambiguous_remaining:
        return None

    completed = OfficialCounts(
        total=c.total,
        clear_total=c.clear_total,
        ambiguous_total=c.ambiguous_total,
        processed=c.total,
        clear_processed=c.clear_total,
        ambiguous_processed=c.ambiguous_total,
        case_passes=c.case_passes + clear_remaining + ambiguous_remaining - ambiguous_autonomous_needed,
        autonomous=c.autonomous + clear_remaining + ambiguous_autonomous_needed,
        correct_autonomous=c.correct_autonomous + clear_remaining,
        ambiguous_correct=c.ambiguous_correct + ambiguous_remaining - ambiguous_autonomous_needed,
    )
    return completed if final_pass(completed, t) else None


def reachable(c: OfficialCounts, t: OfficialThresholds = OfficialThresholds()) -> bool:
    return optimistic_completion(c, t) is not None


def final_pass(c: OfficialCounts, t: OfficialThresholds = OfficialThresholds()) -> bool:
    if not _valid(c) or c.processed != c.total:
        return False
    reliability = c.correct_autonomous / c.autonomous if c.autonomous else 0.0
    clarification = c.ambiguous_correct / c.ambiguous_total if c.ambiguous_total else 1.0
    return (
        c.case_passes >= ceil(t.case_pass * c.total)
        and reliability >= t.selective_reliability
        and c.autonomous >= ceil(t.autonomous_coverage * c.total)
        and c.ambiguous_correct >= ceil(t.clarification_accuracy * c.ambiguous_total)
    )

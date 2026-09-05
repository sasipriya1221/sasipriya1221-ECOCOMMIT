from __future__ import annotations
from dataclasses import dataclass
from math import ceil

@dataclass(frozen=True)
class QualificationThresholds:
    case_pass:float=.95; selective_reliability:float=.97; autonomous_coverage:float=.60; clarification_accuracy:float=.90
@dataclass(frozen=True)
class QualificationCounts:
    total:int; processed:int; case_passes:int; autonomous:int; correct_autonomous:int; ambiguous_total:int; ambiguous_processed:int; ambiguous_correct:int; fail_open:int=0; dropped_guards:int=0; dropped_exceptions:int=0; conservation_failures:int=0; unknown_authorized:int=0

def reachable(c:QualificationCounts,t:QualificationThresholds=QualificationThresholds())->bool:
    rem=c.total-c.processed
    if rem<0 or c.ambiguous_processed>c.ambiguous_total:return False
    if any((c.fail_open,c.dropped_guards,c.dropped_exceptions,c.conservation_failures,c.unknown_authorized)):return False
    if c.case_passes+rem < ceil(t.case_pass*c.total):return False
    required_auto=ceil(t.autonomous_coverage*c.total)
    needed_auto=max(0,required_auto-c.autonomous)
    if needed_auto>rem:return False
    # Exact optimistic reliability bound: only the minimum additional autonomous
    # rows required for coverage are made autonomous, and every such row is correct.
    # Remaining rows may abstain; they cannot repair an existing wrong autonomous row.
    best_auto=c.autonomous+needed_auto
    best_correct=c.correct_autonomous+needed_auto
    if best_auto==0 or best_correct/best_auto<t.selective_reliability:return False
    amb_rem=c.ambiguous_total-c.ambiguous_processed
    if c.ambiguous_total and c.ambiguous_correct+amb_rem < ceil(t.clarification_accuracy*c.ambiguous_total):return False
    return True

def final_pass(c:QualificationCounts,t:QualificationThresholds=QualificationThresholds())->bool:
    if c.processed!=c.total:return False
    rel=c.correct_autonomous/c.autonomous if c.autonomous else 0
    clar=c.ambiguous_correct/c.ambiguous_total if c.ambiguous_total else 1
    return (c.case_passes/c.total>=t.case_pass and rel>=t.selective_reliability and c.autonomous/c.total>=t.autonomous_coverage and clar>=t.clarification_accuracy and not any((c.fail_open,c.dropped_guards,c.dropped_exceptions,c.conservation_failures,c.unknown_authorized)))

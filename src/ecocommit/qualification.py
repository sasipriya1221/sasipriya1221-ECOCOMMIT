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
    if c.case_passes+rem < ceil(t.case_pass*c.total): return False
    # Reliability upper bound must account for remaining cases that could become correct autonomous.
    best_correct=c.correct_autonomous+rem; best_auto=c.autonomous+rem
    if best_auto and best_correct/best_auto < t.selective_reliability: return False
    if c.autonomous+rem < ceil(t.autonomous_coverage*c.total): return False
    amb_rem=c.ambiguous_total-c.ambiguous_processed
    if c.ambiguous_total and c.ambiguous_correct+amb_rem < ceil(t.clarification_accuracy*c.ambiguous_total): return False
    if any((c.fail_open,c.dropped_guards,c.dropped_exceptions,c.conservation_failures,c.unknown_authorized)): return False
    return True

def final_pass(c:QualificationCounts,t:QualificationThresholds=QualificationThresholds())->bool:
    if c.processed!=c.total:return False
    rel=c.correct_autonomous/c.autonomous if c.autonomous else 0
    clar=c.ambiguous_correct/c.ambiguous_total if c.ambiguous_total else 1
    return (c.case_passes/c.total>=t.case_pass and rel>=t.selective_reliability and c.autonomous/c.total>=t.autonomous_coverage and clar>=t.clarification_accuracy and not any((c.fail_open,c.dropped_guards,c.dropped_exceptions,c.conservation_failures,c.unknown_authorized)))

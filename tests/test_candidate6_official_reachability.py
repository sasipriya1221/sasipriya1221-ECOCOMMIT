from itertools import product

from scripts.candidate6_official_reachability import (
    OfficialCounts,
    OfficialThresholds,
    final_pass,
    reachable,
)


def _observed_state_valid(c: OfficialCounts) -> bool:
    return (
        c.total == c.clear_total + c.ambiguous_total
        and c.processed == c.clear_processed + c.ambiguous_processed
        and 0 <= c.clear_processed <= c.clear_total
        and 0 <= c.ambiguous_processed <= c.ambiguous_total
        and 0 <= c.correct_autonomous <= c.clear_processed
        and 0 <= c.ambiguous_correct <= c.ambiguous_processed
        and c.case_passes == c.correct_autonomous + c.ambiguous_correct
        and 0 <= c.correct_autonomous <= c.autonomous <= c.processed
    )


def _brute_reachable(c: OfficialCounts, t: OfficialThresholds) -> bool:
    if not _observed_state_valid(c):
        return False
    clear_remaining = c.clear_total - c.clear_processed
    ambiguous_remaining = c.ambiguous_total - c.ambiguous_processed
    # Clear future rows: 0=fail/non-autonomous, 1=correct autonomous.
    # Ambiguous future rows: 0=fail/non-autonomous, 1=correct clarification,
    # 2=autonomous wrong. Dominated alternatives need not be represented.
    for clear_outcomes in product(range(2), repeat=clear_remaining):
        for ambiguous_outcomes in product(range(3), repeat=ambiguous_remaining):
            clear_correct = sum(x == 1 for x in clear_outcomes)
            amb_correct = sum(x == 1 for x in ambiguous_outcomes)
            amb_auto_wrong = sum(x == 2 for x in ambiguous_outcomes)
            completed = OfficialCounts(
                total=c.total,
                clear_total=c.clear_total,
                ambiguous_total=c.ambiguous_total,
                processed=c.total,
                clear_processed=c.clear_total,
                ambiguous_processed=c.ambiguous_total,
                case_passes=c.case_passes + clear_correct + amb_correct,
                autonomous=c.autonomous + clear_correct + amb_auto_wrong,
                correct_autonomous=c.correct_autonomous + clear_correct,
                ambiguous_correct=c.ambiguous_correct + amb_correct,
            )
            if final_pass(completed, t):
                return True
    return False


def test_frozen_official_thresholds_are_unchanged():
    t = OfficialThresholds()
    assert t.case_pass == 0.90
    assert t.selective_reliability == 0.95
    assert t.autonomous_coverage == 0.55
    assert t.clarification_accuracy == 0.80


def test_class_aware_bound_accounts_for_ambiguous_autonomous_sacrifice():
    t = OfficialThresholds(case_pass=0.75, selective_reliability=0.75, autonomous_coverage=0.75, clarification_accuracy=0.75)
    c = OfficialCounts(
        total=4, clear_total=2, ambiguous_total=2,
        processed=2, clear_processed=2, ambiguous_processed=0,
        case_passes=2, autonomous=2, correct_autonomous=2, ambiguous_correct=0,
    )
    # Coverage needs one of the two remaining ambiguous rows to become autonomous.
    # That leaves only one correct clarification, below the required 2/2.
    assert reachable(c, t) is False


def test_existing_wrong_autonomous_case_cannot_be_repaired_when_reliability_is_unreachable():
    c = OfficialCounts(
        total=10, clear_total=7, ambiguous_total=3,
        processed=9, clear_processed=6, ambiguous_processed=3,
        case_passes=9, autonomous=7, correct_autonomous=6, ambiguous_correct=3,
    )
    assert reachable(c, OfficialThresholds()) is False


def test_exact_bound_matches_bruteforce_for_small_states():
    thresholds = OfficialThresholds(case_pass=0.75, selective_reliability=0.75, autonomous_coverage=0.50, clarification_accuracy=0.50)
    for clear_total in range(1, 4):
        for ambiguous_total in range(1, 3):
            total = clear_total + ambiguous_total
            for clear_processed in range(clear_total + 1):
                for ambiguous_processed in range(ambiguous_total + 1):
                    processed = clear_processed + ambiguous_processed
                    if total - processed > 5:
                        continue
                    for case_passes in range(processed + 1):
                        for autonomous in range(processed + 1):
                            for correct_autonomous in range(autonomous + 1):
                                for ambiguous_correct in range(ambiguous_processed + 1):
                                    c = OfficialCounts(
                                        total=total,
                                        clear_total=clear_total,
                                        ambiguous_total=ambiguous_total,
                                        processed=processed,
                                        clear_processed=clear_processed,
                                        ambiguous_processed=ambiguous_processed,
                                        case_passes=case_passes,
                                        autonomous=autonomous,
                                        correct_autonomous=correct_autonomous,
                                        ambiguous_correct=ambiguous_correct,
                                    )
                                    assert reachable(c, thresholds) == _brute_reachable(c, thresholds)

from __future__ import annotations

from abc import ABC, abstractmethod

from .checkpoint_c_models import (
    BaselineDecision,
    BaselineRegistration,
    BenchmarkCase,
    ConservativeAbstainRegistration,
    Decision,
    DynamicRiskEvidenceRegistration,
    EvidenceStatus,
    LatencyProvenance,
    NaiveAgentReplayRegistration,
    PromptGuardrailReplayRegistration,
    RegisteredAgentDecision,
    StaticRulesRegistration,
)


class DeterministicBaseline(ABC):
    """A local baseline whose decisions depend only on a registered config and case."""

    @property
    @abstractmethod
    def baseline_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, case: BenchmarkCase) -> BaselineDecision:
        raise NotImplementedError


class AgentReplayBaseline(DeterministicBaseline):
    """Deterministically replay a frozen agent-output manifest.

    The registration carries explicit fixture/cached-output provenance. Replaying
    synthetic decisions validates the harness only and is never model-performance
    evidence.
    """

    def __init__(
        self,
        registration: NaiveAgentReplayRegistration | PromptGuardrailReplayRegistration,
    ):
        self.registration = registration
        self._decision_by_case = {
            decision.case_id: decision for decision in registration.decisions
        }

    @property
    def baseline_id(self) -> str:
        return self.registration.baseline_id

    def evaluate(self, case: BenchmarkCase) -> BaselineDecision:
        try:
            registered: RegisteredAgentDecision = self._decision_by_case[case.case_id]
        except KeyError as exc:
            raise ValueError(
                f"agent replay {self.baseline_id!r} has no frozen output for case {case.case_id!r}"
            ) from exc
        return BaselineDecision(
            baseline_id=self.baseline_id,
            case_id=case.case_id,
            decision=registered.decision,
            reason_codes=registered.reason_codes,
            calculated_risk_bps=None,
            examined_evidence_ids=[],
            verification_latency_ms=registered.verification_latency_ms,
            latency_provenance=registered.latency_provenance,
        )

class StaticRulesBaseline(DeterministicBaseline):
    """A strong fixed-rule comparator with no access to evidence state."""

    def __init__(self, registration: StaticRulesRegistration):
        self.registration = registration

    @property
    def baseline_id(self) -> str:
        return self.registration.baseline_id

    def evaluate(self, case: BenchmarkCase) -> BaselineDecision:
        reasons: list[str] = []
        if case.requested_amount_minor > self.registration.amount_ceiling_minor:
            reasons.append("STATIC_AMOUNT_CEILING_EXCEEDED")

        blocked_codes = set(self.registration.blocked_signal_codes)
        if any(signal.active and signal.code in blocked_codes for signal in case.risk_signals):
            reasons.append("STATIC_BLOCKED_SIGNAL_PRESENT")

        if reasons:
            decision = Decision.BLOCK
        else:
            decision = Decision.EXECUTE
            reasons.append("STATIC_RULES_ALLOW")

        return BaselineDecision(
            baseline_id=self.baseline_id,
            case_id=case.case_id,
            decision=decision,
            reason_codes=reasons,
            calculated_risk_bps=None,
            examined_evidence_ids=[],
            verification_latency_ms=self.registration.simulated_decision_overhead_ms,
            latency_provenance=LatencyProvenance.SIMULATED,
        )


class DynamicRiskEvidenceBaseline(DeterministicBaseline):
    """Policy-, risk-, freshness-, and evidence-aware deterministic comparator."""

    def __init__(self, registration: DynamicRiskEvidenceRegistration):
        self.registration = registration

    @property
    def baseline_id(self) -> str:
        return self.registration.baseline_id

    def _risk_score(self, case: BenchmarkCase) -> int:
        risk = case.base_risk_bps
        risk += sum(signal.risk_weight_bps for signal in case.risk_signals if signal.active)
        for item in case.evidence:
            if item.status == EvidenceStatus.VERIFIED:
                risk -= self.registration.verified_evidence_credit_bps
            elif item.status == EvidenceStatus.FAILED:
                risk += self.registration.failed_evidence_penalty_bps
            elif item.status == EvidenceStatus.MISSING:
                risk += self.registration.missing_evidence_penalty_bps
            else:
                risk += self.registration.stale_evidence_penalty_bps
        return min(10_000, max(0, risk))

    def evaluate(self, case: BenchmarkCase) -> BaselineDecision:
        overhead = self.registration.simulated_decision_overhead_ms
        if case.requested_amount_minor > case.policy_limit_minor:
            return BaselineDecision(
                baseline_id=self.baseline_id,
                case_id=case.case_id,
                decision=Decision.BLOCK,
                reason_codes=["CASE_POLICY_LIMIT_EXCEEDED"],
                calculated_risk_bps=case.base_risk_bps,
                examined_evidence_ids=[],
                verification_latency_ms=overhead,
                latency_provenance=LatencyProvenance.SIMULATED,
            )

        examined = [item.evidence_id for item in case.evidence]
        latency = overhead + sum(item.simulated_verification_latency_ms for item in case.evidence)
        score = self._risk_score(case)
        required_failed = any(
            item.required and item.status == EvidenceStatus.FAILED for item in case.evidence
        )
        required_incomplete = any(
            item.required and item.status in {EvidenceStatus.MISSING, EvidenceStatus.STALE}
            for item in case.evidence
        )

        if required_failed and self.registration.block_on_required_failure:
            decision = Decision.BLOCK
            reasons = ["REQUIRED_EVIDENCE_FAILED"]
        elif score >= self.registration.block_risk_min_bps:
            decision = Decision.BLOCK
            reasons = ["DYNAMIC_RISK_BLOCK_THRESHOLD"]
        elif required_incomplete and self.registration.abstain_on_required_missing_or_stale:
            decision = Decision.ABSTAIN
            reasons = ["REQUIRED_EVIDENCE_INCOMPLETE"]
        elif score <= self.registration.execute_risk_max_bps:
            decision = Decision.EXECUTE
            reasons = ["DYNAMIC_POLICY_EVIDENCE_RISK_ALLOW"]
        else:
            decision = Decision.ABSTAIN
            reasons = ["DYNAMIC_RISK_REVIEW_BAND"]

        return BaselineDecision(
            baseline_id=self.baseline_id,
            case_id=case.case_id,
            decision=decision,
            reason_codes=reasons,
            calculated_risk_bps=score,
            examined_evidence_ids=examined,
            verification_latency_ms=latency,
            latency_provenance=LatencyProvenance.SIMULATED,
        )


class ConservativeAbstainBaseline(DeterministicBaseline):
    """Negative control: never grants or denies irreversible authority autonomously."""

    def __init__(self, registration: ConservativeAbstainRegistration):
        self.registration = registration

    @property
    def baseline_id(self) -> str:
        return self.registration.baseline_id

    def evaluate(self, case: BenchmarkCase) -> BaselineDecision:
        return BaselineDecision(
            baseline_id=self.baseline_id,
            case_id=case.case_id,
            decision=Decision.ABSTAIN,
            reason_codes=["CONSERVATIVE_ALWAYS_ABSTAIN"],
            calculated_risk_bps=None,
            examined_evidence_ids=[],
            verification_latency_ms=self.registration.simulated_decision_overhead_ms,
            latency_provenance=LatencyProvenance.SIMULATED,
        )


def build_baseline(registration: BaselineRegistration) -> DeterministicBaseline:
    if isinstance(
        registration,
        (NaiveAgentReplayRegistration, PromptGuardrailReplayRegistration),
    ):
        return AgentReplayBaseline(registration)
    if isinstance(registration, StaticRulesRegistration):
        return StaticRulesBaseline(registration)
    if isinstance(registration, DynamicRiskEvidenceRegistration):
        return DynamicRiskEvidenceBaseline(registration)
    if isinstance(registration, ConservativeAbstainRegistration):
        return ConservativeAbstainBaseline(registration)
    raise TypeError(f"unsupported baseline registration: {type(registration).__name__}")


def evaluate_with_error_retention(
    baseline: DeterministicBaseline,
    case: BenchmarkCase,
) -> BaselineDecision:
    """Keep one explicit row when a baseline implementation raises unexpectedly."""

    try:
        return baseline.evaluate(case)
    except Exception as exc:  # noqa: BLE001 - benchmark errors are retained as data
        return BaselineDecision(
            baseline_id=baseline.baseline_id,
            case_id=case.case_id,
            decision=Decision.ERROR,
            reason_codes=["BASELINE_EVALUATION_ERROR", f"ERROR_TYPE_{type(exc).__name__}"],
            calculated_risk_bps=None,
            examined_evidence_ids=[],
            verification_latency_ms=None,
            latency_provenance=LatencyProvenance.NOT_AVAILABLE,
        )

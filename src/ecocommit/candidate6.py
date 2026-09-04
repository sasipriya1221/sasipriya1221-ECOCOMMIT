from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .semantic_compiler import ConservationError, compile_contract
from .semantic_ir import SemanticIR, Truth, eval_expr, truth_and
from .semantic_validation import SemanticValidationError, blocked_actions


SYSTEM_PROMPT = '''You are the semantic parser for ECOCOMMIT.
Your only task is to translate the user's instruction into semantic-ir-v1.
You do NOT decide whether an economic action is allowed. You do NOT construct the final ECOCOMMIT contract.
Extract only semantic meaning explicitly supported by the instruction. Preserve every explicit economic or commitment-relevant action, object, counterparty, quantity, monetary constraint, condition, dependency, negation, exception and ambiguity. Never invent facts.

REFERENCE DISCIPLINE
- Every reference field MUST contain the ID of a declared semantic object, never copied prose.
- action.object and action.counterparty must reference declared entity IDs such as E1.
- constraint.action and guard.action must reference declared action IDs such as A1.
- predicate.subject must reference a declared entity ID such as E2.
- Boolean ATOM.predicate must reference a declared predicate ID such as P1.
- dependency.action and dependency.prerequisite_action must reference declared action IDs.
- ambiguity targets must reference an existing declared ID of the target kind; ACTION_FIELD uses A#, COUNTERPARTY uses E#, PREDICATE uses P#, GUARD uses G#, CONSTRAINT uses C#, DEPENDENCY uses D#. PRESENTATION has no ID.
- Never write a surface label such as an object name, supplier name, action phrase, or approval phrase into a reference field. Declare the semantic object and reference its ID.

GUARD DISCIPLINE
Conditions governing actions use ONLY_IF guards with ATOM/AND/OR/NOT. Preserve AND versus OR, negation, condition scope and exception scope exactly. Cross-action sequencing belongs only in dependencies. Do not encode the same relationship twice.
Create a guard only when the instruction actually makes execution conditional, for example with "only if", "if", "provided", "on condition that", "subject to", "when", "unless", or an equivalent authorization condition.
Do NOT turn a descriptive, completed-state, purpose, or noun-modifying phrase into a guard merely because it contains words such as "completed", "approved", "valid", or "current". A condition must govern whether the action may occur.

AMBIGUITY DISCIPLINE — ABSENCE IS NOT AMBIGUITY
An unstated fact is NOT, by itself, an ambiguity. Represent missing information only when the instruction itself makes that unresolved information necessary to interpret an explicitly stated action, constraint, condition, dependency, exception, or authority boundary.
Do not create an ambiguity merely because an action lacks a stated budget, price, counterparty/provider/vendor, date, time, duration, location, payment method, or other optional operational detail. If the instruction gives a complete semantic action without requiring such a field, omit that field and do not clarify it.
Do not infer that every BUY/ORDER/HIRE/BOOK/RESERVE action requires a budget, counterparty, date, time, or duration. Those fields become material only when the user's wording makes them part of the requested meaning or authority boundary.
By contrast, if the user explicitly makes authorization depend on unresolved wording — for example an unspecified limit explicitly required by a stated cap, an unclear named counterparty reference, or an ambiguous condition that governs whether the action may execute — preserve that unresolved material meaning as an ambiguity.
If ambiguous wording is strictly presentation/cosmetic language disconnected from economic authorization, target PRESENTATION. The deterministic system, not you, decides materiality.
If wording affecting an economic semantic object is unresolved, target ACTION_FIELD, PREDICATE, GUARD, CONSTRAINT, COUNTERPARTY or DEPENDENCY; never guess.

GROUNDING AND UNSUPPORTED MEANING
ABSENCE grounding is permitted only for information genuinely required by the user's stated semantics, never to list optional unstated details. Semantic facts actually stated use exact SPAN quotes copied verbatim. If the schema cannot safely express material meaning that affects authorization, emit an UNSUPPORTED_SEMANTIC_STRUCTURE ambiguity targeted to the affected economic semantic object instead of simplifying it.

Do not calculate operational consequences. Never output execution_allowed, transaction_allowed, clarification status, approval state, evidence satisfaction, economic authority, validator state or payment permission.
Output exactly one JSON object conforming to semantic-ir-v1. No commentary or markdown. JSON only.'''


PROVIDER_POLICY = {
    "provider": "groq",
    "model": "qwen/qwen3.6-27b",
    "reasoning": "none",
    "response_mode": "json_object",
    "max_completion_tokens": 2048,
    "timeout_seconds": 60,
    "max_total_attempts": 3,
    "max_schema_corrections": 2,
    "terminality": "first_schema_valid_ir",
    "semantic_score_retry": False,
}


class SemanticProvider(Protocol):
    def parse(self, instruction: str) -> SemanticIR: ...


@dataclass(frozen=True)
class Candidate6Result:
    status: str
    contract: Any | None
    semantic_ir: SemanticIR | None
    blocked_actions: frozenset[str]
    error_code: str | None = None


def action_guard_truth(ir: SemanticIR, action_id: str, predicate_values: Mapping[str, Truth]) -> Truth:
    values = [eval_expr(g.expr, predicate_values) for g in ir.guards if g.action == action_id]
    return truth_and(values) if values else Truth.TRUE


def action_authorized(ir: SemanticIR, action_id: str, predicate_values: Mapping[str, Truth]) -> bool:
    if action_id in blocked_actions(ir):
        return False
    if action_guard_truth(ir, action_id, predicate_values) is not Truth.TRUE:
        return False
    for exception in ir.exceptions:
        if exception.target.kind == "ACTION" and exception.target.id == action_id and exception.effect.effect == "BLOCK_ACTION":
            if eval_expr(exception.when, predicate_values) is not Truth.FALSE:
                return False
    return True


def run_candidate6(instruction: str, provider: SemanticProvider) -> Candidate6Result:
    try:
        ir = provider.parse(instruction)
        contract, _, blocked = compile_contract(ir, instruction)
        status = "CLARIFICATION_REQUIRED" if blocked else "COMPILED"
        return Candidate6Result(status, contract, ir, frozenset(blocked))
    except (SemanticValidationError, ConservationError, ValueError) as exc:
        return Candidate6Result("REJECTED", None, None, frozenset(), str(exc))

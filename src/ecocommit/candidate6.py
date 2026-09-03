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
Conditions governing actions use ONLY_IF guards with ATOM/AND/OR/NOT. Preserve AND versus OR, negation, condition scope and exception scope exactly. Cross-action sequencing belongs only in dependencies. Do not encode the same relationship twice.
If wording affecting an economic semantic object is unresolved, represent an ambiguity targeted to ACTION_FIELD, PREDICATE, GUARD, CONSTRAINT, COUNTERPARTY or DEPENDENCY; never guess. If ambiguous wording is strictly presentation/cosmetic language disconnected from economic authorization, target PRESENTATION. The deterministic system, not you, decides materiality.
Missing information uses ABSENCE grounding; semantic facts actually stated use exact SPAN quotes copied verbatim. If the schema cannot safely express the instruction, emit an UNSUPPORTED_SEMANTIC_STRUCTURE ambiguity targeted to the affected economic semantic object instead of simplifying it.
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
    # This is the deterministic semantic authority boundary only; downstream B controls
    # must still pass before any economic commitment. UNKNOWN is never authority.
    if action_id in blocked_actions(ir):
        return False
    if action_guard_truth(ir, action_id, predicate_values) is not Truth.TRUE:
        return False
    for exception in ir.exceptions:
        if exception.target.kind == "ACTION" and exception.target.id == action_id and exception.effect.effect == "BLOCK_ACTION":
            # A restrictive exception whose truth is UNKNOWN is fail-closed.
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

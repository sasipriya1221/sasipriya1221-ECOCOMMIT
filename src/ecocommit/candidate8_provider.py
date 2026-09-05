from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .candidate7_flat import FactBatch, FactKind, LabeledFact, RelationBatch, assign_fact_ids, grounded_span
from .candidate7_provider import Candidate7SchemaError, GroqCandidate7Provider, PASS1_SYSTEM_PROMPT
from .candidate7_relation_checklist import Pass2DecisionBatch, action_entity_pair_payload
from .candidate7_structure import _action_kind
from .candidate8_logic import C8FactDisposition
from .candidate8_normalize import (
    candidate8_dispositions,
    infer_candidate8_relations,
    normalize_candidate8_facts,
)


PASS2_SYSTEM_PROMPT = """You are ECOCOMMIT Candidate 8 pass 2: an exhaustive relation classifier.
You receive an ID-labeled flat fact list plus a deterministic `action_entity_pairs` checklist.
Output one flat JSON object with exactly two keys: `action_entity_decisions` and `relations`.

For EVERY supplied ACTION x ENTITY pair, emit exactly one action_entity_decision with exactly:
  action: supplied ACTION F####
  entity: supplied ENTITY F####
  decision: ACTION_OBJECT | ACTION_COUNTERPARTY | NONE
  justification_span: exact verbatim substring establishing the relation, or null when decision=NONE
No supplied pair may be omitted, duplicated, or replaced with a different pair.

ROLE SEMANTICS — apply these mechanically and consistently:
- ACTION_OBJECT is the grammatical/direct source object or complement of the action. It is a source role, not an ontological type. A person or organization can be ACTION_OBJECT when it occupies that direct-object slot.
- ACTION_COUNTERPARTY is a separate participant explicitly related outside the direct-object slot, normally introduced by `to`, `from`, `with`, `through`, `via`, `by`, or `at`.
- Never label a bare source-local direct object ACTION_COUNTERPARTY merely because it denotes a payee, supplier, contractor, organization, or person.
- Generic examples: `Pay the carrier` => carrier is ACTION_OBJECT. `Pay the invoice to the carrier` => invoice is ACTION_OBJECT and carrier is ACTION_COUNTERPARTY. `Transfer the refund to the customer` => refund is ACTION_OBJECT and customer is ACTION_COUNTERPARTY.

The `relations` list is only for non-ACTION×ENTITY relations. Each relation has exactly:
  kind, left, right, justification_span
Allowed kinds:
PREDICATE_SUBJECT, CONSTRAINT_APPLIES_TO, GUARDS_ACTION, BLOCKS_ACTION,
AFTER_COMPLETION, AFTER_SUCCESS, EXCEPTION_TARGET, EXCEPTION_WHEN,
AMBIGUITY_TARGET, ALL_OF, ANY_OF.

Rules:
- ACTION_OBJECT and ACTION_COUNTERPARTY appear only in `action_entity_decisions`.
- `NONE` is required when a supplied pair has no explicit relationship.
- Every non-NONE justification_span and every relation justification_span MUST be an exact verbatim substring of the instruction that establishes the claimed relationship.
- Every monetary/numeric/temporal CONSTRAINT must be linked to the ACTION it constrains with CONSTRAINT_APPLIES_TO.
- Every authorization PREDICATE must be semantically linked: GUARDS_ACTION, BLOCKS_ACTION, PREDICATE_SUBJECT, ALL_OF/ANY_OF, EXCEPTION_WHEN, or AMBIGUITY_TARGET as supported by the source.
- Every EXCEPTION must have exactly one EXCEPTION_TARGET.
- Prefer source-local evidence and preserve grammatical argument structure before world-knowledge assumptions.
- Reference ONLY supplied F#### IDs. Create no IDs, facts, prose, groups, or nested ASTs.
- ALL_OF and ANY_OF classify logical relationships between existing PREDICATE facts only.
- GUARDS_ACTION means an explicit authorization condition; do not infer it from proximity.
- BLOCKS_ACTION means the predicate explicitly prevents execution when it holds.
- AFTER_COMPLETION / AFTER_SUCCESS are directed: left is later action, right is prerequisite action.
- EXCEPTION_WHEN is directed: left is PREDICATE, right is EXCEPTION.
- Empty `relations` is valid only when no non-ACTION×ENTITY semantic relation is required by the extracted facts.
JSON only."""

PASS1_SYSTEM_PROMPT_C8 = PASS1_SYSTEM_PROMPT + """

Candidate-8 atomicity rules:
- `unless X` is a blocking authorization condition: extract X as a PREDICATE, not as an EXCEPTION.
- Split conditions joined by `and` or `or` into separate atomic PREDICATE facts.
- An EXCEPTION begins with an explicit exception construction such as `except`; it is not a synonym for `unless`.
- Vague quantities, budgets, or subjective selection terms are AMBIGUITY facts in addition to any entity they modify.
- A bare nominal execution context such as `after delivery` is not by itself an authorization predicate.
- A clause after a semicolon that neither authorizes nor constrains a supported economic action is irrelevant context; do not extract it.
JSON only."""


@dataclass(frozen=True)
class Candidate8ParseResult:
    facts: tuple[LabeledFact, ...]
    relations: RelationBatch
    dispositions: dict[str, C8FactDisposition]
    provider_trace: tuple[dict[str, Any], ...]


class GroqCandidate8Provider(GroqCandidate7Provider):
    """Candidate-8 reuses hardened transport/retry code with OTPM-safe output fixed at 900."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.groq.com/openai/v1",
        model: str = "qwen/qwen3.6-27b",
        timeout: float = 60.0,
        max_attempts_per_pass: int = 2,
        max_completion_tokens: int = 900,
        max_retry_delay: float = 900.0,
        min_request_interval_seconds: float = 60.0,
    ) -> None:
        if int(max_completion_tokens) != 900:
            raise ValueError("C8_OUTPUT_TOKEN_CEILING_MUST_BE_900")
        if model != "qwen/qwen3.6-27b":
            raise ValueError("C8_MODEL_MUST_BE_QWEN_3_6_27B")
        super().__init__(
            api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            max_attempts_per_pass=max_attempts_per_pass,
            max_completion_tokens=900,
            max_retry_delay=max_retry_delay,
            min_request_interval_seconds=min_request_interval_seconds,
        )

    def parse_with_metadata(self, instruction: str) -> Candidate8ParseResult:
        pass1_messages = [
            {"role": "system", "content": PASS1_SYSTEM_PROMPT_C8},
            {"role": "user", "content": json.dumps({"instruction": instruction}, separators=(",", ":"))},
        ]

        def validate_facts(parsed: Any) -> tuple[LabeledFact, ...]:
            self._validate_action_types_raw(parsed)
            batch = FactBatch.model_validate(parsed)
            grounded = []
            for raw_fact in batch.facts:
                try:
                    grounded_span(instruction, raw_fact.text_span)
                except ValueError:
                    continue
                grounded.append(raw_fact)
            if not grounded:
                raise ValueError("C8_NO_GROUNDED_FACTS")
            labeled = assign_fact_ids(FactBatch(facts=grounded))
            for fact in labeled:
                if fact.kind is FactKind.ACTION and fact.action_type != _action_kind(fact.text_span.quote):
                    raise ValueError("C7_ACTION_TYPE_SPAN_MISMATCH")
            return normalize_candidate8_facts(instruction, labeled).facts

        facts, trace1 = self._run_stage("facts", pass1_messages, validate_facts)
        labeled_payload = [fact.model_dump(mode="json") for fact in facts]
        pass2_messages = [
            {"role": "system", "content": PASS2_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({
                "instruction": instruction,
                "facts": labeled_payload,
                "action_entity_pairs": action_entity_pair_payload(facts),
            }, separators=(",", ":"))},
        ]

        def validate_relation_batch(parsed: Any) -> tuple[RelationBatch, dict[str, C8FactDisposition]]:
            # The model proposal must remain structurally accountable, while the
            # authority-bearing graph is reconstructed from exact source spans.
            # This prevents a single mislabeled role or paraphrased justification
            # from silently changing economic authority.
            Pass2DecisionBatch.model_validate(parsed)
            relations = infer_candidate8_relations(instruction, facts)
            return relations, candidate8_dispositions(instruction, facts, relations)

        try:
            validated, trace2 = self._run_stage("relations", pass2_messages, validate_relation_batch)
            relations, dispositions = validated
        except Candidate7SchemaError as exc:
            relations = infer_candidate8_relations(instruction, facts)
            dispositions = candidate8_dispositions(instruction, facts, relations)
            trace2 = list(exc.provider_trace) + [{
                "stage": "relations",
                "outcome": "deterministic_source_fallback",
                "reason": "MODEL_PROPOSAL_SCHEMA_INVALID",
            }]
        return Candidate8ParseResult(facts, relations, dispositions, tuple(trace1 + trace2))

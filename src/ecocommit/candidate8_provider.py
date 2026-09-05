from __future__ import annotations

import json
from typing import Any

from .candidate7_flat import (
    FactBatch,
    FactKind,
    RelationBatch,
    assign_fact_ids,
    drop_ungrounded_relations,
    grounded_span,
)
from .candidate7_provider import (
    Candidate7ParseResult,
    GroqCandidate7Provider,
    PASS1_SYSTEM_PROMPT,
)
from .candidate7_relation_checklist import Pass2DecisionBatch, action_entity_pair_payload
from .candidate7_structure import _action_kind
from .candidate8_relation_checklist import validate_and_materialize_pass2


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
- ACTION_OBJECT means the grammatical/direct source object or complement of the action. This is a syntactic/source role, not an ontological type. A person or organization can therefore be ACTION_OBJECT when it directly follows the action as its object.
- ACTION_COUNTERPARTY means a separate participant explicitly related to the action outside the direct-object slot, normally introduced by wording such as `to`, `from`, `with`, `through`, `via`, `by`, or `at`.
- Do NOT label a bare source-local direct object as ACTION_COUNTERPARTY merely because it denotes a payee, supplier, contractor, organization, or person.
- Generic role examples: in `Pay the carrier`, `carrier` is ACTION_OBJECT. In `Pay the invoice to the carrier`, `invoice` is ACTION_OBJECT and `carrier` is ACTION_COUNTERPARTY. In `Transfer the refund to the customer`, `refund` is ACTION_OBJECT and `customer` is ACTION_COUNTERPARTY.

The `relations` list is only for non-ACTION×ENTITY relations. Each relation has exactly:
  kind, left, right, justification_span
Allowed relation kinds there:
PREDICATE_SUBJECT, CONSTRAINT_APPLIES_TO, GUARDS_ACTION, BLOCKS_ACTION,
AFTER_COMPLETION, AFTER_SUCCESS, EXCEPTION_TARGET, EXCEPTION_WHEN,
AMBIGUITY_TARGET, ALL_OF, ANY_OF.

Rules:
- ACTION_OBJECT and ACTION_COUNTERPARTY MUST be expressed only through `action_entity_decisions`, never in `relations`.
- `NONE` is a first-class required decision when a supplied ACTION×ENTITY pair has no explicit semantic relationship.
- Every non-NONE justification_span must be an exact verbatim substring of the instruction that establishes the claimed relationship.
- Prefer source-local evidence and preserve grammatical argument structure before semantic-world assumptions.
- You may reference ONLY the existing F#### IDs supplied in the input.
- Do not create any new identifier of any kind.
- Do not output facts, prose, nested Boolean ASTs, groups, or derived semantic objects.
- ALL_OF and ANY_OF classify pairwise logical relationships between existing PREDICATE facts only.
- GUARDS_ACTION means the predicate must explicitly be an authorization condition for the action to execute. Do not infer GUARDS_ACTION from mere proximity, topic similarity, sequence, or co-occurrence.
- BLOCKS_ACTION means the predicate explicitly prevents the action when it holds.
- AFTER_COMPLETION / AFTER_SUCCESS are directed: left is the later/dependent ACTION, right is the prerequisite ACTION.
- EXCEPTION_WHEN is directed: left is PREDICATE, right is EXCEPTION.
- Other directed relation names follow their English reading.
- Emit only source-supported non-ACTION×ENTITY relations in `relations`; an empty `relations` list is equally valid.
- Do not invent a relation merely to avoid an empty `relations` list.
JSON only."""


class GroqCandidate8Provider(GroqCandidate7Provider):
    """Candidate-8 keeps Candidate-7 transport/retry policy but freezes OTPM-safe output at 900."""

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
        super().__init__(
            api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            max_attempts_per_pass=max_attempts_per_pass,
            max_completion_tokens=max_completion_tokens,
            max_retry_delay=max_retry_delay,
            min_request_interval_seconds=min_request_interval_seconds,
        )

    def parse_with_metadata(self, instruction: str) -> Candidate7ParseResult:
        pass1_messages = [
            {"role": "system", "content": PASS1_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"instruction": instruction}, separators=(",", ":"))},
        ]

        def validate_facts(parsed: Any):
            self._validate_action_types_raw(parsed)
            batch = FactBatch.model_validate(parsed)
            labeled = assign_fact_ids(batch)
            for fact in labeled:
                grounded_span(instruction, fact.text_span)
                if fact.kind is FactKind.ACTION and fact.action_type != _action_kind(fact.text_span.quote):
                    raise ValueError("C7_ACTION_TYPE_SPAN_MISMATCH")
            return labeled

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

        def validate_relation_batch(parsed: Any) -> RelationBatch:
            decision_batch = Pass2DecisionBatch.model_validate(parsed)
            return validate_and_materialize_pass2(instruction, facts, decision_batch)

        relations, trace2 = self._run_stage("relations", pass2_messages, validate_relation_batch)
        grounded_relations, grounding_events = drop_ungrounded_relations(instruction, relations)
        trace2.extend({"stage": "relations", **event} for event in grounding_events)
        return Candidate7ParseResult(facts, grounded_relations, tuple(trace1 + trace2))

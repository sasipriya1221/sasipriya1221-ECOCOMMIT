from __future__ import annotations

import json
from typing import Any

from .candidate7_flat import FactBatch, FactKind, RelationBatch, assign_fact_ids, grounded_span
from .candidate7_provider import Candidate7SchemaError
from .candidate7_relation_checklist import Pass2DecisionBatch, action_entity_pair_payload
from .candidate7_structure import _action_kind
from .candidate8_normalize import Candidate8DispositionError
from .candidate8_provider import (
    Candidate8EvidenceError,
    Candidate8ParseResult,
    GroqCandidate8Provider,
    PASS1_SYSTEM_PROMPT_C8,
    PASS2_SYSTEM_PROMPT,
)
from .candidate9_normalize import candidate9_dispositions, infer_candidate9_relations, normalize_candidate9_facts


class GroqCandidate9Provider(GroqCandidate8Provider):
    """Candidate-9 transport and prompts remain byte-identical to Candidate 8."""

    def parse_with_metadata(self, instruction: str) -> Candidate8ParseResult:
        normalization_events: tuple[dict[str, str], ...] = ()
        pass1_messages = [
            {"role": "system", "content": PASS1_SYSTEM_PROMPT_C8},
            {"role": "user", "content": json.dumps({"instruction": instruction}, separators=(",", ":"))},
        ]

        def validate_facts(parsed: Any):
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
                raise ValueError("C9_NO_GROUNDED_FACTS")
            labeled = assign_fact_ids(FactBatch(facts=grounded))
            for fact in labeled:
                if fact.kind is FactKind.ACTION and fact.action_type != _action_kind(fact.text_span.quote):
                    raise ValueError("C7_ACTION_TYPE_SPAN_MISMATCH")
            nonlocal normalization_events
            normalized = normalize_candidate9_facts(instruction, labeled)
            normalization_events = normalized.events
            return normalized.facts

        facts, trace1 = self._run_stage("facts", pass1_messages, validate_facts)
        pass2_messages = [
            {"role": "system", "content": PASS2_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({
                "instruction": instruction,
                "facts": [fact.model_dump(mode="json") for fact in facts],
                "action_entity_pairs": action_entity_pair_payload(facts),
            }, separators=(",", ":"))},
        ]

        def validate_relation_batch(parsed: Any):
            Pass2DecisionBatch.model_validate(parsed)
            relations = infer_candidate9_relations(instruction, facts)
            return relations, candidate9_dispositions(instruction, facts, relations)

        relations: RelationBatch | None = None
        dispositions = {}
        trace2: list[dict[str, Any]] = []
        try:
            try:
                (relations, dispositions), trace2 = self._run_stage(
                    "relations", pass2_messages, validate_relation_batch
                )
            except Candidate7SchemaError as exc:
                trace2 = list(exc.provider_trace) + [{
                    "stage": "relations",
                    "outcome": "deterministic_source_fallback",
                    "reason": "MODEL_PROPOSAL_SCHEMA_INVALID",
                }]
                relations = infer_candidate9_relations(instruction, facts)
                dispositions = candidate9_dispositions(instruction, facts, relations)
        except Candidate8DispositionError as exc:
            raise Candidate8EvidenceError(
                exc.code.replace("C8_", "C9_", 1),
                facts=facts,
                relations=relations,
                dispositions=exc.partial_dispositions,
                normalization_events=normalization_events,
                provider_trace=tuple(trace1 + trace2),
                unresolved_fact=exc.fact,
            ) from exc
        except Exception as exc:
            raise Candidate8EvidenceError(
                str(exc),
                facts=facts,
                relations=relations,
                dispositions=dispositions,
                normalization_events=normalization_events,
                provider_trace=tuple(trace1 + trace2),
            ) from exc
        return Candidate8ParseResult(
            facts, relations, dispositions, tuple(trace1 + trace2), normalization_events
        )

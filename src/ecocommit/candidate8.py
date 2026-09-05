from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .candidate7_compile import compile_graph_v2
from .candidate7_conservation import verify_candidate7_conservation
from .candidate7_flat import LabeledFact, RelationBatch
from .candidate7_provider import Candidate7SchemaError
from .candidate7_structure import C7Graph, build_graph
from .candidate8_logic import C8FactDisposition, C8LogicalAST, build_typed_ast, verify_ast_conservation
from .interpreter import ProviderRequestError


class Candidate8Provider(Protocol):
    def parse_with_metadata(self, instruction: str): ...


@dataclass(frozen=True)
class Candidate8Result:
    status: str
    contract: Any | None
    graph: C7Graph | None
    logical_ast: C8LogicalAST | None
    facts: tuple[LabeledFact, ...]
    relations: RelationBatch | None
    dispositions: tuple[tuple[str, C8FactDisposition], ...]
    blocked_actions: frozenset[str]
    error_code: str | None = None
    provider_trace: tuple[dict[str, Any], ...] = ()


def _empty_result(
    *,
    status: str,
    facts: tuple[LabeledFact, ...],
    relations: RelationBatch | None,
    dispositions: tuple[tuple[str, C8FactDisposition], ...],
    error_code: str,
    trace: tuple[dict[str, Any], ...],
) -> Candidate8Result:
    return Candidate8Result(
        status=status,
        contract=None,
        graph=None,
        logical_ast=None,
        facts=facts,
        relations=relations,
        dispositions=dispositions,
        blocked_actions=frozenset(),
        error_code=error_code,
        provider_trace=trace,
    )


def run_candidate8(instruction: str, provider: Candidate8Provider) -> Candidate8Result:
    facts: tuple[LabeledFact, ...] = ()
    relations: RelationBatch | None = None
    dispositions: tuple[tuple[str, C8FactDisposition], ...] = ()
    trace: tuple[dict[str, Any], ...] = ()
    try:
        parsed = provider.parse_with_metadata(instruction)
        facts = parsed.facts
        relations = parsed.relations
        disposition_map = dict(parsed.dispositions)
        dispositions = tuple(sorted(disposition_map.items(), key=lambda item: item[0]))
        trace = parsed.provider_trace

        logical_ast = build_typed_ast(facts, relations, disposition_map)
        verify_ast_conservation(logical_ast, relations)

        # Existing deterministic Boolean/guard builder, compiler, conservation
        # checker and contract validators retain economic authority.
        active_ids = {fid for fid, disposition in dispositions if disposition is C8FactDisposition.USED}
        active_facts = tuple(fact for fact in facts if fact.id in active_ids)
        active_relations = RelationBatch(relations=[
            relation for relation in relations.relations
            if relation.left in active_ids and relation.right in active_ids
        ])
        graph = build_graph(instruction, active_facts, active_relations)
        contract = compile_graph_v2(graph)
        verify_candidate7_conservation(graph, contract)

        if any(d is C8FactDisposition.IRRELEVANT for _, d in dispositions):
            # Irrelevance is explicit evidence metadata only; it grants no authority.
            pass
        status = "CLARIFICATION_REQUIRED" if graph.blocked_actions else "COMPILED"
        return Candidate8Result(
            status=status,
            contract=contract,
            graph=graph,
            logical_ast=logical_ast,
            facts=facts,
            relations=relations,
            dispositions=dispositions,
            blocked_actions=graph.blocked_actions,
            provider_trace=trace,
        )
    except ProviderRequestError as exc:
        provider_trace = tuple(getattr(exc, "provider_trace", ()) or trace)
        return _empty_result(
            status="PROVIDER_DEFERRED" if exc.transient else "REJECTED",
            facts=facts,
            relations=relations,
            dispositions=dispositions,
            error_code=exc.code,
            trace=provider_trace,
        )
    except Candidate7SchemaError as exc:
        return _empty_result(
            status="REJECTED",
            facts=facts,
            relations=relations,
            dispositions=dispositions,
            error_code=str(exc),
            trace=tuple(exc.provider_trace),
        )
    except Exception as exc:
        return _empty_result(
            status="REJECTED",
            facts=facts,
            relations=relations,
            dispositions=dispositions,
            error_code=str(exc),
            trace=trace,
        )

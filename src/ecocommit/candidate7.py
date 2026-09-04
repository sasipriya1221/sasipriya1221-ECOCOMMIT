from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .candidate7_compile import compile_graph_v2
from .candidate7_conservation import verify_candidate7_conservation
from .candidate7_flat import LabeledFact, RelationBatch
from .candidate7_structure import C7Graph, build_graph
from .interpreter import ProviderRequestError


class Candidate7Provider(Protocol):
    def parse_with_metadata(self, instruction: str): ...


@dataclass(frozen=True)
class Candidate7Result:
    status: str
    contract: Any | None
    graph: C7Graph | None
    facts: tuple[LabeledFact, ...]
    relations: RelationBatch | None
    blocked_actions: frozenset[str]
    error_code: str | None = None
    provider_trace: tuple[dict[str, Any], ...] = ()


def run_candidate7(instruction: str, provider: Candidate7Provider) -> Candidate7Result:
    facts: tuple[LabeledFact, ...] = ()
    relations: RelationBatch | None = None
    trace: tuple[dict[str, Any], ...] = ()
    try:
        parsed = provider.parse_with_metadata(instruction)
        facts = parsed.facts
        relations = parsed.relations
        trace = parsed.provider_trace
        graph = build_graph(instruction, facts, relations)
        contract = compile_graph_v2(graph)
        verify_candidate7_conservation(graph, contract)
        status = "CLARIFICATION_REQUIRED" if graph.blocked_actions else "COMPILED"
        return Candidate7Result(
            status=status,
            contract=contract,
            graph=graph,
            facts=facts,
            relations=relations,
            blocked_actions=graph.blocked_actions,
            provider_trace=trace,
        )
    except ProviderRequestError as exc:
        provider_trace = tuple(getattr(exc, "provider_trace", ()) or trace)
        return Candidate7Result(
            status="PROVIDER_DEFERRED" if exc.transient else "REJECTED",
            contract=None,
            graph=None,
            facts=facts,
            relations=relations,
            blocked_actions=frozenset(),
            error_code=exc.code,
            provider_trace=provider_trace,
        )
    except Exception as exc:
        return Candidate7Result(
            status="REJECTED",
            contract=None,
            graph=None,
            facts=facts,
            relations=relations,
            blocked_actions=frozenset(),
            error_code=str(exc),
            provider_trace=trace,
        )

from __future__ import annotations

import re
from dataclasses import dataclass

from .candidate7_flat import (
    Fact,
    FactBatch,
    FactKind,
    LabeledFact,
    Polarity,
    Relation,
    RelationBatch,
    RelationKind,
    TextSpan,
    assign_fact_ids,
    grounded_span,
    validate_relations,
)
from .candidate8_logic import C8FactDisposition


_CONDITION_MARKER = re.compile(r"\b(only\s+if|unless|if|after)\b", re.I)
_BOOLEAN_SPLIT = re.compile(r"\s+\b(and|or)\b\s+", re.I)
_VAGUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:reasonable|adequate|appropriate)\s+(?:number|quantity|amount)\b", re.I),
    re.compile(r"\b(?:normal|standard|usual|ordinary)(?:\s+[a-z-]+){0,2}\s+budget\b", re.I),
    re.compile(r"\b(?:a\s+)?(?:suitable|appropriate|best)\s+[a-z][a-z-]*\b", re.I),
    re.compile(r"\b(?:high-quality|premium-quality|best-quality)\b", re.I),
    re.compile(r"\baffordable\s+(?:price|cost|rate)\b", re.I),
)
_MONEY_CONSTRAINT = re.compile(
    r"\b(?:exactly|at\s+most|at\s+least|up\s+to|no\s+more\s+than|minimum|maximum)\s+"
    r"(?:₹|(?:rs\.?|inr)\s*)\s*[+-]?(?:\d+(?:,\d{3})*|\d*\.\d+)"
    r"(?:\s*(?:lakh|lakhs|crore|crores))?(?:\s+(?:each|per\s+(?:unit|item)))?",
    re.I,
)
_BARE_MONEY = re.compile(
    r"(?:₹|\b(?:rs\.?|inr)\s*)\s*[+-]?(?:\d+(?:,\d{3})*|\d*\.\d+)"
    r"(?:\s*(?:lakh|lakhs|crore|crores))?",
    re.I,
)
_ACTION_SUCCESS = re.compile(r"\b(?:it|the\s+\w+|[a-z][a-z-]*)\s+(?:succeeds|is\s+completed|was\s+completed)\b", re.I)
_PREDICATE_CUE = re.compile(
    r"\b(?:is|are|was|were|has|have|fails?|approves?|approved|requests?|received|"
    r"signs?|declares?|expires?|expired|cancels?|cancelled|approval|authorization|confirmation|"
    r"low|below|valid|active|complete|completed|succeeds?)\b",
    re.I,
)
_ROLE_PREPOSITION = re.compile(r"\b(to|from|with|through|via|by|at)\s+(?:the\s+)?$", re.I)
_NON_OBJECT_MARKER = re.compile(r"\b(for|if|unless|after|before|because|when|while|during|except)\b", re.I)


@dataclass(frozen=True)
class NormalizedCandidate8Input:
    facts: tuple[LabeledFact, ...]
    events: tuple[dict[str, str], ...]


def _fact_start(instruction: str, fact: LabeledFact) -> int:
    return grounded_span(instruction, fact.text_span)[0]


def _make_fact(
    quote: str,
    kind: FactKind,
    polarity: Polarity = Polarity.POSITIVE,
    action_type: str | None = None,
    *,
    occurrence: int = 1,
) -> Fact:
    return Fact(text_span=TextSpan(quote=quote, occurrence=occurrence), kind=kind, polarity=polarity, action_type=action_type)


def _occurrence_at(instruction: str, quote: str, start: int) -> int:
    occurrence = 0
    cursor = 0
    while cursor <= start:
        found = instruction.find(quote, cursor)
        if found < 0 or found > start:
            break
        occurrence += 1
        if found == start:
            return occurrence
        cursor = found + len(quote)
    raise ValueError("C8_SOURCE_OCCURRENCE_UNRESOLVED")


def _condition_regions(instruction: str) -> list[tuple[int, int, str, str]]:
    """Return source-grounded condition bodies without consuming exception clauses."""
    regions: list[tuple[int, int, str, str]] = []
    for match in _CONDITION_MARKER.finditer(instruction):
        marker = match.group(1).lower().replace("  ", " ")
        # An `if` inside an explicit exception belongs to that exception, not the
        # primary authorization guard.
        prefix_clause = instruction[max(instruction.rfind(";", 0, match.start()), instruction.rfind(",", 0, match.start())) + 1:match.start()]
        if re.search(r"\bexcept\b", prefix_clause, re.I):
            continue
        end = len(instruction)
        for token in (", except", ";", "."):
            pos = instruction.lower().find(token, match.end())
            if pos >= 0:
                end = min(end, pos)
        body_start = match.end()
        while body_start < end and instruction[body_start].isspace():
            body_start += 1
        body_end = end
        while body_end > body_start and instruction[body_end - 1].isspace():
            body_end -= 1
        if body_start < body_end:
            regions.append((body_start, body_end, marker, instruction[body_start:body_end]))
    return regions


def _atomic_condition_spans(instruction: str, start: int, body: str) -> list[tuple[int, str]]:
    pieces: list[tuple[int, str]] = []
    cursor = 0
    for match in _BOOLEAN_SPLIT.finditer(body):
        raw = body[cursor:match.start()]
        local = cursor
        cursor = match.end()
        cleaned = re.sub(r"^\s*either\s+", "", raw, flags=re.I).strip()
        if cleaned:
            offset = raw.lower().find(cleaned.lower())
            pieces.append((start + local + offset, cleaned))
    raw = body[cursor:]
    cleaned = re.sub(r"^\s*either\s+", "", raw, flags=re.I).strip()
    if cleaned:
        offset = raw.lower().find(cleaned.lower())
        pieces.append((start + cursor + offset, cleaned))
    return pieces


def normalize_candidate8_facts(instruction: str, facts: tuple[LabeledFact, ...]) -> NormalizedCandidate8Input:
    """Canonicalize general source grammar before IDs are exposed to pass 2.

    The transformation is source-only and label-free.  It never consumes an
    evaluator result and every added/retyped fact remains an exact source span.
    """
    events: list[dict[str, str]] = []
    staged: list[tuple[int, Fact]] = []
    condition_regions = _condition_regions(instruction)
    action_count = sum(fact.kind is FactKind.ACTION for fact in facts)

    # Atomize model predicates/exceptions inside explicit condition bodies.  A
    # flat atomic fact inventory is required for deterministic Boolean assembly.
    covered_condition_fact_ids: set[str] = set()
    for fact in facts:
        start, end = grounded_span(instruction, fact.text_span)
        for region_start, region_end, marker, _ in condition_regions:
            inside_body = start >= region_start and end <= region_end
            includes_marker = start < region_start and end >= region_end
            if (inside_body or includes_marker) and fact.kind in {FactKind.PREDICATE, FactKind.EXCEPTION}:
                covered_condition_fact_ids.add(fact.id)
                events.append({"outcome": "condition_fact_rebuilt", "fact_id": fact.id, "marker": marker})
                break

    for fact in facts:
        if fact.id in covered_condition_fact_ids:
            continue
        start, _ = grounded_span(instruction, fact.text_span)
        quote = fact.text_span.quote
        kind = fact.kind
        polarity = fact.polarity

        # A model may absorb an explicit condition tail into the preceding
        # entity (for example, ``the customer after finance approves``). Keep
        # only the source-local entity portion; the condition body is rebuilt
        # independently below. This is grammar-based and does not consult gold.
        crossing_region = next(
            (
                (region_start, marker)
                for region_start, _region_end, marker, _body in condition_regions
                if kind is FactKind.ENTITY and start < region_start < end
            ),
            None,
        )
        if crossing_region is not None:
            region_start, marker = crossing_region
            marker_start = instruction.lower().rfind(marker, start, region_start)
            if marker_start >= start:
                entity_quote = instruction[start:marker_start].rstrip()
                if entity_quote:
                    quote = entity_quote
                    events.append({"outcome": "condition_tail_removed_from_entity", "fact_id": fact.id})

        if kind is FactKind.CONSTRAINT and not _BARE_MONEY.search(quote) and re.search(r"\b(?:budget|affordable|reasonable)\b", quote, re.I):
            kind = FactKind.AMBIGUITY
            events.append({"outcome": "vague_constraint_retyped", "fact_id": fact.id})
        if kind is FactKind.PREDICATE and re.search(r"\b(?:not|does\s+not|do\s+not|is\s+not|are\s+not)\b", quote, re.I):
            polarity = Polarity.NEGATED
        # ``for completed route`` and similar trailing execution context is a
        # nominal provenance/context phrase, not an authorization predicate.
        # Retyping it as ENTITY allows the explicit disposition layer to keep
        # it out of the authority graph without weakening predicate handling.
        if kind is FactKind.PREDICATE and re.search(r"\bfor\s+(?:the\s+)?$", instruction[:start], re.I):
            kind = FactKind.ENTITY
            events.append({"outcome": "trailing_for_context_retyped", "fact_id": fact.id})
        nominal_after = re.fullmatch(r"after\s+(.+)", quote.strip(), re.I) if kind is FactKind.PREDICATE else None
        if nominal_after is not None and not _PREDICATE_CUE.search(nominal_after.group(1)):
            context_quote = nominal_after.group(1)
            context_start = start + quote.lower().find(context_quote.lower())
            staged.append((context_start, _make_fact(context_quote, FactKind.ENTITY, occurrence=_occurrence_at(instruction, context_quote, context_start))))
            events.append({"outcome": "nominal_after_context_retyped", "fact_id": fact.id})
            continue
        staged.append((start, _make_fact(quote, kind, polarity, fact.action_type, occurrence=fact.text_span.occurrence)))

    # A bare number between an action and its following object is a quantity,
    # not a monetary/temporal constraint. Fold it into the exact object span so
    # the existing deterministic quantity compiler can preserve it.
    quantity_constraints = [
        (start, fact)
        for start, fact in staged
        if re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", fact.text_span.quote)
        and fact.kind is FactKind.CONSTRAINT
    ]
    for quantity_start, quantity_fact in quantity_constraints:
        quantity_end = quantity_start + len(quantity_fact.text_span.quote)
        following_entities = [
            (entity_start, entity)
            for entity_start, entity in staged
            if entity.kind is FactKind.ENTITY
            and entity_start >= quantity_end
            and not instruction[quantity_end:entity_start].strip()
        ]
        if not following_entities:
            continue
        entity_start, entity = min(following_entities, key=lambda item: item[0])
        entity_end = entity_start + len(entity.text_span.quote)
        combined = instruction[quantity_start:entity_end]
        staged = [
            (item_start, item)
            for item_start, item in staged
            if item is not quantity_fact and item is not entity
        ]
        staged.append((quantity_start, _make_fact(
            combined,
            FactKind.ENTITY,
            occurrence=_occurrence_at(instruction, combined, quantity_start),
        )))
        events.append({"outcome": "bare_quantity_folded_into_object", "fact_id": quantity_fact.text_span.quote})

    # Split compound monetary constraints so contradictory bounds cannot be
    # hidden inside a single fact.
    money_matches = list(_MONEY_CONSTRAINT.finditer(instruction))
    if money_matches:
        staged = [
            (start, fact) for start, fact in staged
            if fact.kind is not FactKind.CONSTRAINT or not _BARE_MONEY.search(fact.text_span.quote)
        ]
        for match in money_matches:
            staged.append((match.start(), _make_fact(match.group(0), FactKind.CONSTRAINT, occurrence=_occurrence_at(instruction, match.group(0), match.start()))))
    elif (bare := _BARE_MONEY.search(instruction)) is not None and not any(f.kind is FactKind.CONSTRAINT for _, f in staged):
        staged.append((bare.start(), _make_fact(bare.group(0), FactKind.CONSTRAINT, occurrence=_occurrence_at(instruction, bare.group(0), bare.start()))))

    # Rebuild all primary condition atoms from exact source substrings.
    for region_start, _region_end, marker, body in condition_regions:
        # Action-success/completion clauses are represented by action dependency
        # edges, not duplicate authorization guards.
        if _ACTION_SUCCESS.search(body) and action_count > 1:
            continue
        if marker == "after" and not _PREDICATE_CUE.search(body):
            continue
        for atom_start, atom in _atomic_condition_spans(instruction, region_start, body):
            polarity = Polarity.NEGATED if re.search(r"\b(?:not|does\s+not|do\s+not|is\s+not|are\s+not)\b", atom, re.I) else Polarity.POSITIVE
            staged.append((atom_start, _make_fact(atom, FactKind.PREDICATE, polarity, occurrence=_occurrence_at(instruction, atom, atom_start))))

    # Material vagueness is explicit even when the model embedded the cue in an
    # entity rather than emitting a separate ambiguity fact.
    existing_ambiguity_quotes = {f.text_span.quote.lower() for _, f in staged if f.kind is FactKind.AMBIGUITY}
    for pattern in _VAGUE_PATTERNS:
        for match in pattern.finditer(instruction):
            quote = match.group(0)
            if quote.lower() not in existing_ambiguity_quotes:
                staged.append((match.start(), _make_fact(quote, FactKind.AMBIGUITY, occurrence=_occurrence_at(instruction, quote, match.start()))))
                existing_ambiguity_quotes.add(quote.lower())
                events.append({"outcome": "explicit_ambiguity_added", "quote_sha_hint": str(len(quote))})

    # Deduplicate only identical semantic facts. Overlapping ENTITY/AMBIGUITY
    # facts are intentional because they carry distinct authority semantics.
    deduped: list[tuple[int, Fact]] = []
    seen: set[tuple[int, str, FactKind, Polarity, str | None]] = set()
    for start, fact in sorted(staged, key=lambda item: (item[0], item[1].kind.value, item[1].text_span.quote)):
        key = (start, fact.text_span.quote, fact.kind, fact.polarity, fact.action_type)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((start, fact))

    normalized = assign_fact_ids(FactBatch(facts=[fact for _, fact in deduped]))
    return NormalizedCandidate8Input(normalized, tuple(events))


def _cover_span(instruction: str, left: LabeledFact, right: LabeledFact) -> str:
    lstart, lend = grounded_span(instruction, left.text_span)
    rstart, rend = grounded_span(instruction, right.text_span)
    return instruction[min(lstart, rstart):max(lend, rend)]


def _nearest_preceding_action(instruction: str, actions: list[LabeledFact], fact: LabeledFact) -> LabeledFact | None:
    start = _fact_start(instruction, fact)
    preceding = [action for action in actions if _fact_start(instruction, action) <= start]
    return max(preceding, key=lambda action: _fact_start(instruction, action)) if preceding else None


def infer_candidate8_relations(instruction: str, facts: tuple[LabeledFact, ...]) -> RelationBatch:
    """Build a conservative, source-grounded relation graph from typed facts."""
    ordered = sorted(facts, key=lambda fact: (_fact_start(instruction, fact), fact.id))
    actions = [fact for fact in ordered if fact.kind is FactKind.ACTION]
    entities = [fact for fact in ordered if fact.kind is FactKind.ENTITY]
    constraints = [fact for fact in ordered if fact.kind is FactKind.CONSTRAINT]
    predicates = [fact for fact in ordered if fact.kind is FactKind.PREDICATE]
    exceptions = [fact for fact in ordered if fact.kind is FactKind.EXCEPTION]
    relations: list[Relation] = []

    def add(kind: RelationKind, left: LabeledFact, right: LabeledFact) -> None:
        key = (kind, left.id, right.id)
        if any((r.kind, r.left, r.right) == key for r in relations):
            return
        relations.append(Relation(kind=kind, left=left.id, right=right.id, justification_span=_cover_span(instruction, left, right)))

    # Roles are determined from source grammar, not the entity's ontology.
    for index, action in enumerate(actions):
        astart, aend = grounded_span(instruction, action.text_span)
        next_start = _fact_start(instruction, actions[index + 1]) if index + 1 < len(actions) else len(instruction)
        candidates: list[tuple[int, LabeledFact, str]] = []
        for entity in entities:
            estart, _ = grounded_span(instruction, entity.text_span)
            if estart < astart or estart >= next_start:
                continue
            prefix = instruction[astart:estart]
            immediate = instruction[aend:estart] if estart >= aend else instruction[astart:estart]
            if _ROLE_PREPOSITION.search(prefix):
                add(RelationKind.ACTION_COUNTERPARTY, action, entity)
                continue
            if _NON_OBJECT_MARKER.search(immediate):
                continue
            candidates.append((estart, entity, immediate))
        if candidates:
            add(RelationKind.ACTION_OBJECT, action, min(candidates, key=lambda item: item[0])[1])

    for constraint in constraints:
        target = _nearest_preceding_action(instruction, actions, constraint)
        if target is not None:
            add(RelationKind.CONSTRAINT_APPLIES_TO, constraint, target)

    # Explicit sequencing is action-to-action. It must not become a duplicate
    # guard merely because the source also contains the word `after`.
    dependency_predicates: set[str] = set()
    for index in range(1, len(actions)):
        previous, current = actions[index - 1], actions[index]
        pstart, _ = grounded_span(instruction, previous.text_span)
        cstart, _ = grounded_span(instruction, current.text_span)
        bridge = instruction[pstart:cstart]
        tail = instruction[cstart:]
        if re.search(r"\bthen\b", bridge, re.I) or re.search(r";\s*after\b", bridge, re.I):
            kind = RelationKind.AFTER_SUCCESS if re.search(r"\b(?:succeeds|successful|approved)\b", bridge + tail, re.I) else RelationKind.AFTER_COMPLETION
            add(kind, current, previous)
            previous_terms = set(re.findall(r"[a-z0-9]+", previous.text_span.quote.lower()))
            for predicate in predicates:
                ptext = predicate.text_span.quote.lower()
                ptokens = set(re.findall(r"[a-z0-9]+", ptext))
                if re.search(r"\b(?:succeeds|completed)\b", ptext) and (previous_terms & ptokens or re.search(r"\bit\b", ptext)):
                    dependency_predicates.add(predicate.id)

    predicate_targets: dict[str, LabeledFact] = {}
    predicate_markers: dict[str, str] = {}
    exception_regions = [(grounded_span(instruction, exc.text_span), exc) for exc in exceptions]
    for predicate in predicates:
        pstart_full, pend_full = grounded_span(instruction, predicate.text_span)
        contained_entities = [
            entity for entity in entities
            if pstart_full <= grounded_span(instruction, entity.text_span)[0]
            and grounded_span(instruction, entity.text_span)[1] <= pend_full
        ]
        if contained_entities:
            add(RelationKind.PREDICATE_SUBJECT, predicate, min(contained_entities, key=lambda item: _fact_start(instruction, item)))
        if predicate.id in dependency_predicates:
            continue
        pstart = pstart_full
        containing_exception = next((exc for (start_end, exc) in exception_regions if start_end[0] <= pstart <= start_end[1]), None)
        if containing_exception is not None:
            add(RelationKind.EXCEPTION_WHEN, predicate, containing_exception)
            continue
        target = _nearest_preceding_action(instruction, actions, predicate)
        if target is None:
            continue
        tstart, _ = grounded_span(instruction, target.text_span)
        prefix = instruction[tstart:pstart]
        marker_matches = list(_CONDITION_MARKER.finditer(prefix))
        if not marker_matches:
            continue
        marker = marker_matches[-1].group(1).lower()
        if marker == "unless":
            add(RelationKind.BLOCKS_ACTION, predicate, target)
        else:
            add(RelationKind.GUARDS_ACTION, predicate, target)
        predicate_targets[predicate.id] = target
        predicate_markers[predicate.id] = marker

    # Recover Boolean structure from exact connectives between atomic spans.
    for target in actions:
        guarded = sorted(
            [p for p in predicates if predicate_targets.get(p.id) == target],
            key=lambda p: _fact_start(instruction, p),
        )
        for left, right in zip(guarded, guarded[1:]):
            _, lend = grounded_span(instruction, left.text_span)
            rstart, _ = grounded_span(instruction, right.text_span)
            connector = instruction[lend:rstart]
            kind = RelationKind.ANY_OF if re.search(r"\bor\b", connector, re.I) else RelationKind.ALL_OF
            add(kind, left, right)

    for exception in exceptions:
        target = _nearest_preceding_action(instruction, actions, exception)
        if target is not None:
            add(RelationKind.EXCEPTION_TARGET, exception, target)

    result = RelationBatch(relations=relations)
    validate_relations(facts, result)
    return result


def candidate8_dispositions(
    instruction: str,
    facts: tuple[LabeledFact, ...],
    relations: RelationBatch,
) -> dict[str, C8FactDisposition]:
    refs = {r.left for r in relations.relations} | {r.right for r in relations.relations}
    dispositions: dict[str, C8FactDisposition] = {}
    for fact in facts:
        if fact.id in refs or fact.kind in {FactKind.ACTION, FactKind.AMBIGUITY}:
            dispositions[fact.id] = C8FactDisposition.USED
            continue
        start, _ = grounded_span(instruction, fact.text_span)
        prefix = instruction[:start]
        if fact.kind is FactKind.ENTITY and re.search(r"\b(?:for|after|about)\s+(?:the\s+)?$", prefix, re.I):
            dispositions[fact.id] = C8FactDisposition.IRRELEVANT
            continue
        if ";" in prefix:
            clause = prefix[prefix.rfind(";") + 1:] + fact.text_span.quote
            if not re.search(r"\b(?:if|unless|after)\b", clause, re.I):
                dispositions[fact.id] = C8FactDisposition.IRRELEVANT
                continue
        if fact.kind is FactKind.PREDICATE and _ACTION_SUCCESS.search(fact.text_span.quote):
            dispositions[fact.id] = C8FactDisposition.IRRELEVANT
            continue
        raise ValueError(f"C8_UNRESOLVED_{fact.kind.value}_DISPOSITION")
    return dispositions

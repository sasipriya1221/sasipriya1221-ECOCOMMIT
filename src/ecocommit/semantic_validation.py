from __future__ import annotations

from dataclasses import dataclass

from .semantic_ir import (
    ConstraintKind,
    SemanticIR,
    SpanSource,
    normalize_money,
    normalize_quantity,
)


@dataclass(frozen=True)
class SemanticFinding:
    code: str
    location: str
    message: str


class SemanticValidationError(ValueError):
    def __init__(self, findings: list[SemanticFinding]):
        self.findings = tuple(findings)
        super().__init__(findings[0].code if findings else "IR_INVALID")


def refs_expr(expr) -> set[str]:
    if expr.op == "ATOM":
        return {expr.predicate}
    if expr.op == "NOT":
        return refs_expr(expr.arg)
    result: set[str] = set()
    for arg in expr.args:
        result |= refs_expr(arg)
    return result


def canonical_expr(expr) -> str:
    if expr.op == "ATOM":
        return f"ATOM({expr.predicate})"
    if expr.op == "NOT":
        inner = expr.arg
        if inner.op == "NOT":
            return canonical_expr(inner.arg)
        return f"NOT({canonical_expr(inner)})"
    children: list[str] = []
    for arg in expr.args:
        child = canonical_expr(arg)
        prefix = f"{expr.op}("
        if child.startswith(prefix) and child.endswith(")"):
            children.extend(child[len(prefix):-1].split(","))
        else:
            children.append(child)
    return f"{expr.op}({','.join(sorted(set(children)))})"


def _contains_direct_contradiction(expr) -> bool:
    if expr.op == "NOT" or expr.op == "ATOM":
        return False if expr.op == "ATOM" else _contains_direct_contradiction(expr.arg)
    if expr.op == "OR":
        return any(_contains_direct_contradiction(arg) for arg in expr.args)
    positive: set[str] = set()
    negative: set[str] = set()
    for arg in expr.args:
        if arg.op == "ATOM":
            positive.add(arg.predicate)
        elif arg.op == "NOT" and arg.arg.op == "ATOM":
            negative.add(arg.arg.predicate)
        elif _contains_direct_contradiction(arg):
            return True
    return bool(positive & negative)


def _validate_source(instruction: str, source: SpanSource, location: str, findings: list[SemanticFinding]) -> None:
    start = -1
    cursor = 0
    for _ in range(source.occurrence):
        start = instruction.find(source.quote, cursor)
        if start < 0:
            findings.append(SemanticFinding("IR_SOURCE_UNGROUNDED", location, "SPAN quote/occurrence is not verbatim input"))
            return
        cursor = start + len(source.quote)


def validate_semantic_ir(ir: SemanticIR, instruction: str) -> None:
    findings: list[SemanticFinding] = []
    groups = [ir.entities, ir.actions, ir.constraints, ir.predicates, ir.guards, ir.dependencies, ir.exceptions, ir.ambiguities]
    ids = [item.id for group in groups for item in group]
    if len(ids) != len(set(ids)):
        findings.append(SemanticFinding("IR_DUPLICATE_ID", "root", "IDs must be globally unique"))

    entities = {x.id for x in ir.entities}
    actions = {x.id for x in ir.actions}
    constraints = {x.id for x in ir.constraints}
    predicates = {x.id for x in ir.predicates}
    guards = {x.id for x in ir.guards}
    dependencies = {x.id for x in ir.dependencies}

    for entity in ir.entities:
        _validate_source(instruction, entity.source, entity.id, findings)

    for action in ir.actions:
        _validate_source(instruction, action.source, action.id, findings)
        if action.object not in entities:
            findings.append(SemanticFinding("IR_DANGLING_REFERENCE", action.id, "unknown action object"))
        if action.counterparty and action.counterparty not in entities:
            findings.append(SemanticFinding("IR_DANGLING_REFERENCE", action.id, "unknown action counterparty"))
        if action.quantity:
            _validate_source(instruction, action.quantity.source, f"{action.id}.quantity", findings)
            try:
                normalize_quantity(action.quantity.raw_value, action.quantity.raw_unit)
            except ValueError as exc:
                findings.append(SemanticFinding(str(exc), f"{action.id}.quantity", "invalid quantity or unit"))

    normalized_constraints: dict[str, list[tuple[ConstraintKind, object]]] = {a: [] for a in actions}
    for constraint in ir.constraints:
        _validate_source(instruction, constraint.money.source, constraint.id, findings)
        if constraint.action not in actions:
            findings.append(SemanticFinding("IR_DANGLING_REFERENCE", constraint.id, "unknown constraint action"))
            continue
        try:
            amount, currency = normalize_money(constraint.money.raw_amount, constraint.money.raw_currency)
            normalized_constraints[constraint.action].append((constraint.kind, (amount, currency)))
        except ValueError as exc:
            findings.append(SemanticFinding(str(exc), constraint.id, "invalid monetary constraint"))

    for action_id, rows in normalized_constraints.items():
        by_currency: dict[str, dict[ConstraintKind, list]] = {}
        for kind, (amount, currency) in rows:
            by_currency.setdefault(currency, {}).setdefault(kind, []).append(amount)
        for currency, kinds in by_currency.items():
            exact = kinds.get(ConstraintKind.EXACT_TOTAL_COST, [])
            minimum = kinds.get(ConstraintKind.MIN_TOTAL_COST, [])
            maxima = kinds.get(ConstraintKind.MAX_TOTAL_COST, [])
            if exact and len(set(exact)) > 1:
                findings.append(SemanticFinding("IR_CONTRADICTORY_CONSTRAINTS", action_id, f"multiple exact {currency} amounts disagree"))
            if exact and maxima and exact[0] > min(maxima):
                findings.append(SemanticFinding("IR_CONTRADICTORY_CONSTRAINTS", action_id, "exact amount exceeds maximum"))
            if exact and minimum and exact[0] < max(minimum):
                findings.append(SemanticFinding("IR_CONTRADICTORY_CONSTRAINTS", action_id, "exact amount is below minimum"))
            if maxima and minimum and max(minimum) > min(maxima):
                findings.append(SemanticFinding("IR_CONTRADICTORY_CONSTRAINTS", action_id, "minimum exceeds maximum"))

    for predicate in ir.predicates:
        _validate_source(instruction, predicate.source, predicate.id, findings)
        if predicate.subject not in entities:
            findings.append(SemanticFinding("IR_DANGLING_REFERENCE", predicate.id, "unknown predicate subject"))

    for guard in ir.guards:
        _validate_source(instruction, guard.source, guard.id, findings)
        if guard.action not in actions:
            findings.append(SemanticFinding("IR_DANGLING_REFERENCE", guard.id, "unknown guard action"))
        if not refs_expr(guard.expr) <= predicates:
            findings.append(SemanticFinding("IR_DANGLING_REFERENCE", guard.id, "unknown predicate in Boolean AST"))
        if _contains_direct_contradiction(guard.expr):
            findings.append(SemanticFinding("IR_GUARD_CONTRADICTION", guard.id, "guard contains an explicit P AND NOT(P) contradiction"))

    graph = {action: set() for action in actions}
    for dep in ir.dependencies:
        _validate_source(instruction, dep.source, dep.id, findings)
        if dep.action not in actions or dep.prerequisite_action not in actions:
            findings.append(SemanticFinding("IR_DANGLING_REFERENCE", dep.id, "unknown dependency action"))
            continue
        if dep.action == dep.prerequisite_action:
            findings.append(SemanticFinding("IR_SELF_DEPENDENCY", dep.id, "self dependency"))
        graph[dep.action].add(dep.prerequisite_action)

    visiting: set[str] = set()
    done: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in done:
            return False
        visiting.add(node)
        cycle = any(visit(other) for other in graph[node])
        visiting.remove(node)
        done.add(node)
        return cycle

    if any(visit(action) for action in graph if action not in done):
        findings.append(SemanticFinding("IR_DEPENDENCY_CYCLE", "dependencies", "dependency graph contains a cycle"))

    for exception in ir.exceptions:
        _validate_source(instruction, exception.source, exception.id, findings)
        valid_targets = {"ACTION": actions, "GUARD": guards, "CONSTRAINT": constraints}[exception.target.kind]
        if exception.target.id not in valid_targets:
            findings.append(SemanticFinding("IR_EXCEPTION_TARGET_INVALID", exception.id, "invalid exception target"))
        if not refs_expr(exception.when) <= predicates:
            findings.append(SemanticFinding("IR_DANGLING_REFERENCE", exception.id, "unknown predicate in exception"))
        if exception.effect.effect == "ADD_MONETARY_ALLOWANCE":
            if exception.target.kind != "CONSTRAINT":
                findings.append(SemanticFinding("IR_EXCEPTION_SCOPE_INVALID", exception.id, "monetary allowance must target a constraint"))
            try:
                normalize_money(exception.effect.money.raw_amount, exception.effect.money.raw_currency)
            except ValueError as exc:
                findings.append(SemanticFinding(str(exc), f"{exception.id}.allowance", "invalid allowance"))

    for ambiguity in ir.ambiguities:
        target = ambiguity.target
        if isinstance(ambiguity.source, SpanSource):
            _validate_source(instruction, ambiguity.source, ambiguity.id, findings)
        reference_sets = {
            "ACTION_FIELD": actions,
            "PREDICATE": predicates,
            "GUARD": guards,
            "CONSTRAINT": constraints,
            "COUNTERPARTY": entities,
            "DEPENDENCY": dependencies,
        }
        if target.kind in reference_sets and (not target.id or target.id not in reference_sets[target.kind]):
            findings.append(SemanticFinding("IR_DANGLING_REFERENCE", ambiguity.id, "ambiguity target does not exist"))
        if target.kind == "ACTION_FIELD" and not target.field:
            findings.append(SemanticFinding("IR_AMBIGUITY_TARGET_INVALID", ambiguity.id, "ACTION_FIELD ambiguity requires field"))
        if target.kind == "PRESENTATION" and target.id is not None:
            findings.append(SemanticFinding("IR_AMBIGUITY_TARGET_INVALID", ambiguity.id, "PRESENTATION ambiguity must not target economic semantic IDs"))

    if findings:
        raise SemanticValidationError(findings)


def blocked_actions(ir: SemanticIR) -> set[str]:
    actions = {action.id for action in ir.actions}
    blocked: set[str] = set()
    for ambiguity in ir.ambiguities:
        target = ambiguity.target
        # Materiality is deterministic. PRESENTATION is the only explicitly
        # non-economic target category. Any unknown/unresolvable mapping blocks all.
        if target.kind == "PRESENTATION":
            continue
        if target.kind == "ACTION_FIELD" and target.id in actions:
            blocked.add(target.id)
        elif target.kind == "COUNTERPARTY":
            blocked |= {a.id for a in ir.actions if a.counterparty == target.id}
        elif target.kind == "PREDICATE":
            blocked |= {g.action for g in ir.guards if target.id in refs_expr(g.expr)}
            blocked |= {
                a.id for a in ir.actions
                for x in ir.exceptions
                if target.id in refs_expr(x.when) and x.target.kind == "ACTION" and x.target.id == a.id
            }
        elif target.kind == "GUARD":
            blocked |= {g.action for g in ir.guards if g.id == target.id}
        elif target.kind == "CONSTRAINT":
            blocked |= {c.action for c in ir.constraints if c.id == target.id}
        elif target.kind == "DEPENDENCY":
            blocked |= {d.action for d in ir.dependencies if d.id == target.id}
        else:
            blocked |= actions

    changed = True
    while changed:
        before = len(blocked)
        blocked |= {dep.action for dep in ir.dependencies if dep.prerequisite_action in blocked}
        changed = len(blocked) != before
    return blocked

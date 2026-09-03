from __future__ import annotations
from dataclasses import dataclass
from .semantic_ir import SemanticIR, SpanSource

@dataclass(frozen=True)
class SemanticFinding:
    code:str; location:str; message:str
class SemanticValidationError(ValueError):
    def __init__(self, findings:list[SemanticFinding]): self.findings=tuple(findings); super().__init__(findings[0].code if findings else "IR_INVALID")

def _refs_expr(expr):
    if expr.op=="ATOM": return {expr.predicate}
    if expr.op=="NOT": return _refs_expr(expr.arg)
    out=set()
    for a in expr.args: out |= _refs_expr(a)
    return out

def validate_semantic_ir(ir:SemanticIR,instruction:str)->None:
    f=[]; groups=[ir.entities,ir.actions,ir.constraints,ir.predicates,ir.guards,ir.dependencies,ir.exceptions,ir.ambiguities]
    ids=[x.id for g in groups for x in g]
    if len(ids)!=len(set(ids)): f.append(SemanticFinding("IR_DUPLICATE_ID","root","IDs must be globally unique"))
    entities={x.id for x in ir.entities}; actions={x.id for x in ir.actions}; constraints={x.id for x in ir.constraints}; predicates={x.id for x in ir.predicates}; guards={x.id for x in ir.guards}; deps={x.id for x in ir.dependencies}
    def span(src,loc):
        if isinstance(src,SpanSource) and src.quote not in instruction: f.append(SemanticFinding("IR_SOURCE_UNGROUNDED",loc,"SPAN quote is not verbatim input"))
    for e in ir.entities: span(e.source,e.id)
    for a in ir.actions:
        span(a.source,a.id)
        if a.object not in entities: f.append(SemanticFinding("IR_DANGLING_REFERENCE",a.id,"unknown object"))
        if a.counterparty and a.counterparty not in entities: f.append(SemanticFinding("IR_DANGLING_REFERENCE",a.id,"unknown counterparty"))
        if a.quantity: span(a.quantity.source,a.id+".quantity")
    for c in ir.constraints:
        span(c.money.source,c.id)
        if c.action not in actions:f.append(SemanticFinding("IR_DANGLING_REFERENCE",c.id,"unknown action"))
    for p in ir.predicates:
        span(p.source,p.id)
        if p.subject not in entities:f.append(SemanticFinding("IR_DANGLING_REFERENCE",p.id,"unknown subject"))
    for g in ir.guards:
        span(g.source,g.id)
        if g.action not in actions:f.append(SemanticFinding("IR_DANGLING_REFERENCE",g.id,"unknown action"))
        if not _refs_expr(g.expr)<=predicates:f.append(SemanticFinding("IR_DANGLING_REFERENCE",g.id,"unknown predicate in Boolean AST"))
    graph={a:set() for a in actions}
    for d in ir.dependencies:
        span(d.source,d.id)
        if d.action not in actions or d.prerequisite_action not in actions:f.append(SemanticFinding("IR_DANGLING_REFERENCE",d.id,"unknown dependency action"));continue
        if d.action==d.prerequisite_action:f.append(SemanticFinding("IR_SELF_DEPENDENCY",d.id,"self dependency"))
        graph[d.action].add(d.prerequisite_action)
    visiting=set(); done=set()
    def visit(n):
        if n in visiting:return True
        if n in done:return False
        visiting.add(n)
        cyc=any(visit(x) for x in graph[n]); visiting.remove(n); done.add(n); return cyc
    if any(visit(a) for a in graph if a not in done):f.append(SemanticFinding("IR_DEPENDENCY_CYCLE","dependencies","cycle"))
    for x in ir.exceptions:
        span(x.source,x.id)
        valid={"ACTION":actions,"GUARD":guards,"CONSTRAINT":constraints}[x.target.kind]
        if x.target.id not in valid:f.append(SemanticFinding("IR_EXCEPTION_TARGET_INVALID",x.id,"invalid target"))
        if not _refs_expr(x.when)<=predicates:f.append(SemanticFinding("IR_DANGLING_REFERENCE",x.id,"unknown predicate in exception"))
        if x.effect.effect=="ADD_MONETARY_ALLOWANCE" and x.target.kind!="CONSTRAINT":f.append(SemanticFinding("IR_EXCEPTION_SCOPE_INVALID",x.id,"allowance must target constraint"))
    if f: raise SemanticValidationError(f)

def blocked_actions(ir:SemanticIR)->set[str]:
    actions={a.id for a in ir.actions}; blocked=set()
    for u in ir.ambiguities:
        t=u.target
        if t.kind=="NON_MATERIAL": continue
        if t.kind=="ACTION_FIELD" and t.id in actions: blocked.add(t.id)
        elif t.kind=="COUNTERPARTY":
            blocked|={a.id for a in ir.actions if a.counterparty==t.id}
        elif t.kind=="PREDICATE": blocked|={g.action for g in ir.guards if t.id in _refs_expr(g.expr)}
        elif t.kind=="GUARD": blocked|={g.action for g in ir.guards if g.id==t.id}
        elif t.kind=="CONSTRAINT": blocked|={c.action for c in ir.constraints if c.id==t.id}
        elif t.kind=="DEPENDENCY": blocked|={d.action for d in ir.dependencies if d.id==t.id}
        else: blocked|=actions
    changed=True
    while changed:
        before=len(blocked)
        blocked|={d.action for d in ir.dependencies if d.prerequisite_action in blocked}
        changed=len(blocked)!=before
    return blocked

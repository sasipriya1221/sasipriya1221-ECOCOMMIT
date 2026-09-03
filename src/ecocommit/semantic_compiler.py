from __future__ import annotations
from dataclasses import dataclass
from .contracts import EconomicIntentContract,EconomicClause,ClauseType,Provenance,Hardness,SourceSpan
from .semantic_ir import SemanticIR, normalize_money
from .semantic_validation import validate_semantic_ir, blocked_actions

@dataclass(frozen=True)
class ConservationEdge: source_id:str; destination_id:str; relationship:str
class ConservationError(RuntimeError): pass

def _span(instruction,src):
    start=instruction.find(src.quote)
    if start<0: raise ConservationError("IR_SOURCE_UNGROUNDED")
    return SourceSpan(text=src.quote,start=start,end=start+len(src.quote))
def _clause(cid,typ,val,instruction,src,*,depends=(),exceptions=()):
    return EconomicClause(clause_id=cid,clause_type=typ,normalized_value=val,source_span=_span(instruction,src),provenance=Provenance.EXPLICIT_USER,materiality=1.0,confidence=1.0,hardness=Hardness.HARD,depends_on=list(depends),exception_to=list(exceptions))

def compile_contract(ir:SemanticIR,instruction:str)->tuple[EconomicIntentContract,tuple[ConservationEdge,...],set[str]]:
    validate_semantic_ir(ir,instruction); clauses=[]; edges=[]
    entity_clause={}
    for e in ir.entities:
        typ=ClauseType.COUNTERPARTY if e.kind.value=="COUNTERPARTY" else ClauseType.PRODUCT
        cid="ir_"+e.id; clauses.append(_clause(cid,typ,e.text,instruction,e.source)); entity_clause[e.id]=cid; edges.append(ConservationEdge(e.id,cid,"entity"))
    action_anchor={}
    for a in ir.actions:
        # Existing contract has no ACTION clause; authorization is the deterministic action anchor.
        cid="ir_"+a.id; action_anchor[a.id]=cid
        clauses.append(_clause(cid,ClauseType.AUTHORIZATION,a.kind.value,instruction,a.source)); edges.append(ConservationEdge(a.id,cid,"action"))
        if a.quantity:
            qid=cid+"_quantity"; clauses.append(_clause(qid,ClauseType.QUANTITY,f"{a.quantity.raw_value} {a.quantity.raw_unit}",instruction,a.quantity.source)); edges.append(ConservationEdge(a.id,qid,"quantity"))
    for c in ir.constraints:
        amount,currency=normalize_money(c.money.raw_amount,c.money.raw_currency); cid="ir_"+c.id
        val=f"{c.kind.value}:{currency}:{amount}"; clauses.append(_clause(cid,ClauseType.AMOUNT,val,instruction,c.money.source,depends=(action_anchor[c.action],))); edges.append(ConservationEdge(c.id,cid,"constraint"))
    pred_clause={}
    for p in ir.predicates:
        cid="ir_"+p.id; pred_clause[p.id]=cid
        val=":".join(x for x in (p.kind.value,p.operator.value,p.attribute,p.value) if x)
        clauses.append(_clause(cid,ClauseType.CONDITION,val,instruction,p.source)); edges.append(ConservationEdge(p.id,cid,"predicate"))
    def refs(expr):
        if expr.op=="ATOM":return [expr.predicate]
        if expr.op=="NOT":return refs(expr.arg)
        out=[]
        for x in expr.args:out+=refs(x)
        return out
    def canon(expr):
        if expr.op=="ATOM":return f"ATOM({expr.predicate})"
        if expr.op=="NOT":return f"NOT({canon(expr.arg)})"
        return f"{expr.op}({','.join(sorted(canon(x) for x in expr.args))})"
    for g in ir.guards:
        cid="ir_"+g.id; deps=tuple(pred_clause[x] for x in refs(g.expr)); clauses.append(_clause(cid,ClauseType.DEPENDENCY,"ONLY_IF:"+canon(g.expr),instruction,g.source,depends=deps+(action_anchor[g.action],))); edges.append(ConservationEdge(g.id,cid,"guard:"+canon(g.expr)))
    for d in ir.dependencies:
        cid="ir_"+d.id; clauses.append(_clause(cid,ClauseType.DEPENDENCY,d.relation,instruction,d.source,depends=(action_anchor[d.prerequisite_action],action_anchor[d.action]))); edges.append(ConservationEdge(d.id,cid,"dependency"))
    for x in ir.exceptions:
        cid="ir_"+x.id; target="ir_"+x.target.id; clauses.append(_clause(cid,ClauseType.EXCEPTION,x.effect.effect+":"+canon(x.when),instruction,x.source,exceptions=(target,))); edges.append(ConservationEdge(x.id,cid,"exception-target:"+target))
    for u in ir.ambiguities: edges.append(ConservationEdge(u.id,action_anchor.get(u.target.id,"NON_EXECUTABLE"),"ambiguity"))
    contract=EconomicIntentContract(instruction=instruction,clauses=clauses)
    verify_conservation(ir,contract,edges)
    return contract,tuple(edges),blocked_actions(ir)

def verify_conservation(ir,contract,edges):
    expected={x.id for group in (ir.entities,ir.actions,ir.constraints,ir.predicates,ir.guards,ir.dependencies,ir.exceptions,ir.ambiguities) for x in group}
    covered={e.source_id for e in edges}
    if expected-covered: raise ConservationError("SEMANTIC_CONSERVATION_FAILURE")
    destinations={c.clause_id for c in contract.clauses}|{"NON_EXECUTABLE"}
    if any(e.destination_id not in destinations for e in edges): raise ConservationError("SEMANTIC_CONSERVATION_FAILURE")
    # relationship conservation: every guard/exceptions retains canonical logic/target in its destination.
    byid={c.clause_id:c for c in contract.clauses}
    for e in edges:
        if e.relationship.startswith("guard:") and e.relationship.split(":",1)[1] not in byid[e.destination_id].normalized_value: raise ConservationError("RELATIONSHIP_CONSERVATION_FAILURE")
        if e.relationship.startswith("exception-target:") and e.relationship.split(":",1)[1] not in byid[e.destination_id].exception_to: raise ConservationError("RELATIONSHIP_CONSERVATION_FAILURE")

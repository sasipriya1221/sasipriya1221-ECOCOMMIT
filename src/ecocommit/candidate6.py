from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol
from .semantic_ir import SemanticIR
from .semantic_compiler import compile_contract, ConservationError
from .semantic_validation import SemanticValidationError

SYSTEM_PROMPT='''You are the semantic parser for ECOCOMMIT.
Your only task is to translate the user's instruction into semantic-ir-v1.
You do NOT decide whether an economic action is allowed. You do NOT construct the final ECOCOMMIT contract.
Extract only semantic meaning explicitly supported by the instruction. Preserve every action, object, counterparty, quantity, monetary constraint, condition, dependency, negation, exception and material ambiguity. Never invent facts.
Conditions governing actions use ONLY_IF guards with ATOM/AND/OR/NOT. Preserve AND versus OR, negation, scope and exceptions exactly. Cross-action sequencing belongs only in dependencies. If wording affecting economic authority is unresolved, represent an ambiguity targeted to the semantic object; never guess. Cosmetic ambiguity unrelated to authority may target NON_MATERIAL. Missing information uses ABSENCE; stated facts use exact SPAN quotes. If the schema cannot safely express meaning, emit UNSUPPORTED_SEMANTIC_STRUCTURE. Never output execution permission, authority, validator state or operational consequences. JSON only.'''

PROVIDER_POLICY={"provider":"groq","model":"qwen/qwen3.6-27b","reasoning":"none","response_mode":"json_object","max_completion_tokens":2048,"timeout_seconds":60,"max_total_attempts":3,"max_schema_corrections":2,"terminality":"first_schema_valid_ir","semantic_score_retry":False}

class SemanticProvider(Protocol):
    def parse(self,instruction:str)->SemanticIR: ...
@dataclass(frozen=True)
class Candidate6Result:
    status:str; contract:Any|None; semantic_ir:SemanticIR|None; blocked_actions:frozenset[str]; error_code:str|None=None

def run_candidate6(instruction:str,provider:SemanticProvider)->Candidate6Result:
    try:
        ir=provider.parse(instruction)
        contract,_,blocked=compile_contract(ir,instruction)
        status="CLARIFICATION_REQUIRED" if blocked else "COMPILED"
        return Candidate6Result(status,contract,ir,frozenset(blocked))
    except (SemanticValidationError,ConservationError,ValueError) as exc:
        return Candidate6Result("REJECTED",None,None,frozenset(),str(exc))

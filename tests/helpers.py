from ecocommit.contracts import EconomicClause, EconomicIntentContract, SourceSpan


def span(instruction: str, text: str) -> SourceSpan:
    start = instruction.index(text)
    return SourceSpan(text=text, start=start, end=start + len(text))


def contract(instruction: str, clauses: list[EconomicClause]) -> EconomicIntentContract:
    return EconomicIntentContract(instruction=instruction, clauses=clauses)

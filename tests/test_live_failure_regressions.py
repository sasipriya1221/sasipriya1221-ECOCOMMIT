from ecocommit.contracts import ClauseType, DecisionStatus, EconomicClause, EconomicIntentContract, Provenance
from ecocommit.interpreter import OpenAICompatibleIntentProvider
from ecocommit.validator import FidelityValidator


def _span(instruction: str, text: str):
    from ecocommit.contracts import SourceSpan
    start = instruction.index(text)
    return SourceSpan(text=text, start=start, end=start + len(text))


def test_certified_word_does_not_create_fake_if_dependency():
    instruction = "Buy 500 S17-certified bearings from Vendor A for no more than ₹8 lakh and ensure delivery within five days."
    clauses = [
        EconomicClause(clause_id="p", clause_type=ClauseType.PRODUCT, normalized_value="S17-certified bearings", source_span=_span(instruction, "S17-certified bearings"), provenance=Provenance.EXPLICIT_USER, materiality=0.9, confidence=1.0),
        EconomicClause(clause_id="q", clause_type=ClauseType.QUANTITY, normalized_value="500", source_span=_span(instruction, "500"), provenance=Provenance.EXPLICIT_USER, materiality=0.9, confidence=1.0),
        EconomicClause(clause_id="m", clause_type=ClauseType.AMOUNT, normalized_value="₹8 lakh", source_span=_span(instruction, "₹8 lakh"), provenance=Provenance.EXPLICIT_USER, materiality=1.0, confidence=1.0),
        EconomicClause(clause_id="t", clause_type=ClauseType.TEMPORAL, normalized_value="five days", source_span=_span(instruction, "five days"), provenance=Provenance.EXPLICIT_USER, materiality=0.8, confidence=1.0),
    ]
    report = FidelityValidator().validate(EconomicIntentContract(instruction=instruction, clauses=clauses))
    assert report.status == DecisionStatus.VALIDATED
    assert not any(f.code == "DEPENDENCY_NOT_PRESERVED" for f in report.findings)


def test_material_inference_requires_clarification_not_rejection():
    instruction = "Choose a reliable supplier and spend a little more if needed."
    clauses = [
        EconomicClause(clause_id="r", clause_type=ClauseType.CONDITION, normalized_value="reliable supplier", source_span=None, provenance=Provenance.INFERENCE, materiality=0.8, confidence=0.5, hardness="SOFT"),
        EconomicClause(clause_id="d", clause_type=ClauseType.DEPENDENCY, normalized_value="if needed", source_span=_span(instruction, "if needed"), provenance=Provenance.EXPLICIT_USER, materiality=0.7, confidence=0.6, hardness="SOFT"),
    ]
    report = FidelityValidator().validate(EconomicIntentContract(instruction=instruction, clauses=clauses))
    assert report.status == DecisionStatus.CLARIFICATION_REQUIRED
    assert any(f.code in {"MATERIAL_INFERENCE", "MATERIAL_VAGUENESS"} for f in report.findings)


def test_open_textured_quantity_requires_clarification_even_if_model_is_confident():
    instruction = "Buy around 500 production-grade S17 parts at a reasonable price."
    clauses = [
        EconomicClause(clause_id="q", clause_type=ClauseType.QUANTITY, normalized_value="around 500", source_span=_span(instruction, "around 500"), provenance=Provenance.EXPLICIT_USER, materiality=0.9, confidence=1.0, hardness="SOFT"),
        EconomicClause(clause_id="p", clause_type=ClauseType.PRODUCT, normalized_value="production-grade S17 parts", source_span=_span(instruction, "production-grade S17 parts"), provenance=Provenance.EXPLICIT_USER, materiality=0.8, confidence=1.0),
    ]
    report = FidelityValidator().validate(EconomicIntentContract(instruction=instruction, clauses=clauses))
    assert report.status == DecisionStatus.CLARIFICATION_REQUIRED
    assert any(f.code == "MATERIAL_VAGUENESS" for f in report.findings)


def test_source_offsets_are_recomputed_from_exact_text():
    instruction = "Buy 120 ISO-9001 pressure valves under ₹6 lakh."
    raw = {
        "instruction": instruction,
        "schema_version": "0.1",
        "clauses": [{
            "clause_id": "product",
            "clause_type": "PRODUCT",
            "normalized_value": "ISO-9001 pressure valves",
            "source_span": {"text": "ISO-9001 pressure valves", "start": 0, "end": 4},
            "provenance": "EXPLICIT_USER",
            "materiality": 0.9,
            "confidence": 1.0,
            "hardness": "HARD",
            "policy_class": None,
            "negated": False,
            "depends_on": [],
            "exception_to": [],
        }],
    }
    repaired = OpenAICompatibleIntentProvider._repair_source_spans(raw, instruction)
    contract = EconomicIntentContract.model_validate(repaired)
    assert contract.clauses[0].source_span.text == "ISO-9001 pressure valves"
    assert instruction[contract.clauses[0].source_span.start:contract.clauses[0].source_span.end] == "ISO-9001 pressure valves"


def test_verified_exact_span_can_repair_omitted_explicit_user_provenance():
    instruction = "Buy 40 fire-rated network cabinets."
    raw = {
        "instruction": instruction,
        "schema_version": "0.1",
        "clauses": [{
            "clause_id": "product",
            "clause_type": "PRODUCT",
            "normalized_value": "fire-rated network cabinets",
            "source_span": {"text": "fire-rated network cabinets", "start": 0, "end": 2},
            "materiality": 0.9,
            "confidence": 1.0,
            "hardness": "HARD",
            "policy_class": None,
            "negated": False,
            "depends_on": [],
            "exception_to": [],
        }],
    }

    repaired = OpenAICompatibleIntentProvider._repair_source_spans(raw, instruction)
    contract = EconomicIntentContract.model_validate(repaired)

    assert contract.clauses[0].provenance == Provenance.EXPLICIT_USER
    assert contract.clauses[0].source_span.text == "fire-rated network cabinets"


def test_ungrounded_clause_does_not_get_explicit_provenance_repair():
    instruction = "Buy bearings."
    raw = {
        "instruction": instruction,
        "schema_version": "0.1",
        "clauses": [{
            "clause_id": "fabricated",
            "clause_type": "COUNTERPARTY",
            "normalized_value": "Vendor A",
            "source_span": {"text": "Vendor A", "start": 0, "end": 1},
            "materiality": 0.9,
            "confidence": 1.0,
            "hardness": "HARD",
            "policy_class": None,
            "negated": False,
            "depends_on": [],
            "exception_to": [],
        }],
    }

    repaired = OpenAICompatibleIntentProvider._repair_source_spans(raw, instruction)

    assert repaired["clauses"][0]["source_span"] is None
    assert "provenance" not in repaired["clauses"][0]

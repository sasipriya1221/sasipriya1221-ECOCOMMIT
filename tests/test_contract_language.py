import pytest
from pydantic import ValidationError

from ecocommit.contracts import ClauseType, EconomicClause, EconomicIntentContract, Hardness, Provenance
from helpers import span

SAMPLES = [
    "Buy 500 S17-certified parts below ₹800000.",
    "Buy 20 laptops under ₹1400000 and deliver within 3 days.",
    "Purchase 100 sensors from Vendor A only.",
    "Do not buy refurbished servers; maximum budget ₹900000.",
    "Buy 50 routers unless the delivery date is after Friday.",
    "Purchase 200 units only if ISO certification is valid.",
    "Buy 30 monitors, but do not pay before inspection.",
    "Acquire 10 GPUs with a hard cap of ₹1200000.",
    "Order 75 keyboards before 5 PM tomorrow.",
    "Buy 40 SSDs from approved suppliers only.",
    "Purchase 12 UPS units with replacement guarantee.",
    "Buy 60 headsets if delivery is within 48 hours.",
    "Order 25 printers except from Vendor Z.",
    "Buy 300 cables under ₹150000 total.",
    "Purchase 8 switches after manager authorization.",
    "Buy 15 tablets; around ₹450000 is preferred, not a hard cap.",
    "Order 90 webcams and never use Vendor B.",
    "Buy 100 adapters provided that certification remains valid.",
    "Purchase 25 access points before quarter end.",
    "Buy 500 S17 parts below ₹800000, but do not pay more than 20% until quality is verified unless Vendor A provides the approved replacement guarantee.",
]


def test_twenty_instructions_fit_one_schema():
    for i, instruction in enumerate(SAMPLES):
        marker = next((x for x in ["₹800000", "₹1400000", "Vendor A", "refurbished", "Friday", "ISO", "inspection", "₹1200000", "5 PM", "approved", "guarantee", "48 hours", "Vendor Z", "₹150000", "manager", "₹450000", "Vendor B", "certification", "quarter end", "20%"] if x in instruction), instruction.split()[0])
        clause = EconomicClause(
            clause_id=f"c{i}", clause_type=ClauseType.CONDITION, normalized_value=marker,
            source_span=span(instruction, marker), provenance=Provenance.EXPLICIT_USER,
            materiality=0.8, confidence=1.0,
        )
        assert EconomicIntentContract(instruction=instruction, clauses=[clause]).schema_version == "0.1"


def test_inference_cannot_create_hard_amount_authority():
    with pytest.raises(ValidationError):
        EconomicClause(
            clause_id="amount", clause_type=ClauseType.AMOUNT, normalized_value="hard max ₹800000",
            source_span=None, provenance=Provenance.INFERENCE,
            materiality=1.0, confidence=0.6, hardness=Hardness.HARD,
        )

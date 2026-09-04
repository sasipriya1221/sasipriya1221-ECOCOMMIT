from __future__ import annotations

from ecocommit.candidate7_flat import Relation, RelationBatch, RelationKind, drop_ungrounded_relations
from ecocommit.candidate7_provider import GroqCandidate7Provider


def test_out_of_vocab_action_uses_existing_bounded_correction_path(monkeypatch):
    provider = GroqCandidate7Provider("test-key", max_attempts_per_pass=2, min_request_interval_seconds=0)
    replies = iter([
        (
            {
                "facts": [
                    {
                        "text_span": {"quote": "Pay invoice", "occurrence": 1},
                        "kind": "ACTION",
                        "polarity": "POSITIVE",
                        "action_type": "SEND_MONEY",
                    }
                ]
            },
            {"attempt": 1, "candidate_sha256": "bad", "finish_reason": "stop"},
        ),
        (
            {
                "facts": [
                    {
                        "text_span": {"quote": "Pay invoice", "occurrence": 1},
                        "kind": "ACTION",
                        "polarity": "POSITIVE",
                        "action_type": "PAY",
                    }
                ]
            },
            {"attempt": 2, "candidate_sha256": "good", "finish_reason": "stop"},
        ),
    ])
    monkeypatch.setattr(provider, "_request", lambda messages, attempt: next(replies))

    def validator(parsed):
        provider._validate_action_types_raw(parsed)
        return parsed

    value, trace = provider._run_stage("facts", [{"role": "user", "content": "x"}], validator)

    assert value["facts"][0]["action_type"] == "PAY"
    assert trace[0]["outcome"] == "schema_invalid"
    assert trace[0]["issues"] == [{"location": "root", "code": "C7_ACTION_TYPE_OUT_OF_VOCAB"}]
    assert trace[1]["outcome"] == "accepted"


def test_ungrounded_relation_is_dropped_and_recorded():
    instruction = "Pay invoice after manager approval."
    batch = RelationBatch(relations=[
        Relation(
            kind=RelationKind.GUARDS_ACTION,
            left="F0002",
            right="F0001",
            justification_span="only if CFO signs",
        )
    ])

    filtered, events = drop_ungrounded_relations(instruction, batch)

    assert filtered.relations == []
    assert events == ({
        "outcome": "relation_dropped_ungrounded",
        "kind": "GUARDS_ACTION",
        "left": "F0002",
        "right": "F0001",
        "reason": "UNGROUNDED_SPAN",
        "justification_span": "only if CFO signs",
    },)


def test_grounded_relation_passes_through_unchanged():
    instruction = "Pay invoice after manager approval."
    relation = Relation(
        kind=RelationKind.GUARDS_ACTION,
        left="F0002",
        right="F0001",
        justification_span="after manager approval",
    )
    batch = RelationBatch(relations=[relation])

    filtered, events = drop_ungrounded_relations(instruction, batch)

    assert filtered.relations == [relation]
    assert events == ()

from datetime import datetime, timezone

import pytest

from ecocommit.audit import AppendOnlyAuditLog, AuditIntegrityError, GENESIS_HASH
from ecocommit.observability import (
    InMemoryEventSink,
    MetricsRegistry,
    StructuredLogger,
    resolve_correlation_id,
)


FIXED_TIME = datetime(2026, 9, 1, 8, 30, tzinfo=timezone.utc)


def test_audit_log_is_append_only_and_hash_chained(tmp_path):
    log = AppendOnlyAuditLog(tmp_path / "audit.ndjson", clock=lambda: FIXED_TIME)

    first = log.append("request.received", "corr-1", {"amount_minor": 100})
    second = log.append("request.denied", "corr-1", {"money_moved": False})
    verification = log.verify()

    assert first.sequence == 1
    assert first.previous_hash == GENESIS_HASH
    assert second.sequence == 2
    assert second.previous_hash == first.event_hash
    assert verification.valid is True
    assert verification.entries == 2
    assert verification.head_hash == second.event_hash
    assert [event.event_type for event in log.events()] == [
        "request.received",
        "request.denied",
    ]


def test_audit_log_detects_tampering_and_refuses_to_append(tmp_path):
    path = tmp_path / "audit.ndjson"
    log = AppendOnlyAuditLog(path, clock=lambda: FIXED_TIME)
    log.append("request.received", "corr-1", {"amount_minor": 100})
    path.write_text(
        path.read_text(encoding="utf-8").replace("100", "900"),
        encoding="utf-8",
    )

    verification = log.verify()
    assert verification.valid is False
    assert "hash mismatch" in verification.error
    with pytest.raises(AuditIntegrityError):
        log.append("request.denied", "corr-1", {"money_moved": False})


def test_audit_payload_rejects_non_finite_or_non_json_data(tmp_path):
    log = AppendOnlyAuditLog(tmp_path / "audit.ndjson")

    with pytest.raises(TypeError, match="finite JSON"):
        log.append("bad", "corr-1", {"value": float("nan")})


def test_correlation_ids_are_preserved_only_when_safe():
    supplied = resolve_correlation_id("order:123.retry-2")
    injected = resolve_correlation_id("bad\nheader")

    assert supplied.correlation_id == "order:123.retry-2"
    assert supplied.caller_supplied is True
    assert injected.correlation_id != "bad\nheader"
    assert injected.caller_supplied is False
    assert len(injected.correlation_id) == 32


def test_metrics_and_structured_events_are_machine_readable():
    metrics = MetricsRegistry()
    sink = InMemoryEventSink()
    logger = StructuredLogger(sink, clock=lambda: FIXED_TIME)

    metrics.increment("ecocommit_requests_total", labels={"outcome": "denied"})
    metrics.observe("ecocommit_latency_seconds", 0.25, labels={"route": "commit"})
    logger.emit("info", "commit.denied", "corr-1", reason="GATE_BLOCKED")
    snapshot = metrics.snapshot()

    assert snapshot["counters"][0]["value"] == 1.0
    assert snapshot["histograms"][0]["value"] == {
        "count": 1.0,
        "sum": 0.25,
        "min": 0.25,
        "max": 0.25,
    }
    assert sink.events[0]["event"] == "commit.denied"
    assert sink.events[0]["correlation_id"] == "corr-1"

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import json

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


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_metrics_reject_non_finite_values_before_they_break_json(value):
    metrics = MetricsRegistry()

    with pytest.raises(ValueError, match="finite"):
        metrics.increment("bad_counter", value)
    with pytest.raises(ValueError, match="finite"):
        metrics.set_gauge("bad_gauge", value)
    with pytest.raises(ValueError, match="finite"):
        metrics.observe("bad_histogram", value)

    json.dumps(metrics.snapshot(), allow_nan=False)


def test_metric_aggregate_cannot_overflow_to_infinity():
    metrics = MetricsRegistry()
    metrics.increment("large_counter", 1e308)
    metrics.observe("large_histogram", 1e308)

    with pytest.raises(ValueError, match="aggregate must remain finite"):
        metrics.increment("large_counter", 1e308)
    with pytest.raises(ValueError, match="aggregate must remain finite"):
        metrics.observe("large_histogram", 1e308)

    json.dumps(metrics.snapshot(), allow_nan=False)


def test_multiple_audit_instances_share_a_process_lock(tmp_path):
    path = tmp_path / "shared-audit.ndjson"
    first = AppendOnlyAuditLog(path, clock=lambda: FIXED_TIME)
    second = AppendOnlyAuditLog(path, clock=lambda: FIXED_TIME)

    def append(index):
        target = first if index % 2 else second
        target.append("concurrent.event", f"corr-{index}", {"index": index})

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append, range(80)))

    verification = first.verify()
    assert verification.valid is True
    assert verification.entries == 80
    assert {event.payload["index"] for event in first.events()} == set(range(80))


def test_audit_verifier_rejects_rehashed_but_malformed_record(tmp_path):
    path = tmp_path / "malformed-audit.ndjson"
    log = AppendOnlyAuditLog(path, clock=lambda: FIXED_TIME)
    log.append("request.received", "corr-1", {"amount_minor": 100})
    record = json.loads(path.read_text(encoding="utf-8"))
    record["timestamp"] = "2026-09-01T08:30:00"
    record["event_hash"] = AppendOnlyAuditLog._expected_hash(record)
    path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    verification = log.verify()
    assert verification.valid is False
    assert "non-timezone-aware timestamp" in verification.error

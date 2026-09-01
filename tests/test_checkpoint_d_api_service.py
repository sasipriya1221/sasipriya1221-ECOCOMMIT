import io
import json

from ecocommit.api import ApiRequest, CheckpointDApi, MAX_JSON_BODY_BYTES
from ecocommit.audit import AppendOnlyAuditLog
from ecocommit.checkpoint_status import (
    CHECKPOINTS,
    ExecutionMode,
    GateReport,
    GateState,
    ProviderStatus,
    SafetyStatus,
)
from ecocommit.observability import InMemoryEventSink, StructuredLogger
from ecocommit.service import CheckpointDService


def build_api(tmp_path):
    sink = InMemoryEventSink()
    audit = AppendOnlyAuditLog(tmp_path / "audit.ndjson")
    service = CheckpointDService(
        SafetyStatus(),
        audit,
        logger=StructuredLogger(sink),
    )
    return CheckpointDApi(service), audit, sink


def test_health_is_liveness_only_and_readiness_stays_blocked(tmp_path):
    api, _, _ = build_api(tmp_path)

    health = api.handle(ApiRequest("GET", "/healthz", {"X-Correlation-ID": "corr-7"}))
    readiness = api.handle(ApiRequest("GET", "/readyz"))

    assert health.status_code == 200
    assert health.headers["X-Correlation-ID"] == "corr-7"
    assert health.body["health_scope"] == "PROCESS_LIVENESS_ONLY"
    assert health.body["does_not_imply_checkpoint_acceptance"] is True
    assert tuple(health.body["checkpoint_gates"]) == ("A", "B", "C", "D", "E")
    assert readiness.status_code == 503
    assert readiness.body["ready"] is False
    assert readiness.body["readiness_scope"] == "IRREVERSIBLE_COMMIT_PATH"


def test_scaffold_readiness_stays_blocked_even_if_external_prerequisites_claim_ready(tmp_path):
    external_status = SafetyStatus(
        gates={
            checkpoint: GateReport(
                checkpoint,
                GateState.PASSED,
                evidence=f"evidence://{checkpoint}",
            )
            for checkpoint in CHECKPOINTS
        },
        mode=ExecutionMode.REAL_PROVIDER_TEST,
        provider_status=ProviderStatus.RAZORPAY_TEST_MODE,
        provider_credentials_verified=True,
        provider_calls_enabled=True,
        final_integration_verified=True,
    )
    service = CheckpointDService(
        external_status,
        AppendOnlyAuditLog(tmp_path / "external-audit.ndjson"),
    )

    readiness = CheckpointDApi(service).handle(ApiRequest("GET", "/readyz"))

    assert readiness.status_code == 503
    assert readiness.body["gate_and_provider_prerequisites_ready"] is True
    assert readiness.body["service_execution_adapter_configured"] is False
    assert readiness.body["irreversible_commit_ready"] is False
    assert "EXECUTION_ADAPTER_NOT_IMPLEMENTED" in readiness.body["blockers"]


def test_real_commit_route_stays_locked_even_with_synthetic_all_passed_status(tmp_path):
    class SimulationMustNotRun:
        def run(self, scenario):
            raise AssertionError("real commit route invoked the simulation workflow")

    external_status = SafetyStatus(
        gates={
            checkpoint: GateReport(
                checkpoint,
                GateState.PASSED,
                evidence=f"test-fixture://synthetic-{checkpoint.lower()}-pass",
            )
            for checkpoint in CHECKPOINTS
        },
        mode=ExecutionMode.REAL_PROVIDER_TEST,
        provider_status=ProviderStatus.RAZORPAY_TEST_MODE,
        provider_credentials_verified=True,
        provider_calls_enabled=True,
        final_integration_verified=True,
    )
    service = CheckpointDService(
        external_status,
        AppendOnlyAuditLog(tmp_path / "locked-commit-audit.ndjson"),
        simulation_workflow=SimulationMustNotRun(),
    )

    response = CheckpointDApi(service).handle(ApiRequest(
        "POST",
        "/v1/commit",
        {"Content-Type": "application/json"},
        b'{"authorized":true}',
    ))

    assert response.status_code == 423
    assert response.body["reason"] == "EXECUTION_ADAPTER_NOT_IMPLEMENTED"
    assert response.body["checkpoint_snapshot"]["gate_and_provider_prerequisites_ready"] is True
    assert response.body["money_moved"] is False
    assert response.body["provider_called"] is False


def test_forged_authority_claims_cannot_trigger_a_provider_or_money_movement(tmp_path):
    api, audit, _ = build_api(tmp_path)
    forged = {
        "ai_validated": True,
        "authorized": True,
        "checkpoint_a_passed": True,
        "money_movement_enabled": True,
        "amount_minor": 500_000,
        "api_key": "must-never-be-logged",
    }

    response = api.handle(ApiRequest(
        "POST",
        "/v1/commit",
        {"X-Correlation-ID": "attempt-42"},
        json.dumps(forged).encode("utf-8"),
    ))

    assert response.status_code == 423
    assert response.body["outcome"] == "DENIED"
    assert response.body["default_deny"] is True
    assert response.body["money_moved"] is False
    assert response.body["provider_called"] is False
    assert set(response.body["ignored_untrusted_authority_claims"]) == {
        "ai_validated",
        "authorized",
        "checkpoint_a_passed",
        "money_movement_enabled",
    }
    assert [event.event_type for event in audit.events()] == [
        "commit.requested",
        "commit.denied",
    ]
    assert "must-never-be-logged" not in audit.path.read_text(encoding="utf-8")


def test_simulation_is_unmistakable_and_uses_only_synthetic_authority(tmp_path):
    api, audit, _ = build_api(tmp_path)
    response = api.handle(ApiRequest(
        "POST",
        "/v1/commit/simulate",
        {"Content-Type": "application/json"},
        body=b'{"scenario":"HAPPY_PATH","authorized":true}',
    ))

    assert response.status_code == 200
    assert response.body["outcome"] == "SIMULATED_CAPTURED"
    assert response.body["simulation_label"] == "NO REAL PROVIDER CALL; NO MONEY MOVEMENT"
    assert response.body["authority_evaluated"] is False
    assert response.body["synthetic_authority_fixture_evaluated"] is True
    assert response.body["authority_scope"] == "SYNTHETIC_FIXTURE_ONLY"
    assert response.body["authoritative_checkpoint_evidence_used"] is False
    assert response.body["money_moved"] is False
    assert response.body["provider_called"] is False
    assert response.body["workflow"]["execution_mode"] == "SIMULATED_LOCAL"
    assert response.body["workflow"]["counts_as_checkpoint_evidence"] is False
    assert response.body["workflow"]["final_commitment_stage"] == "CAPTURED"
    assert response.body["simulation_input_contract"] == "SCENARIO_SELECTOR_ONLY"
    assert response.body["ignored_simulation_request_fields"] == ["authorized"]
    assert response.body["ignored_untrusted_authority_claims"] == ["authorized"]
    assert [event.event_type for event in audit.events()] == [
        "simulation.requested",
        "simulation.completed",
    ]


def test_bad_or_oversized_api_inputs_fail_closed(tmp_path):
    api, audit, _ = build_api(tmp_path)

    malformed = api.handle(ApiRequest("POST", "/v1/commit", body=b"{"))
    array = api.handle(ApiRequest("POST", "/v1/commit", body=b"[]"))
    oversized = api.handle(ApiRequest(
        "POST",
        "/v1/commit",
        body=b"x" * (MAX_JSON_BODY_BYTES + 1),
    ))

    assert (malformed.status_code, malformed.body["reason"]) == (400, "INVALID_JSON")
    assert (array.status_code, array.body["reason"]) == (400, "JSON_OBJECT_REQUIRED")
    assert (oversized.status_code, oversized.body["reason"]) == (
        413,
        "REQUEST_BODY_TOO_LARGE",
    )
    assert malformed.body["money_moved"] is False
    assert array.body["provider_called"] is False
    assert [event.event_type for event in audit.events()] == [
        "api.request.rejected",
        "api.request.rejected",
        "api.request.rejected",
    ]


def test_non_json_content_type_and_unknown_scenario_are_rejected_and_audited(tmp_path):
    api, audit, _ = build_api(tmp_path)

    wrong_type = api.handle(ApiRequest(
        "POST",
        "/v1/commit/simulate",
        {"Content-Type": "text/plain"},
        b'{}',
    ))
    unknown = api.handle(ApiRequest(
        "POST",
        "/v1/commit/simulate",
        {"Content-Type": "application/json; charset=utf-8"},
        b'{"scenario":"NOT_REAL"}',
    ))

    assert (wrong_type.status_code, wrong_type.body["reason"]) == (
        415,
        "JSON_CONTENT_TYPE_REQUIRED",
    )
    assert (unknown.status_code, unknown.body["reason"]) == (
        400,
        "INVALID_SIMULATION_SCENARIO",
    )
    assert [event.event_type for event in audit.events()] == [
        "api.request.rejected",
        "simulation.requested",
        "simulation.rejected",
    ]


def test_audit_tampering_causes_commit_to_fail_closed(tmp_path):
    api, audit, _ = build_api(tmp_path)
    audit.append("seed", "corr", {"value": 1})
    audit.path.write_text(
        audit.path.read_text(encoding="utf-8").replace('"value":1', '"value":2'),
        encoding="utf-8",
    )

    response = api.handle(ApiRequest("POST", "/v1/commit", body=b"{}"))

    assert response.status_code == 503
    assert response.body["reason"] == "AUDIT_INTEGRITY_UNAVAILABLE"
    assert response.body["money_moved"] is False
    assert response.body["provider_called"] is False


def test_wsgi_adapter_returns_json_and_correlation_header(tmp_path):
    api, _, _ = build_api(tmp_path)
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    chunks = api({
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/v1/status",
        "QUERY_STRING": "",
        "CONTENT_LENGTH": "0",
        "HTTP_X_CORRELATION_ID": "wsgi-1",
        "wsgi.input": io.BytesIO(),
    }, start_response)
    payload = json.loads(b"".join(chunks))

    assert captured["status"] == "200 OK"
    assert captured["headers"]["X-Correlation-ID"] == "wsgi-1"
    assert payload["correlation_id"] == "wsgi-1"
    assert payload["safe_to_move_real_money"] is False


def test_wsgi_adapter_rejects_invalid_length_and_missing_body_stream(tmp_path):
    api, audit, _ = build_api(tmp_path)

    def invoke(content_length, stream_marker=True):
        captured = {}
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/v1/commit",
            "QUERY_STRING": "",
            "CONTENT_LENGTH": content_length,
            "CONTENT_TYPE": "application/json",
            "HTTP_X_CORRELATION_ID": "wsgi-invalid",
        }
        if stream_marker:
            environ["wsgi.input"] = io.BytesIO(b"{}")

        chunks = api(environ, lambda status, headers: captured.update(status=status))
        return captured["status"], json.loads(b"".join(chunks))

    bad_length = invoke("not-an-integer")
    missing_stream = invoke("2", stream_marker=False)

    incomplete_captured = {}
    incomplete_chunks = api(
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/v1/commit",
            "QUERY_STRING": "",
            "CONTENT_LENGTH": "4",
            "CONTENT_TYPE": "application/json",
            "wsgi.input": io.BytesIO(b"{}"),
        },
        lambda status, headers: incomplete_captured.update(status=status),
    )
    incomplete = json.loads(b"".join(incomplete_chunks))

    assert bad_length[0] == "400 Bad Request"
    assert bad_length[1]["reason"] == "INVALID_CONTENT_LENGTH"
    assert missing_stream[1]["reason"] == "REQUEST_BODY_UNAVAILABLE"
    assert incomplete_captured["status"] == "400 Bad Request"
    assert incomplete["reason"] == "REQUEST_BODY_INCOMPLETE"
    assert all(event.event_type == "api.request.rejected" for event in audit.events())


def test_status_source_exception_fails_closed_without_leaking_detail(tmp_path):
    def unavailable_status():
        raise RuntimeError("secret status backend detail")

    service = CheckpointDService(
        unavailable_status,
        AppendOnlyAuditLog(tmp_path / "status-failure-audit.ndjson"),
    )
    response = CheckpointDApi(service).handle(ApiRequest("GET", "/v1/status"))

    assert response.status_code == 500
    assert response.body["reason"] == "INTERNAL_FAILURE_CLOSED"
    assert "secret" not in json.dumps(response.body)
    assert response.body["money_moved"] is False


def test_simulation_runner_exception_is_denied_and_audited(tmp_path):
    class BrokenSimulation:
        def run(self, scenario):
            raise RuntimeError("internal fixture detail")

    audit = AppendOnlyAuditLog(tmp_path / "broken-simulation-audit.ndjson")
    service = CheckpointDService(
        SafetyStatus(),
        audit,
        simulation_workflow=BrokenSimulation(),
    )
    response = CheckpointDApi(service).handle(ApiRequest(
        "POST",
        "/v1/commit/simulate",
        {"Content-Type": "application/json"},
        b'{"scenario":"HAPPY_PATH"}',
    ))

    assert response.status_code == 503
    assert response.body["reason"] == "SIMULATION_WORKFLOW_FAILURE"
    assert "internal fixture detail" not in json.dumps(response.body)
    assert response.body["money_moved"] is False
    assert response.body["provider_called"] is False
    assert [event.event_type for event in audit.events()] == [
        "simulation.requested",
        "simulation.failed_closed",
    ]


def test_boundary_rejection_stays_closed_when_log_sink_fails(tmp_path):
    def exploding_sink(event):
        raise RuntimeError("logging backend unavailable")

    audit = AppendOnlyAuditLog(tmp_path / "logging-failure-audit.ndjson")
    service = CheckpointDService(
        SafetyStatus(),
        audit,
        logger=StructuredLogger(exploding_sink),
    )
    response = CheckpointDApi(service).handle(ApiRequest("DELETE", "/v1/commit"))

    assert response.status_code == 405
    assert response.body["reason"] == "METHOD_NOT_ALLOWED"
    assert response.body["money_moved"] is False
    assert [event.event_type for event in audit.events()] == ["api.request.rejected"]


def test_service_observability_keeps_route_outcome_and_correlation(tmp_path):
    api, _, sink = build_api(tmp_path)

    response = api.handle(ApiRequest(
        "POST",
        "/v1/commit",
        {"Content-Type": "application/json", "X-Correlation-ID": "observe-42"},
        b'{}',
    ))
    metrics = api.handle(ApiRequest("GET", "/v1/metrics")).body["metrics"]

    completed = next(
        event
        for event in sink.events
        if event["event"] == "api.request.completed"
        and event["correlation_id"] == "observe-42"
    )
    assert response.status_code == 423
    assert completed["route"] == "commit"
    assert completed["outcome"] == "denied"
    assert any(
        row["name"] == "ecocommit_commit_attempts_total"
        and row["labels"]["outcome"] == "denied"
        for row in metrics["counters"]
    )

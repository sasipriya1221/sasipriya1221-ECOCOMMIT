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


def test_simulation_is_unmistakable_and_does_not_evaluate_authority(tmp_path):
    api, audit, _ = build_api(tmp_path)
    response = api.handle(ApiRequest(
        "POST",
        "/v1/commit/simulate",
        body=b'{"amount_minor":100}',
    ))

    assert response.status_code == 200
    assert response.body["outcome"] == "SIMULATED_ONLY"
    assert response.body["simulation_label"] == "NO REAL PROVIDER CALL; NO MONEY MOVEMENT"
    assert response.body["authority_evaluated"] is False
    assert response.body["money_moved"] is False
    assert response.body["provider_called"] is False
    assert [event.event_type for event in audit.events()] == [
        "simulation.requested",
        "simulation.completed",
    ]


def test_bad_or_oversized_api_inputs_fail_closed(tmp_path):
    api, _, _ = build_api(tmp_path)

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

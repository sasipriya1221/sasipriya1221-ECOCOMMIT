import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ecocommit.audit import AppendOnlyAuditLog


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "checkpoint_d_server.py"


def load_server_module():
    spec = importlib.util.spec_from_file_location("checkpoint_d_server", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def invoke(application, method, path, body=b"", content_type=None):
    captured = {}
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
    }
    if content_type:
        environ["CONTENT_TYPE"] = content_type

    chunks = application(
        environ,
        lambda status, headers: captured.update(status=status, headers=dict(headers)),
    )
    return captured, b"".join(chunks)


def test_local_demo_serves_only_known_ui_assets_with_security_headers(tmp_path):
    application = load_server_module().build_application(tmp_path / "audit.ndjson")

    captured, body = invoke(application, "GET", "/")
    missing, missing_body = invoke(application, "GET", "/../PROGRESS.md")

    assert captured["status"] == "200 OK"
    assert b"ECOCOMMIT Safety Console" in body
    assert captured["headers"]["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in captured["headers"]["Content-Security-Policy"]
    assert missing["status"] == "404 Not Found"
    assert json.loads(missing_body)["reason"] == "NOT_FOUND"


def test_local_demo_api_keeps_gates_blocked_and_runs_synthetic_workflow(tmp_path):
    application = load_server_module().build_application(tmp_path / "audit.ndjson")

    status_response, status_body = invoke(application, "GET", "/v1/status")
    simulation_response, simulation_body = invoke(
        application,
        "POST",
        "/v1/commit/simulate",
        b'{"scenario":"HAPPY_PATH"}',
        "application/json",
    )
    real_response, real_body = invoke(
        application,
        "POST",
        "/v1/commit",
        b'{"authorized":true}',
        "application/json",
    )

    status = json.loads(status_body)
    simulation = json.loads(simulation_body)
    real = json.loads(real_body)
    assert status_response["status"] == "200 OK"
    assert all(
        report["state"] == "BLOCKED" and report["accepted"] is False
        for report in status["checkpoint_gates"].values()
    )
    assert simulation_response["status"] == "200 OK"
    assert simulation["workflow"]["outcome"] == "SIMULATED_CAPTURED"
    assert simulation["workflow"]["counts_as_checkpoint_evidence"] is False
    assert real_response["status"] == "423 Locked"
    assert real["money_moved"] is False
    assert real["provider_called"] is False


def test_partial_prepared_server_configuration_fails_before_startup(tmp_path):
    module = load_server_module()

    with pytest.raises(ValueError, match="inseparable"):
        module.serve(
            8765,
            tmp_path / "audit.ndjson",
            prepared_operation_path=tmp_path / "prepared.json",
        )


def test_runtime_validates_webhook_secret_before_provider_preflight(tmp_path, monkeypatch):
    module = load_server_module()
    operation = SimpleNamespace(
        handoff=SimpleNamespace(public_key_id="rzp_test_x"),
    )
    monkeypatch.setattr(module, "load_prepared_test_operation", lambda *args, **kwargs: operation)
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_x")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "provider-secret")
    monkeypatch.setenv("ECOCOMMIT_D_SIGNING_SECRET", "s" * 32)
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
    preflight_called = []
    monkeypatch.setattr(
        module.RazorpayTestPaymentAdapter,
        "verify_credentials",
        lambda self: preflight_called.append(True),
    )

    with pytest.raises(ValueError, match="webhook secret"):
        module.build_prepared_execution_runtime(
            tmp_path / "prepared.json",
            "0" * 64,
            tmp_path / "state.sqlite3",
            audit_log=AppendOnlyAuditLog(tmp_path / "audit.ndjson"),
        )

    assert preflight_called == []


def test_authoritative_evidence_is_validated_before_runtime_preflight(tmp_path, monkeypatch):
    module = load_server_module()
    runtime_called = []

    def invalid_evidence(*args, **kwargs):
        raise ValueError("invalid pinned evidence")

    monkeypatch.setattr(module, "load_authoritative_evidence", invalid_evidence)
    monkeypatch.setattr(
        module,
        "build_prepared_execution_runtime",
        lambda *args, **kwargs: runtime_called.append(True),
    )

    with pytest.raises(ValueError, match="invalid pinned evidence"):
        module.serve(
            8765,
            tmp_path / "audit.ndjson",
            evidence_root=tmp_path,
            pins_path=tmp_path / "pins.json",
            pins_sha256="0" * 64,
            prepared_operation_path=tmp_path / "prepared.json",
            prepared_operation_sha256="1" * 64,
            state_db_path=tmp_path / "state.sqlite3",
        )

    assert runtime_called == []

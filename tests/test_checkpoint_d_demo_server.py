import importlib.util
import io
import json
from pathlib import Path


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

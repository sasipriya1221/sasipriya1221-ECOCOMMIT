import io
import ipaddress
import json
import os
import runpy
from http import HTTPStatus
from pathlib import Path

import pytest

from ecocommit.api import MAX_JSON_BODY_BYTES
from ecocommit.deployment import (
    DeploymentConfig,
    DeploymentConfigurationError,
    StrictTLSProxyMiddleware,
    _validate_api_token,
    create_application_from_environment,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def deployment_environment(tmp_path):
    persistent_root = tmp_path / "persistent"
    persistent_root.mkdir(parents=True)
    return {
        "ECOCOMMIT_D_PUBLIC_HOST": "ecocommit.example.test",
        "ECOCOMMIT_D_TRUSTED_PROXY_CIDRS": "127.0.0.1/32,::1/128",
        "ECOCOMMIT_D_TLS_TERMINATION": "TRUSTED_REVERSE_PROXY",
        "ECOCOMMIT_D_EDGE_RATE_LIMITING": "EXTERNAL_SHARED_LIMITER_REQUIRED",
        "ECOCOMMIT_D_MAX_REQUEST_BODY_BYTES": str(MAX_JSON_BODY_BYTES),
        "ECOCOMMIT_D_INSTANCE_COUNT": "1",
        "ECOCOMMIT_D_WORKER_COUNT": "1",
        "ECOCOMMIT_D_PROVIDER_MODE": "DISABLED",
        "ECOCOMMIT_D_PERSISTENT_ROOT": str(persistent_root.resolve()),
        "ECOCOMMIT_D_AUDIT_PATH": str(
            (persistent_root / "audit" / "events.ndjson").resolve()
        ),
    }


def proxy_environ(**overrides):
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/healthz",
        "QUERY_STRING": "",
        "CONTENT_LENGTH": "0",
        "wsgi.input": io.BytesIO(),
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_HOST": "ecocommit.example.test",
        "HTTP_X_FORWARDED_FOR": "203.0.113.24",
        "HTTP_X_FORWARDED_HOST": "ecocommit.example.test",
        "HTTP_X_FORWARDED_PROTO": "https",
        "HTTP_X_FORWARDED_PORT": "443",
        "wsgi.url_scheme": "http",
        "SERVER_NAME": "127.0.0.1",
        "SERVER_PORT": "8000",
    }
    environ.update(overrides)
    return environ


def invoke(application, environ):
    captured = {}

    def start_response(status, headers, exc_info=None):
        captured.update(status=status, headers=dict(headers), exc_info=exc_info)

    body = b"".join(application(environ, start_response))
    return captured, body


def test_safe_hosted_factory_reuses_blocked_app_without_provider_activity(tmp_path):
    environment = deployment_environment(tmp_path)
    application = create_application_from_environment(environment)

    captured, body = invoke(application, proxy_environ())
    payload = json.loads(body)

    assert captured["status"] == "200 OK"
    assert payload["health"] == "ALIVE"
    assert payload["health_scope"] == "PROCESS_LIVENESS_ONLY"
    assert captured["headers"]["Strict-Transport-Security"] == "max-age=31536000"
    assert captured["headers"]["X-Frame-Options"] == "DENY"
    assert Path(environment["ECOCOMMIT_D_AUDIT_PATH"]).is_file()


class RecordingApplication:
    def __init__(self):
        self.environ = None

    def __call__(self, environ, start_response):
        self.environ = environ
        start_response("204 No Content", [])
        return [b""]


def strict_boundary(application=None):
    return StrictTLSProxyMiddleware(
        application or RecordingApplication(),
        public_host="ecocommit.example.test",
        trusted_proxy_networks=(ipaddress.ip_network("127.0.0.1/32"),),
    )


@pytest.mark.parametrize(
    ("override", "expected_status", "reason"),
    [
        ({"REMOTE_ADDR": "198.51.100.5"}, "403 Forbidden", "UNTRUSTED_REVERSE_PROXY"),
        ({"HTTP_HOST": "attacker.example"}, "421 Misdirected Request", "PUBLIC_HOST_MISMATCH"),
        ({"HTTP_X_FORWARDED_PROTO": "http"}, "400 Bad Request", "FORWARDED_TLS_REQUIRED"),
        ({"HTTP_X_FORWARDED_FOR": "1.2.3.4, 5.6.7.8"}, "400 Bad Request", "SINGLE_FORWARDED_CLIENT_IP_REQUIRED"),
        ({"HTTP_FORWARDED": "for=203.0.113.24;proto=https"}, "400 Bad Request", "AMBIGUOUS_FORWARDED_HEADERS"),
        ({"HTTP_TRANSFER_ENCODING": "chunked"}, "400 Bad Request", "TRANSFER_ENCODING_FORBIDDEN"),
        ({"CONTENT_LENGTH": " 1"}, "400 Bad Request", "INVALID_CONTENT_LENGTH"),
        ({"CONTENT_LENGTH": "+1"}, "400 Bad Request", "INVALID_CONTENT_LENGTH"),
        ({"CONTENT_LENGTH": "00"}, "400 Bad Request", "INVALID_CONTENT_LENGTH"),
        ({"CONTENT_LENGTH": str(MAX_JSON_BODY_BYTES + 1)}, f"413 {HTTPStatus(413).phrase}", "REQUEST_BODY_TOO_LARGE"),
    ],
)
def test_strict_proxy_boundary_rejects_direct_or_ambiguous_requests(
    override,
    expected_status,
    reason,
):
    captured, body = invoke(strict_boundary(), proxy_environ(**override))
    payload = json.loads(body)

    assert captured["status"] == expected_status
    assert payload == {
        "error": "DEPLOYMENT_BOUNDARY_REJECTED",
        "reason": reason,
        "provider_called": False,
        "money_moved": False,
    }


def test_strict_proxy_boundary_canonicalizes_only_validated_tls_request():
    downstream = RecordingApplication()
    captured, _ = invoke(strict_boundary(downstream), proxy_environ())

    assert captured["status"] == "204 No Content"
    assert downstream.environ["wsgi.url_scheme"] == "https"
    assert downstream.environ["HTTPS"] == "on"
    assert downstream.environ["SERVER_NAME"] == "ecocommit.example.test"
    assert downstream.environ["SERVER_PORT"] == "443"


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("ECOCOMMIT_D_PUBLIC_HOST", "*.example.test", "exact DNS hostname"),
        ("ECOCOMMIT_D_TRUSTED_PROXY_CIDRS", "0.0.0.0/0", "entire Internet"),
        ("ECOCOMMIT_D_WORKER_COUNT", "2", "exactly one instance"),
        ("ECOCOMMIT_D_INSTANCE_COUNT", "2", "exactly one instance"),
        ("ECOCOMMIT_D_MAX_REQUEST_BODY_BYTES", "65535", "must equal 65536"),
        ("ECOCOMMIT_D_PROVIDER_MODE", "LIVE", "only DISABLED or RAZORPAY_TEST_MODE"),
    ],
)
def test_environment_contract_rejects_unsafe_hosting_values(tmp_path, key, value, message):
    environment = deployment_environment(tmp_path)
    environment[key] = value

    with pytest.raises(DeploymentConfigurationError, match=message):
        DeploymentConfig.from_environment(environment)


@pytest.mark.parametrize("value", ["01", "+1", "1.0", "１"])
def test_environment_contract_requires_canonical_numeric_values(tmp_path, value):
    environment = deployment_environment(tmp_path)
    environment["ECOCOMMIT_D_WORKER_COUNT"] = value

    with pytest.raises(DeploymentConfigurationError, match="canonical decimal"):
        DeploymentConfig.from_environment(environment)


@pytest.mark.parametrize(
    "token",
    ["x" * 31, "x" * 257, "x" * 31 + " ", "x" * 31 + "é"],
)
def test_api_token_requires_bounded_visible_ascii(token):
    with pytest.raises(DeploymentConfigurationError, match="visible ASCII"):
        _validate_api_token({"ECOCOMMIT_D_API_TOKEN": token})


def test_api_token_accepts_bounded_visible_ascii():
    assert _validate_api_token({"ECOCOMMIT_D_API_TOKEN": "x" * 32}) == "x" * 32


def test_environment_contract_rejects_partial_or_unpinned_authority(tmp_path):
    environment = deployment_environment(tmp_path)
    environment["ECOCOMMIT_D_EVIDENCE_ROOT"] = str((tmp_path / "evidence").resolve())
    with pytest.raises(DeploymentConfigurationError, match="must be supplied together"):
        DeploymentConfig.from_environment(environment)

    environment = deployment_environment(tmp_path / "second")
    environment["ECOCOMMIT_D_PROVIDER_MODE"] = "RAZORPAY_TEST_MODE"
    with pytest.raises(DeploymentConfigurationError, match="requires complete pinned evidence"):
        DeploymentConfig.from_environment(environment)


def test_test_mode_state_must_live_on_persistent_volume(tmp_path):
    environment = deployment_environment(tmp_path)
    environment.update(
        {
            "ECOCOMMIT_D_PROVIDER_MODE": "RAZORPAY_TEST_MODE",
            "ECOCOMMIT_D_EVIDENCE_ROOT": str((tmp_path / "evidence").resolve()),
            "ECOCOMMIT_D_PINS_PATH": str((tmp_path / "evidence" / "pins.json").resolve()),
            "ECOCOMMIT_D_PINS_SHA256": "a" * 64,
            "ECOCOMMIT_D_PREPARED_OPERATION_PATH": str(
                (tmp_path / "operation.json").resolve()
            ),
            "ECOCOMMIT_D_PREPARED_OPERATION_SHA256": "b" * 64,
            "ECOCOMMIT_D_STATE_DB_PATH": str((tmp_path / "ephemeral.sqlite3").resolve()),
        }
    )

    with pytest.raises(DeploymentConfigurationError, match="below ECOCOMMIT_D_PERSISTENT_ROOT"):
        DeploymentConfig.from_environment(environment)


def test_test_mode_state_must_not_hardlink_the_append_only_audit_log(tmp_path):
    environment = deployment_environment(tmp_path)
    audit_path = Path(environment["ECOCOMMIT_D_AUDIT_PATH"])
    audit_path.parent.mkdir(parents=True)
    audit_path.write_bytes(b"")
    state_path = Path(environment["ECOCOMMIT_D_PERSISTENT_ROOT"]) / "state.sqlite3"
    os.link(audit_path, state_path)
    environment.update(
        {
            "ECOCOMMIT_D_PROVIDER_MODE": "RAZORPAY_TEST_MODE",
            "ECOCOMMIT_D_EVIDENCE_ROOT": str((tmp_path / "evidence").resolve()),
            "ECOCOMMIT_D_PINS_PATH": str(
                (tmp_path / "evidence" / "pins.json").resolve()
            ),
            "ECOCOMMIT_D_PINS_SHA256": "a" * 64,
            "ECOCOMMIT_D_PREPARED_OPERATION_PATH": str(
                (tmp_path / "operation.json").resolve()
            ),
            "ECOCOMMIT_D_PREPARED_OPERATION_SHA256": "b" * 64,
            "ECOCOMMIT_D_STATE_DB_PATH": str(state_path.resolve()),
        }
    )

    with pytest.raises(DeploymentConfigurationError, match="different files"):
        DeploymentConfig.from_environment(environment)


def test_wsgi_entrypoint_is_importable_with_safe_environment(tmp_path, monkeypatch):
    environment = deployment_environment(tmp_path)
    optional_names = (
        "ECOCOMMIT_D_EVIDENCE_ROOT",
        "ECOCOMMIT_D_PINS_PATH",
        "ECOCOMMIT_D_PINS_SHA256",
        "ECOCOMMIT_D_PREPARED_OPERATION_PATH",
        "ECOCOMMIT_D_PREPARED_OPERATION_SHA256",
        "ECOCOMMIT_D_STATE_DB_PATH",
    )
    for name in optional_names:
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    namespace = runpy.run_path(str(REPOSITORY_ROOT / "deploy" / "wsgi.py"))

    assert isinstance(namespace["application"], StrictTLSProxyMiddleware)


def test_proxy_templates_pin_host_headers_tls_limits_and_loopback():
    nginx = (REPOSITORY_ROOT / "deploy" / "nginx.conf.template").read_text(
        encoding="utf-8"
    )
    proxy = (REPOSITORY_ROOT / "deploy" / "proxy-policy.inc.template").read_text(
        encoding="utf-8"
    )
    example = (REPOSITORY_ROOT / "deploy" / "ecocommit.env.example").read_text(
        encoding="utf-8"
    )

    assert "server 127.0.0.1:@@WSGI_PORT@@;" in nginx
    assert "listen 443 ssl default_server;" in nginx
    assert 'if ($ssl_server_name != "@@PUBLIC_HOST@@") { return 421; }' in nginx
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in nginx
    assert "client_max_body_size 64k;" in nginx
    assert "limit_req zone=ecocommit_commit" in nginx
    assert "limit_req zone=ecocommit_webhook" in nginx
    assert "proxy_set_header Host @@PUBLIC_HOST@@;" in proxy
    assert "proxy_set_header Forwarded \"\";" in proxy
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in proxy
    assert "proxy_add_x_forwarded_for" not in proxy
    assert 'proxy_set_header Transfer-Encoding "";' in proxy
    assert "ECOCOMMIT_D_PROVIDER_MODE=DISABLED" in example
    assert "rzp_test_" not in example

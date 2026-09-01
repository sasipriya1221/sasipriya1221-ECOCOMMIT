from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from ecocommit._canonical import sha256_hex
from ecocommit.github_actions import (
    GitHubRunVerificationError,
    fetch_razorpay_preflight_run,
    load_preflight_receipt,
    verify_razorpay_preflight_run,
    write_preflight_receipt,
)


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import checkpoint_b8_razorpay_live as live_script
from checkpoint_b8_razorpay_live import run as run_order_boundary


REPOSITORY = "owner/ecocommit"
RUN_ID = 33535533432
SOURCE_SHA = "a" * 40


def run_payload() -> dict:
    return {
        "id": RUN_ID,
        "run_attempt": 1,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "path": ".github/workflows/razorpay-test-preflight.yml@main",
        "head_sha": SOURCE_SHA,
        "repository": {"full_name": REPOSITORY},
        "head_repository": {"full_name": REPOSITORY},
    }


def test_checkpoint_b_preflight_receipt_binds_successful_same_revision_run(tmp_path):
    receipt = verify_razorpay_preflight_run(
        run_payload(),
        repository=REPOSITORY,
        run_id=RUN_ID,
        expected_sha=SOURCE_SHA,
    )
    unsigned = {
        key: value for key, value in receipt.items() if key != "receipt_sha256"
    }
    assert receipt["receipt_sha256"] == sha256_hex(unsigned)
    assert receipt["verification_source"] == "GITHUB_ACTIONS_API"

    path = tmp_path / "preflight.json"
    write_preflight_receipt(path, receipt)
    assert load_preflight_receipt(
        path,
        repository=REPOSITORY,
        run_id=RUN_ID,
        expected_sha=SOURCE_SHA,
    ) == receipt


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ({"id": RUN_ID + 1}, "UNEXPECTED_ID"),
        ({"event": "push"}, "UNEXPECTED_EVENT"),
        ({"status": "in_progress"}, "UNEXPECTED_STATUS"),
        ({"conclusion": "failure"}, "UNEXPECTED_CONCLUSION"),
        ({"path": ".github/workflows/other.yml"}, "UNEXPECTED_PATH"),
        ({"head_sha": "b" * 40}, "UNEXPECTED_HEAD_SHA"),
        ({"run_attempt": 0}, "INVALID_RUN_ATTEMPT"),
        ({"repository": {"full_name": "other/repo"}}, "UNEXPECTED_REPOSITORY"),
        (
            {"head_repository": {"full_name": "fork/repo"}},
            "UNEXPECTED_HEAD_REPOSITORY",
        ),
    ],
)
def test_checkpoint_b_preflight_rejects_wrong_run_identity(mutation, expected_code):
    payload = deepcopy(run_payload())
    payload.update(mutation)
    with pytest.raises(GitHubRunVerificationError) as caught:
        verify_razorpay_preflight_run(
            payload,
            repository=REPOSITORY,
            run_id=RUN_ID,
            expected_sha=SOURCE_SHA,
        )
    assert caught.value.code == expected_code


class _Response:
    def __init__(self, raw: bytes, *, final_url: str | None = None):
        self.raw = raw
        self.status = 200
        self.final_url = final_url or (
            "https://api.github.com/repos/owner/ecocommit/actions/runs/33535533432"
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def geturl(self):
        return self.final_url

    def read(self, size=-1):
        return self.raw if size < 0 else self.raw[:size]


def test_checkpoint_b_preflight_fetch_uses_bounded_authenticated_github_api():
    seen = {}

    def opener(api_request, timeout):
        seen["url"] = api_request.full_url
        seen["authorization"] = api_request.get_header("Authorization")
        seen["redirectable_authorization"] = api_request.headers.get("Authorization")
        seen["api_version"] = api_request.get_header("X-github-api-version")
        seen["timeout"] = timeout
        return _Response(json.dumps(run_payload()).encode("utf-8"))

    receipt = fetch_razorpay_preflight_run(
        repository=REPOSITORY,
        run_id=RUN_ID,
        expected_sha=SOURCE_SHA,
        token="github-token-not-retained",
        opener=opener,
    )

    assert seen == {
        "url": "https://api.github.com/repos/owner/ecocommit/actions/runs/33535533432",
        "authorization": "Bearer github-token-not-retained",
        "redirectable_authorization": None,
        "api_version": "2026-03-10",
        "timeout": 20.0,
    }
    assert "github-token-not-retained" not in json.dumps(receipt)


@pytest.mark.parametrize(
    ("final_url", "expected_code"),
    [
        ("https://attacker.example/run", "UNEXPECTED_RESPONSE_ORIGIN"),
        (
            "https://api.github.com/repos/owner/ecocommit/actions/runs/1",
            "UNEXPECTED_RESPONSE_URL",
        ),
    ],
)
def test_checkpoint_b_preflight_fetch_rejects_redirected_response(
    final_url,
    expected_code,
):
    with pytest.raises(GitHubRunVerificationError) as caught:
        fetch_razorpay_preflight_run(
            repository=REPOSITORY,
            run_id=RUN_ID,
            expected_sha=SOURCE_SHA,
            token="github-token-not-retained",
            opener=lambda *_args, **_kwargs: _Response(
                json.dumps(run_payload()).encode("utf-8"),
                final_url=final_url,
            ),
        )
    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    ("raw", "limit", "expected_code"),
    [
        (b'{"id":1,"id":2}', 1024, "MALFORMED_RESPONSE"),
        (b"{}", 1, "RESPONSE_TOO_LARGE"),
        (b"", 1024, "EMPTY_RESPONSE"),
    ],
)
def test_checkpoint_b_preflight_fetch_rejects_ambiguous_or_unbounded_json(
    raw,
    limit,
    expected_code,
):
    with pytest.raises(GitHubRunVerificationError) as caught:
        fetch_razorpay_preflight_run(
            repository=REPOSITORY,
            run_id=RUN_ID,
            expected_sha=SOURCE_SHA,
            token="github-token-not-retained",
            max_response_bytes=limit,
            opener=lambda *_args, **_kwargs: _Response(raw),
        )
    assert caught.value.code == expected_code


def test_checkpoint_b_preflight_receipt_rejects_tamper_unknown_fields_and_overwrite(
    tmp_path,
):
    receipt = verify_razorpay_preflight_run(
        run_payload(),
        repository=REPOSITORY,
        run_id=RUN_ID,
        expected_sha=SOURCE_SHA,
    )
    path = tmp_path / "preflight.json"
    write_preflight_receipt(path, receipt)
    with pytest.raises(GitHubRunVerificationError) as caught:
        write_preflight_receipt(path, receipt)
    assert caught.value.code == "OUTPUT_ALREADY_EXISTS"

    tampered = {**receipt, "unexpected": True}
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(GitHubRunVerificationError) as caught:
        load_preflight_receipt(
            path,
            repository=REPOSITORY,
            run_id=RUN_ID,
            expected_sha=SOURCE_SHA,
        )
    assert caught.value.code == "INVALID_RECEIPT_FIELDS"


def test_checkpoint_b_order_boundary_requires_verified_preflight_before_credentials(
    tmp_path,
    monkeypatch,
):
    receipt = verify_razorpay_preflight_run(
        run_payload(),
        repository=REPOSITORY,
        run_id=RUN_ID,
        expected_sha=SOURCE_SHA,
    )
    receipt_path = tmp_path / "preflight.json"
    write_preflight_receipt(receipt_path, receipt)
    monkeypatch.setenv("GITHUB_REPOSITORY", REPOSITORY)
    monkeypatch.setenv("GITHUB_SHA", SOURCE_SHA)
    monkeypatch.setenv("B8_PREFLIGHT_RUN_ID", str(RUN_ID))
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)

    output = tmp_path / "evidence.json"
    assert run_order_boundary(output, preflight_receipt=receipt_path) == 2
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert evidence["status"] == "BLOCKED_CONFIGURATION"
    assert evidence["authentication"]["credential_preflight_run_verified"] is True
    assert (
        evidence["authentication"]["preflight_reference_receipt_sha256"]
        == receipt["receipt_sha256"]
    )
    assert evidence["provider_calls"] == []


def test_checkpoint_b_order_boundary_rejects_tampered_preflight_before_provider_call(
    tmp_path,
    monkeypatch,
):
    receipt = verify_razorpay_preflight_run(
        run_payload(),
        repository=REPOSITORY,
        run_id=RUN_ID,
        expected_sha=SOURCE_SHA,
    )
    receipt["head_sha"] = "b" * 40
    receipt_path = tmp_path / "preflight.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    monkeypatch.setenv("GITHUB_REPOSITORY", REPOSITORY)
    monkeypatch.setenv("GITHUB_SHA", SOURCE_SHA)
    monkeypatch.setenv("B8_PREFLIGHT_RUN_ID", str(RUN_ID))
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_not_used")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret-not-used")
    credential_loads = []

    def reject_credential_load(cls, environ=None):
        credential_loads.append(environ)
        raise AssertionError("credentials loaded before preflight receipt validation")

    monkeypatch.setattr(
        live_script.RazorpayTestCredentials,
        "from_environment",
        classmethod(reject_credential_load),
    )

    output = tmp_path / "evidence.json"
    assert run_order_boundary(output, preflight_receipt=receipt_path) == 2
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert evidence["status"] == "BLOCKED_PREFLIGHT_REFERENCE"
    assert evidence["authentication"]["credential_preflight_run_verified"] is False
    assert evidence["provider_calls"] == []
    assert credential_loads == []

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable
from urllib import error, request
from urllib.parse import quote, urlsplit

from ._canonical import sha256_hex, strict_json_loads


GITHUB_API_ORIGIN = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"
RAZORPAY_PREFLIGHT_WORKFLOW_PATH = ".github/workflows/razorpay-test-preflight.yml"
PREFLIGHT_RECEIPT_SCHEMA_VERSION = "B8.PREFLIGHT_REFERENCE.1"
MAX_GITHUB_RESPONSE_BYTES = 512 * 1024
MAX_PREFLIGHT_RECEIPT_BYTES = 64 * 1024

_REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
_RECEIPT_FIELDS = {
    "schema_version",
    "verification_source",
    "repository",
    "workflow_path",
    "run_id",
    "run_attempt",
    "event",
    "status",
    "conclusion",
    "head_sha",
    "receipt_sha256",
}


class GitHubRunVerificationError(RuntimeError):
    """A redacted GitHub Actions verification failure safe for CI output."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(f"GitHub Actions preflight verification failed: {code}")


def _validate_identity(repository: str, run_id: int, expected_sha: str) -> None:
    if not _REPOSITORY_PATTERN.fullmatch(repository):
        raise GitHubRunVerificationError("INVALID_REPOSITORY")
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
        raise GitHubRunVerificationError("INVALID_RUN_ID")
    if not _SHA_PATTERN.fullmatch(expected_sha):
        raise GitHubRunVerificationError("INVALID_EXPECTED_SHA")


def _repository_name(payload: dict[str, Any], field: str) -> str | None:
    value = payload.get(field)
    return value.get("full_name") if isinstance(value, dict) else None


def verify_razorpay_preflight_run(
    payload: Any,
    *,
    repository: str,
    run_id: int,
    expected_sha: str,
) -> dict[str, Any]:
    """Verify one successful same-revision credential-preflight workflow run."""

    _validate_identity(repository, run_id, expected_sha)
    if not isinstance(payload, dict):
        raise GitHubRunVerificationError("RESPONSE_OBJECT_REQUIRED")

    expected = {
        "id": run_id,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "head_sha": expected_sha,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise GitHubRunVerificationError(f"UNEXPECTED_{field.upper()}")
    workflow_path = payload.get("path")
    if (
        not isinstance(workflow_path, str)
        or workflow_path.split("@", 1)[0] != RAZORPAY_PREFLIGHT_WORKFLOW_PATH
    ):
        raise GitHubRunVerificationError("UNEXPECTED_PATH")
    if _repository_name(payload, "repository") != repository:
        raise GitHubRunVerificationError("UNEXPECTED_REPOSITORY")
    if _repository_name(payload, "head_repository") != repository:
        raise GitHubRunVerificationError("UNEXPECTED_HEAD_REPOSITORY")

    run_attempt = payload.get("run_attempt")
    if (
        not isinstance(run_attempt, int)
        or isinstance(run_attempt, bool)
        or run_attempt < 1
    ):
        raise GitHubRunVerificationError("INVALID_RUN_ATTEMPT")

    receipt: dict[str, Any] = {
        "schema_version": PREFLIGHT_RECEIPT_SCHEMA_VERSION,
        "verification_source": "GITHUB_ACTIONS_API",
        "repository": repository,
        "workflow_path": RAZORPAY_PREFLIGHT_WORKFLOW_PATH,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "head_sha": expected_sha,
    }
    receipt["receipt_sha256"] = sha256_hex(receipt)
    return receipt


def fetch_razorpay_preflight_run(
    *,
    repository: str,
    run_id: int,
    expected_sha: str,
    token: str,
    timeout_seconds: float = 20.0,
    max_response_bytes: int = MAX_GITHUB_RESPONSE_BYTES,
    opener: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    """Fetch and verify a run without retaining the API token or response body."""

    _validate_identity(repository, run_id, expected_sha)
    if not token or any(character.isspace() for character in token):
        raise GitHubRunVerificationError("TOKEN_MISSING_OR_INVALID")
    if max_response_bytes < 1:
        raise GitHubRunVerificationError("INVALID_RESPONSE_LIMIT")

    owner, name = repository.split("/", 1)
    url = (
        f"{GITHUB_API_ORIGIN}/repos/{quote(owner, safe='')}/"
        f"{quote(name, safe='')}/actions/runs/{run_id}"
    )
    api_request = request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ECOCOMMIT/0.1",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        },
        method="GET",
    )
    api_request.add_unredirected_header("Authorization", f"Bearer {token}")

    try:
        with opener(api_request, timeout=timeout_seconds) as response:
            final_url = response.geturl() if hasattr(response, "geturl") else url
            parsed = urlsplit(final_url)
            if parsed.scheme != "https" or parsed.hostname != "api.github.com":
                raise GitHubRunVerificationError("UNEXPECTED_RESPONSE_ORIGIN")
            if final_url != api_request.full_url:
                raise GitHubRunVerificationError("UNEXPECTED_RESPONSE_URL")
            status = getattr(response, "status", 200)
            if status != 200:
                raise GitHubRunVerificationError("UNEXPECTED_HTTP_STATUS")
            raw = response.read(max_response_bytes + 1)
    except GitHubRunVerificationError:
        raise
    except error.HTTPError as exc:
        try:
            exc.read(max_response_bytes + 1)
        except Exception:
            pass
        raise GitHubRunVerificationError(f"HTTP_{exc.code}") from None
    except (error.URLError, TimeoutError):
        raise GitHubRunVerificationError("TRANSPORT_ERROR") from None

    if not raw or len(raw) > max_response_bytes:
        code = "EMPTY_RESPONSE" if not raw else "RESPONSE_TOO_LARGE"
        raise GitHubRunVerificationError(code)
    try:
        payload = strict_json_loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise GitHubRunVerificationError("MALFORMED_RESPONSE") from None
    return verify_razorpay_preflight_run(
        payload,
        repository=repository,
        run_id=run_id,
        expected_sha=expected_sha,
    )


def write_preflight_receipt(path: Path, receipt: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise GitHubRunVerificationError("OUTPUT_ALREADY_EXISTS")
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        receipt,
        ensure_ascii=True,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(serialized)


def load_preflight_receipt(
    path: Path,
    *,
    repository: str,
    run_id: int,
    expected_sha: str,
) -> dict[str, Any]:
    _validate_identity(repository, run_id, expected_sha)
    if path.is_symlink():
        raise GitHubRunVerificationError("SYMLINKED_RECEIPT")
    try:
        raw = path.resolve().read_bytes()
    except OSError:
        raise GitHubRunVerificationError("RECEIPT_UNREADABLE") from None
    if not raw or len(raw) > MAX_PREFLIGHT_RECEIPT_BYTES:
        code = "EMPTY_RECEIPT" if not raw else "RECEIPT_TOO_LARGE"
        raise GitHubRunVerificationError(code)
    try:
        receipt = strict_json_loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise GitHubRunVerificationError("MALFORMED_RECEIPT") from None
    if not isinstance(receipt, dict) or set(receipt) != _RECEIPT_FIELDS:
        raise GitHubRunVerificationError("INVALID_RECEIPT_FIELDS")

    claimed_hash = receipt.get("receipt_sha256")
    unsigned = {
        key: value for key, value in receipt.items() if key != "receipt_sha256"
    }
    if claimed_hash != sha256_hex(unsigned):
        raise GitHubRunVerificationError("RECEIPT_DIGEST_MISMATCH")
    expected = {
        "schema_version": PREFLIGHT_RECEIPT_SCHEMA_VERSION,
        "verification_source": "GITHUB_ACTIONS_API",
        "repository": repository,
        "workflow_path": RAZORPAY_PREFLIGHT_WORKFLOW_PATH,
        "run_id": run_id,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "head_sha": expected_sha,
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise GitHubRunVerificationError(f"RECEIPT_{field.upper()}_MISMATCH")
    run_attempt = receipt.get("run_attempt")
    if (
        not isinstance(run_attempt, int)
        or isinstance(run_attempt, bool)
        or run_attempt < 1
    ):
        raise GitHubRunVerificationError("INVALID_RECEIPT_RUN_ATTEMPT")
    return receipt

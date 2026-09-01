from __future__ import annotations

import hmac
import json
import time
from collections import deque
from dataclasses import dataclass, field
from http import HTTPStatus
from threading import RLock
from typing import Callable, Iterable, Mapping
from urllib.parse import urlsplit

from .observability import resolve_correlation_id
from .service import CheckpointDService, ServiceReply
from .webhook import BoundRazorpayWebhookProcessor, WebhookProcessingError


MAX_JSON_BODY_BYTES = 64 * 1024


class SlidingWindowRateLimiter:
    """Single-process limiter for the loopback Test execution server."""

    def __init__(
        self,
        *,
        max_attempts: int,
        window_seconds: float,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_attempts <= 0 or window_seconds <= 0:
            raise ValueError("rate limit bounds must be positive")
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._monotonic = monotonic
        self._attempts: deque[float] = deque()
        self._lock = RLock()

    def allow(self) -> bool:
        now = self._monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            while self._attempts and self._attempts[0] <= cutoff:
                self._attempts.popleft()
            if len(self._attempts) >= self.max_attempts:
                return False
            self._attempts.append(now)
            return True


@dataclass(frozen=True)
class ApiRequest:
    method: str
    path: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""


@dataclass(frozen=True)
class ApiResponse:
    status_code: int
    body: Mapping[str, object]
    headers: Mapping[str, str]

    def json_bytes(self) -> bytes:
        return json.dumps(
            self.body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    return next((value for key, value in headers.items() if key.lower() == lowered), None)


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON keys are forbidden")
        result[key] = value
    return result


class CheckpointDApi:
    """Dependency-light JSON API and WSGI adapter around CheckpointDService."""

    _GET_ROUTES = {
        "/healthz": "health",
        "/readyz": "readiness",
        "/v1/status": "status",
        "/v1/metrics": "metrics_snapshot",
    }
    _POST_ROUTES = {
        "/v1/commit/simulate": "simulate",
        "/v1/commit": "request_commit",
    }
    _WEBHOOK_ROUTE = "/v1/razorpay/webhook"

    def __init__(
        self,
        service: CheckpointDService,
        *,
        commit_bearer_token: str | None = None,
        commit_rate_limiter: SlidingWindowRateLimiter | None = None,
        webhook_processor: BoundRazorpayWebhookProcessor | None = None,
    ) -> None:
        if commit_bearer_token is not None and (
            len(commit_bearer_token.encode("utf-8")) < 32
            or any(character.isspace() for character in commit_bearer_token)
        ):
            raise ValueError("commit bearer token must contain at least 32 non-space bytes")
        self.service = service
        self._commit_bearer_token = commit_bearer_token
        self._commit_rate_limiter = commit_rate_limiter
        self._webhook_processor = webhook_processor

    @staticmethod
    def _response(reply: ServiceReply) -> ApiResponse:
        correlation_id = str(reply.body.get("correlation_id", ""))
        return ApiResponse(
            reply.status_code,
            reply.body,
            {
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Correlation-ID": correlation_id,
            },
        )

    @staticmethod
    def _error(status_code: int, reason: str, correlation_id: str) -> ApiResponse:
        return ApiResponse(
            status_code,
            {
                "correlation_id": correlation_id,
                "outcome": "DENIED",
                "reason": reason,
                "default_deny": True,
                "money_moved": False,
                "provider_called": False,
            },
            {
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Correlation-ID": correlation_id,
            },
        )

    def _reject(
        self,
        status_code: int,
        reason: str,
        correlation_id: str,
        *,
        method: str,
        path: str,
    ) -> ApiResponse:
        try:
            self.service.record_boundary_rejection(
                correlation_id=correlation_id,
                method=method,
                path=path,
                reason=reason,
                status_code=status_code,
            )
        except Exception:
            # Boundary observability must not prevent a closed response.
            pass
        return self._error(status_code, reason, correlation_id)

    def handle(self, request: ApiRequest) -> ApiResponse:
        supplied_correlation = _header(request.headers, "X-Correlation-ID")
        correlation = resolve_correlation_id(supplied_correlation)
        method = request.method.upper()
        path = urlsplit(request.path).path

        try:
            if path == self._WEBHOOK_ROUTE:
                if self._webhook_processor is None:
                    return self._reject(
                        404,
                        "NOT_FOUND",
                        correlation.correlation_id,
                        method=method,
                        path=path,
                    )
                if method != "POST":
                    return self._reject(
                        405,
                        "METHOD_NOT_ALLOWED",
                        correlation.correlation_id,
                        method=method,
                        path=path,
                    )
                if len(request.body) > MAX_JSON_BODY_BYTES:
                    return self._reject(
                        413,
                        "REQUEST_BODY_TOO_LARGE",
                        correlation.correlation_id,
                        method=method,
                        path=path,
                    )
                content_type = _header(request.headers, "Content-Type")
                if (
                    content_type is None
                    or content_type.split(";", 1)[0].strip().lower()
                    != "application/json"
                ):
                    return self._reject(
                        415,
                        "JSON_CONTENT_TYPE_REQUIRED",
                        correlation.correlation_id,
                        method=method,
                        path=path,
                    )
                signature = _header(request.headers, "X-Razorpay-Signature") or ""
                event_id = _header(request.headers, "X-Razorpay-Event-Id") or ""
                try:
                    result = self._webhook_processor.ingest(
                        raw_body=request.body,
                        signature=signature,
                        event_id=event_id,
                    )
                except WebhookProcessingError as exc:
                    return self._reject(
                        exc.status_code,
                        exc.code,
                        correlation.correlation_id,
                        method=method,
                        path=path,
                    )
                return self._response(ServiceReply(
                    200,
                    {
                        "correlation_id": correlation.correlation_id,
                        "outcome": "WEBHOOK_ACCEPTED",
                        **result.model_dump(mode="json"),
                    },
                ))

            if path in self._GET_ROUTES:
                if method != "GET":
                    return self._reject(
                        405,
                        "METHOD_NOT_ALLOWED",
                        correlation.correlation_id,
                        method=method,
                        path=path,
                    )
                handler = getattr(self.service, self._GET_ROUTES[path])
                return self._response(handler(correlation.correlation_id))

            if path in self._POST_ROUTES:
                if method != "POST":
                    return self._reject(
                        405,
                        "METHOD_NOT_ALLOWED",
                        correlation.correlation_id,
                        method=method,
                        path=path,
                    )
                if path == "/v1/commit" and self._commit_bearer_token is not None:
                    if (
                        self._commit_rate_limiter is not None
                        and not self._commit_rate_limiter.allow()
                    ):
                        return self._reject(
                            429,
                            "TEST_EXECUTION_RATE_LIMITED",
                            correlation.correlation_id,
                            method=method,
                            path=path,
                        )
                    supplied = _header(request.headers, "Authorization") or ""
                    expected = f"Bearer {self._commit_bearer_token}"
                    if not hmac.compare_digest(supplied, expected):
                        return self._reject(
                            401,
                            "TEST_EXECUTION_AUTHENTICATION_REQUIRED",
                            correlation.correlation_id,
                            method=method,
                            path=path,
                        )
                if len(request.body) > MAX_JSON_BODY_BYTES:
                    return self._reject(
                        413,
                        "REQUEST_BODY_TOO_LARGE",
                        correlation.correlation_id,
                        method=method,
                        path=path,
                    )
                content_type = _header(request.headers, "Content-Type")
                if (
                    content_type is not None
                    and content_type.split(";", 1)[0].strip().lower() != "application/json"
                ):
                    return self._reject(
                        415,
                        "JSON_CONTENT_TYPE_REQUIRED",
                        correlation.correlation_id,
                        method=method,
                        path=path,
                    )
                try:
                    payload = json.loads(
                        request.body or b"{}",
                        object_pairs_hook=_unique_object,
                        parse_constant=_reject_constant,
                    )
                except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                    return self._reject(
                        400,
                        "INVALID_JSON",
                        correlation.correlation_id,
                        method=method,
                        path=path,
                    )
                if not isinstance(payload, dict):
                    return self._reject(
                        400,
                        "JSON_OBJECT_REQUIRED",
                        correlation.correlation_id,
                        method=method,
                        path=path,
                    )
                handler = getattr(self.service, self._POST_ROUTES[path])
                return self._response(handler(payload, correlation.correlation_id))

            return self._reject(
                404,
                "NOT_FOUND",
                correlation.correlation_id,
                method=method,
                path=path,
            )
        except Exception:
            # No exception detail crosses this untrusted boundary. Service-level
            # execution failures are handled before this generic parser guard so
            # provider-call uncertainty is represented truthfully.
            return self._reject(
                500,
                "INTERNAL_FAILURE_CLOSED",
                correlation.correlation_id,
                method=method,
                path=path,
            )

    def __call__(self, environ: Mapping[str, object], start_response) -> Iterable[bytes]:
        method = str(environ.get("REQUEST_METHOD", "GET"))
        path = str(environ.get("PATH_INFO", "/"))
        query = str(environ.get("QUERY_STRING", ""))
        if query:
            path = f"{path}?{query}"

        headers: dict[str, str] = {}
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                name = key[5:].replace("_", "-")
                headers[name] = str(value)
        if environ.get("CONTENT_TYPE"):
            headers["Content-Type"] = str(environ["CONTENT_TYPE"])

        try:
            declared_length = int(str(environ.get("CONTENT_LENGTH") or "0"))
        except ValueError:
            declared_length = -1
        correlation = resolve_correlation_id(_header(headers, "X-Correlation-ID"))
        if declared_length < 0:
            response = self._reject(
                400,
                "INVALID_CONTENT_LENGTH",
                correlation.correlation_id,
                method=method.upper(),
                path=urlsplit(path).path,
            )
            return self._wsgi_response(response, start_response)
        input_stream = environ.get("wsgi.input")
        body = b""
        if declared_length > MAX_JSON_BODY_BYTES:
            body = b"x" * (MAX_JSON_BODY_BYTES + 1)
        elif declared_length > 0:
            if input_stream is None:
                response = self._reject(
                    400,
                    "REQUEST_BODY_UNAVAILABLE",
                    correlation.correlation_id,
                    method=method.upper(),
                    path=urlsplit(path).path,
                )
                return self._wsgi_response(response, start_response)
            try:
                body = input_stream.read(declared_length)
            except Exception:
                response = self._reject(
                    400,
                    "REQUEST_BODY_UNAVAILABLE",
                    correlation.correlation_id,
                    method=method.upper(),
                    path=urlsplit(path).path,
                )
                return self._wsgi_response(response, start_response)
            if not isinstance(body, bytes):
                response = self._reject(
                    400,
                    "REQUEST_BODY_UNAVAILABLE",
                    correlation.correlation_id,
                    method=method.upper(),
                    path=urlsplit(path).path,
                )
                return self._wsgi_response(response, start_response)
            if len(body) != declared_length:
                response = self._reject(
                    400,
                    "REQUEST_BODY_INCOMPLETE",
                    correlation.correlation_id,
                    method=method.upper(),
                    path=urlsplit(path).path,
                )
                return self._wsgi_response(response, start_response)

        response = self.handle(ApiRequest(method, path, headers, body))

        return self._wsgi_response(response, start_response)

    @staticmethod
    def _wsgi_response(response: ApiResponse, start_response) -> Iterable[bytes]:
        status = HTTPStatus(response.status_code)
        encoded = response.json_bytes()
        response_headers = list(response.headers.items()) + [
            ("Content-Length", str(len(encoded)))
        ]
        start_response(f"{status.value} {status.phrase}", response_headers)
        return [encoded]

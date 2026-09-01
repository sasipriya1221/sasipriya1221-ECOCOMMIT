from __future__ import annotations

import json
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Iterable, Mapping
from urllib.parse import urlsplit

from .observability import resolve_correlation_id
from .service import CheckpointDService, ServiceReply


MAX_JSON_BODY_BYTES = 64 * 1024


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

    def __init__(self, service: CheckpointDService) -> None:
        self.service = service

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

    def handle(self, request: ApiRequest) -> ApiResponse:
        supplied_correlation = _header(request.headers, "X-Correlation-ID")
        correlation = resolve_correlation_id(supplied_correlation)
        method = request.method.upper()
        path = urlsplit(request.path).path

        try:
            if path in self._GET_ROUTES:
                if method != "GET":
                    return self._error(405, "METHOD_NOT_ALLOWED", correlation.correlation_id)
                handler = getattr(self.service, self._GET_ROUTES[path])
                return self._response(handler(correlation.correlation_id))

            if path in self._POST_ROUTES:
                if method != "POST":
                    return self._error(405, "METHOD_NOT_ALLOWED", correlation.correlation_id)
                if len(request.body) > MAX_JSON_BODY_BYTES:
                    return self._error(413, "REQUEST_BODY_TOO_LARGE", correlation.correlation_id)
                try:
                    payload = json.loads(request.body or b"{}")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return self._error(400, "INVALID_JSON", correlation.correlation_id)
                if not isinstance(payload, dict):
                    return self._error(400, "JSON_OBJECT_REQUIRED", correlation.correlation_id)
                handler = getattr(self.service, self._POST_ROUTES[path])
                return self._response(handler(payload, correlation.correlation_id))

            return self._error(404, "NOT_FOUND", correlation.correlation_id)
        except Exception:
            # No exception detail crosses this untrusted boundary. Since this
            # scaffold has no execution adapter, the failure remains side-effect free.
            self.service.logger.emit(
                "ERROR",
                "api.request.failed_closed",
                correlation.correlation_id,
                method=method,
                path=path,
                default_deny=True,
            )
            return self._error(500, "INTERNAL_FAILURE_CLOSED", correlation.correlation_id)

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

        try:
            declared_length = int(str(environ.get("CONTENT_LENGTH") or "0"))
        except ValueError:
            declared_length = MAX_JSON_BODY_BYTES + 1
        input_stream = environ.get("wsgi.input")
        body = b""
        if input_stream is not None and declared_length > 0:
            body = input_stream.read(min(declared_length, MAX_JSON_BODY_BYTES + 1))

        response = self.handle(ApiRequest(method, path, headers, body))
        status = HTTPStatus(response.status_code)
        encoded = response.json_bytes()
        response_headers = list(response.headers.items()) + [
            ("Content-Length", str(len(encoded)))
        ]
        start_response(f"{status.value} {status.phrase}", response_headers)
        return [encoded]

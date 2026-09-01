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
                    payload = json.loads(request.body or b"{}")
                except (json.JSONDecodeError, UnicodeDecodeError):
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
            # No exception detail crosses this untrusted boundary. Since this
            # scaffold has no execution adapter, the failure remains side-effect free.
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

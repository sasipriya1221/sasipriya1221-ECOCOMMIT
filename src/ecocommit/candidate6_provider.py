from __future__ import annotations

import json
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from urllib import error, request
from urllib.parse import urlsplit

from pydantic import ValidationError

from ._canonical import (
    DuplicateJSONKeyError,
    InvalidJSONValueError,
    NonFiniteJSONValueError,
    strict_json_loads,
)
from .candidate6 import SYSTEM_PROMPT
from .interpreter import ProviderRequestError
from .semantic_ir import SemanticIR


@dataclass(frozen=True)
class SemanticParseResult:
    semantic_ir: SemanticIR
    provider_trace: tuple[dict[str, Any], ...]


class SemanticIRSchemaError(RuntimeError):
    def __init__(self, issues: list[dict[str, str]], trace: list[dict[str, Any]]):
        self.issues = tuple(issues)
        self.provider_trace = tuple(trace)
        super().__init__("semantic IR remained schema-invalid after bounded correction")


class GroqSemanticIRProvider:
    DEFAULT_ALLOWED_HOSTS = frozenset({"api.groq.com"})
    MAX_RESPONSE_BYTES = 1_048_576

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.groq.com/openai/v1",
        model: str = "qwen/qwen3.6-27b",
        timeout: float = 60.0,
        max_attempts: int = 3,
        max_schema_corrections: int = 2,
        max_completion_tokens: int = 2048,
        max_retry_delay: float = 15.0,
    ):
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.hostname not in self.DEFAULT_ALLOWED_HOSTS or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("provider base URL is not permitted")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = float(timeout)
        self.max_attempts = max(1, int(max_attempts))
        self.max_schema_corrections = max(0, int(max_schema_corrections))
        self.max_completion_tokens = max(1, int(max_completion_tokens))
        self.max_retry_delay = max(0.0, float(max_retry_delay))

    @staticmethod
    def _issues(exc: Exception) -> list[dict[str, str]]:
        if isinstance(exc, ValidationError):
            return [
                {
                    "location": ".".join(str(p) for p in item.get("loc", ())) or "root",
                    "code": str(item.get("type", "invalid")),
                }
                for item in exc.errors(include_input=False, include_url=False)[:32]
            ]
        if isinstance(exc, json.JSONDecodeError):
            return [{"location": "root", "code": "invalid_json"}]
        if isinstance(exc, DuplicateJSONKeyError):
            return [{"location": "root", "code": "duplicate_json_key"}]
        if isinstance(exc, NonFiniteJSONValueError):
            return [{"location": "root", "code": "non_finite_number"}]
        if isinstance(exc, InvalidJSONValueError):
            return [{"location": "root", "code": "invalid_json_value"}]
        return [{"location": "root", "code": "malformed_candidate"}]

    @staticmethod
    def _candidate_metadata(body: dict[str, Any], content: str, attempt: int) -> dict[str, Any]:
        choices = body.get("choices") if isinstance(body.get("choices"), list) else []
        choice = choices[0] if choices and isinstance(choices[0], dict) else {}
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        safe_usage = {
            k: int(usage[k])
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")
            if isinstance(usage.get(k), int) and usage[k] >= 0
        }
        rid = body.get("id")
        return {
            "attempt": attempt,
            "candidate_sha256": sha256(content.encode("utf-8")).hexdigest(),
            "finish_reason": choice.get("finish_reason"),
            "request_id": rid[:200] if isinstance(rid, str) else None,
            "usage": safe_usage,
        }

    def _request(self, payload: dict[str, Any], attempt: int) -> dict[str, Any]:
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ECOCOMMIT-Candidate6/1",
            },
            method="POST",
        )
        req.add_unredirected_header("Authorization", f"Bearer {self.api_key}")
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                if response.geturl() != req.full_url:
                    raise ProviderRequestError("REDIRECT_REJECTED", attempts=attempt, transient=False)
                raw = response.read(self.MAX_RESPONSE_BYTES + 1)
                if len(raw) > self.MAX_RESPONSE_BYTES:
                    raise ProviderRequestError("RESPONSE_TOO_LARGE", attempts=attempt, transient=False)
            body = strict_json_loads(raw.decode("utf-8"))
            if not isinstance(body, dict):
                raise TypeError("provider response must be object")
            return body
        except error.HTTPError as exc:
            try:
                exc.read(self.MAX_RESPONSE_BYTES + 1)
            except Exception:
                pass
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            raise ProviderRequestError(f"HTTP_{exc.code}", attempts=attempt, transient=retryable) from exc
        except (error.URLError, TimeoutError) as exc:
            raise ProviderRequestError("TRANSPORT_ERROR", attempts=attempt, transient=True) from exc

    def parse_with_metadata(self, instruction: str) -> SemanticParseResult:
        schema = SemanticIR.model_json_schema()
        base_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"instruction": instruction, "semantic_ir_json_schema": schema},
                    separators=(",", ":"),
                ),
            },
        ]
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_completion_tokens": self.max_completion_tokens,
            "messages": base_messages,
            "response_format": {"type": "json_object"},
        }
        trace: list[dict[str, Any]] = []
        corrections = 0
        attempt = 1
        while attempt <= self.max_attempts:
            try:
                body = self._request(payload, attempt)
            except ProviderRequestError as exc:
                trace.append({"attempt": attempt, "outcome": "provider_error", "code": exc.code, "transient": exc.transient})
                if exc.transient and attempt < self.max_attempts:
                    time.sleep(min(self.max_retry_delay, 2 ** (attempt - 1)))
                    attempt += 1
                    continue
                raise ProviderRequestError(exc.code, attempts=attempt, transient=exc.transient, provider_trace=trace) from exc

            choices = body.get("choices")
            message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str):
                trace.append({"attempt": attempt, "outcome": "provider_error", "code": "MALFORMED_RESPONSE", "transient": False})
                raise ProviderRequestError("MALFORMED_RESPONSE", attempts=attempt, transient=False, provider_trace=trace)

            meta = self._candidate_metadata(body, content, attempt)
            try:
                parsed = strict_json_loads(content)
                ir = SemanticIR.model_validate(parsed)
            except (json.JSONDecodeError, DuplicateJSONKeyError, NonFiniteJSONValueError, InvalidJSONValueError, ValidationError, TypeError) as exc:
                issues = self._issues(exc)
                trace.append({**meta, "outcome": "schema_invalid", "issues": issues})
                if corrections < self.max_schema_corrections and attempt < self.max_attempts:
                    corrections += 1
                    compact = ", ".join(f"{i['location']} ({i['code']})" for i in issues)
                    payload["messages"] = base_messages + [{
                        "role": "user",
                        "content": "The previous JSON failed only the declared Semantic IR schema at: " + compact + ". Return a complete replacement from the original instruction. Do not use evaluator results, expected answers, or semantic scoring. JSON only.",
                    }]
                    attempt += 1
                    continue
                raise SemanticIRSchemaError(issues, trace) from exc

            # First schema-valid IR is terminal. No semantic validator/evaluator feedback
            # can cause another provider request.
            trace.append({**meta, "outcome": "accepted"})
            return SemanticParseResult(ir, tuple(trace))

        raise ProviderRequestError("RETRY_EXHAUSTED", attempts=self.max_attempts, transient=True, provider_trace=trace)

    def parse(self, instruction: str) -> SemanticIR:
        return self.parse_with_metadata(instruction).semantic_ir

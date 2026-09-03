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


SPAN_SOURCE = {"kind": "SPAN", "quote": "exact substring from instruction", "occurrence": 1}
ABSENCE_SOURCE = {"kind": "ABSENCE", "expected": "description of information genuinely required but absent"}
BOOL_AST = {
    "ATOM": {"op": "ATOM", "predicate": "P#"},
    "AND": {"op": "AND", "args": ["BoolExpr", "BoolExpr"]},
    "OR": {"op": "OR", "args": ["BoolExpr", "BoolExpr"]},
    "NOT": {"op": "NOT", "arg": "BoolExpr"},
}

# Compact provider contract only. SemanticIR/Pydantic remains the authoritative schema.
# Every nested object is shown explicitly because free-text shorthands such as "SPAN"
# previously caused avoidable schema-invalid provider outputs.
COMPACT_SEMANTIC_IR_SCHEMA = {
    "schema_version": "semantic-ir-v1",
    "entities": [{
        "id": "E#",
        "kind": "OBJECT|COUNTERPARTY|PERSON|ORGANIZATION|DOCUMENT|EVENT|RESOURCE|OTHER",
        "text": "string",
        "source": SPAN_SOURCE,
    }],
    "actions": [{
        "id": "A#",
        "kind": "BUY|ORDER|PAY|TRANSFER|HIRE|BOOK|RENEW|RESERVE|SELECT|RELEASE|CANCEL|COMMIT",
        "object": "E#",
        "counterparty": "E# or null",
        "quantity": {
            "raw_value": "string",
            "raw_unit": "string",
            "source": SPAN_SOURCE,
        },
        "source": SPAN_SOURCE,
    }],
    "constraints": [{
        "id": "C#",
        "action": "A#",
        "kind": "MAX_TOTAL_COST|MAX_UNIT_COST|MIN_TOTAL_COST|EXACT_TOTAL_COST",
        "money": {
            "raw_amount": "string",
            "raw_currency": "string",
            "source": SPAN_SOURCE,
        },
    }],
    "predicates": [{
        "id": "P#",
        "kind": "STATE|APPROVAL|EVENT|DOCUMENT_STATUS|COMPARISON|EXISTENCE",
        "subject": "E#",
        "attribute": "string or null",
        "operator": "EQ|NEQ|LT|LTE|GT|GTE|EXISTS|OCCURRED|APPROVED|VALID|CURRENT|RECEIVED",
        "value": "string or null",
        "source": SPAN_SOURCE,
    }],
    "guards": [{
        "id": "G#",
        "action": "A#",
        "mode": "ONLY_IF",
        "expr": BOOL_AST,
        "source": SPAN_SOURCE,
    }],
    "dependencies": [{
        "id": "D#",
        "action": "A#",
        "prerequisite_action": "A#",
        "relation": "AFTER_COMPLETION|AFTER_SUCCESS",
        "source": SPAN_SOURCE,
    }],
    "exceptions": [{
        "id": "X#",
        "target": {"kind": "ACTION|GUARD|CONSTRAINT", "id": "matching target ID"},
        "when": BOOL_AST,
        "effect": {
            "one_of": [
                {"effect": "BLOCK_ACTION"},
                {
                    "effect": "ADD_MONETARY_ALLOWANCE",
                    "money": {"raw_amount": "string", "raw_currency": "string", "source": SPAN_SOURCE},
                },
            ]
        },
        "source": SPAN_SOURCE,
    }],
    "ambiguities": [{
        "id": "U#",
        "kind": "UNDEFINED_QUANTITY|UNDEFINED_BUDGET|SUBJECTIVE_SELECTION_CRITERION|UNCLEAR_COUNTERPARTY|VAGUE_PERMISSION|AMBIGUOUS_CONDITION|MISSING_REQUIRED_INFORMATION|UNSUPPORTED_SEMANTIC_STRUCTURE",
        "target": {
            "kind": "ACTION_FIELD|PREDICATE|GUARD|CONSTRAINT|COUNTERPARTY|DEPENDENCY|PRESENTATION",
            "id": "target ID or null",
            "field": "field or null",
        },
        "source": {"one_of": [SPAN_SOURCE, ABSENCE_SOURCE]},
    }],
}


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
        max_retry_delay: float = 900.0,
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

    @staticmethod
    def _safe_http_metadata(raw: bytes, headers: Any) -> dict[str, Any]:
        meta: dict[str, Any] = {"error_body_sha256": sha256(raw).hexdigest()}
        retry_after = headers.get("Retry-After") if headers else None
        try:
            if retry_after is not None:
                meta["retry_after_seconds"] = min(max(0.0, float(retry_after)), 3600.0)
        except (TypeError, ValueError):
            pass
        try:
            body = strict_json_loads(raw.decode("utf-8"))
            error_obj = body.get("error") if isinstance(body, dict) else None
            if isinstance(error_obj, dict):
                kind = error_obj.get("type") or error_obj.get("code")
                if isinstance(kind, str):
                    meta["provider_error_type"] = kind[:120]
        except Exception:
            pass
        return meta

    def _request(self, payload: dict[str, Any], attempt: int) -> dict[str, Any]:
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "ECOCOMMIT-Candidate6/1"},
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
                raw = exc.read(self.MAX_RESPONSE_BYTES + 1)
            except Exception:
                raw = b""
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            provider_exc = ProviderRequestError(f"HTTP_{exc.code}", attempts=attempt, transient=retryable)
            provider_exc.safe_http_metadata = self._safe_http_metadata(raw, exc.headers)
            raise provider_exc from exc
        except (error.URLError, TimeoutError) as exc:
            raise ProviderRequestError("TRANSPORT_ERROR", attempts=attempt, transient=True) from exc

    def parse_with_metadata(self, instruction: str) -> SemanticParseResult:
        schema_contract = json.dumps(COMPACT_SEMANTIC_IR_SCHEMA, separators=(",", ":"))
        base_messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
                + "\nCompact semantic-ir-v1 shape (authoritative local validation still applies). "
                  "Objects shown for source/expr/effect are structural examples, not strings.\n"
                + schema_contract,
            },
            {"role": "user", "content": json.dumps({"instruction": instruction}, separators=(",", ":"))},
        ]
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_completion_tokens": self.max_completion_tokens,
            "messages": base_messages,
            "response_format": {"type": "json_object"},
            "reasoning_effort": "none",
        }
        trace: list[dict[str, Any]] = []
        corrections = 0
        attempt = 1
        while attempt <= self.max_attempts:
            try:
                body = self._request(payload, attempt)
            except ProviderRequestError as exc:
                safe_meta = getattr(exc, "safe_http_metadata", {})
                trace.append({
                    "attempt": attempt,
                    "outcome": "provider_error",
                    "code": exc.code,
                    "transient": exc.transient,
                    **safe_meta,
                })
                if exc.transient and attempt < self.max_attempts:
                    provider_delay = float(safe_meta.get("retry_after_seconds", 0.0) or 0.0)
                    exponential = min(8.0, 2 ** (attempt - 1))
                    # Honor the provider's reset window instead of immediately consuming
                    # the remaining per-case attempts against the same exhausted bucket.
                    time.sleep(min(self.max_retry_delay, max(exponential, provider_delay)))
                    attempt += 1
                    continue
                raise ProviderRequestError(
                    exc.code,
                    attempts=attempt,
                    transient=exc.transient,
                    provider_trace=trace,
                ) from exc

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
                        "content": "The previous JSON failed only semantic-ir-v1 schema validation at: "
                        + compact
                        + ". Return a complete replacement from the original instruction using the same compact schema contract above. "
                          "Every source must be an object: SPAN={kind,quote,occurrence} or, only for ambiguities, ABSENCE={kind,expected}. "
                          "Do not use evaluator results, expected answers, or semantic scoring. JSON only.",
                    }]
                    attempt += 1
                    continue
                raise SemanticIRSchemaError(issues, trace) from exc

            trace.append({**meta, "outcome": "accepted"})
            return SemanticParseResult(ir, tuple(trace))

        raise ProviderRequestError("RETRY_EXHAUSTED", attempts=self.max_attempts, transient=True, provider_trace=trace)

    def parse(self, instruction: str) -> SemanticIR:
        return self.parse_with_metadata(instruction).semantic_ir

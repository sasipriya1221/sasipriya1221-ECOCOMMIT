from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
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
from .contracts import EconomicIntentContract


@dataclass(frozen=True)
class InterpretationResult:
    contract: EconomicIntentContract
    provider_trace: tuple[dict[str, Any], ...]


class CandidateContractError(RuntimeError):
    """A provider candidate stayed schema-invalid after bounded correction."""

    def __init__(self, issues: list[dict[str, str]], provider_trace: list[dict[str, Any]]):
        self.issues = tuple(dict(issue) for issue in issues)
        self.provider_trace = tuple(dict(item) for item in provider_trace)
        compact = ", ".join(f"{i['location']}:{i['code']}" for i in issues)
        super().__init__(f"candidate contract invalid after bounded correction ({compact})")


class _CandidateShapeError(ValueError):
    """Internal carrier for safe, path-only candidate shape findings."""

    def __init__(self, issues: list[dict[str, str]]):
        self.issues = issues
        super().__init__("candidate shape invalid")


class ProviderRequestError(RuntimeError):
    """A redacted provider failure safe to retain in evaluation evidence."""

    def __init__(
        self,
        code: str,
        *,
        attempts: int,
        transient: bool,
        provider_trace: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    ):
        self.code = code
        self.attempts = attempts
        self.transient = transient
        self.provider_trace = tuple(dict(item) for item in provider_trace)
        super().__init__(f"provider {code} after {attempts} attempt(s)")


class IntentProvider(ABC):
    @abstractmethod
    def interpret(self, instruction: str) -> EconomicIntentContract:
        raise NotImplementedError


class OpenAICompatibleIntentProvider(IntentProvider):
    """OpenAI-compatible provider with local grounding and bounded retry behavior."""

    DEFAULT_ALLOWED_HOSTS = frozenset({"api.openai.com", "api.groq.com"})
    DEFAULT_MAX_RESPONSE_BYTES = 1_048_576

    COMPACT_SCHEMA = {
        "instruction": "exact original instruction",
        "schema_version": "0.1",
        "clauses": [{
            "clause_id": "unique string",
            "clause_type": "PRODUCT|QUANTITY|AMOUNT|COUNTERPARTY|TEMPORAL|CERTIFICATION|REVERSIBILITY|AUTHORIZATION|CONDITION|EXCEPTION|DEPENDENCY",
            "normalized_value": "string",
            "source_span": {"text": "exact verbatim substring", "start": 0, "end": 1},
            "provenance": "EXPLICIT_USER|INCORPORATED_POLICY|AUTHORITATIVE_EVIDENCE|INFERENCE",
            "materiality": "0..1",
            "confidence": "0..1",
            "hardness": "HARD|SOFT",
            "policy_class": None,
            "negated": False,
            "depends_on": [],
            "exception_to": [],
        }],
    }

    STRICT_JSON_SCHEMA = {
        "type": "object",
        "properties": {
            "instruction": {"type": "string", "minLength": 1},
            "schema_version": {"type": "string", "enum": ["0.1"]},
            "clauses": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "clause_id": {"type": "string", "minLength": 1},
                        "clause_type": {
                            "type": "string",
                            "enum": [
                                "PRODUCT", "QUANTITY", "AMOUNT", "COUNTERPARTY", "TEMPORAL",
                                "CERTIFICATION", "REVERSIBILITY", "AUTHORIZATION", "CONDITION",
                                "EXCEPTION", "DEPENDENCY",
                            ],
                        },
                        "normalized_value": {"type": "string", "minLength": 1},
                        "source_span": {
                            "anyOf": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "text": {"type": "string", "minLength": 1},
                                        "start": {"type": "integer", "minimum": 0},
                                        "end": {"type": "integer", "minimum": 1},
                                    },
                                    "required": ["text", "start", "end"],
                                    "additionalProperties": False,
                                },
                                {"type": "null"},
                            ]
                        },
                        "provenance": {
                            "type": "string",
                            "enum": ["EXPLICIT_USER", "INCORPORATED_POLICY", "AUTHORITATIVE_EVIDENCE", "INFERENCE"],
                        },
                        "materiality": {"type": "number", "minimum": 0, "maximum": 1},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "hardness": {"type": "string", "enum": ["HARD", "SOFT"]},
                        "policy_class": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "negated": {"type": "boolean"},
                        "depends_on": {"type": "array", "items": {"type": "string"}},
                        "exception_to": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "clause_id", "clause_type", "normalized_value", "source_span", "provenance",
                        "materiality", "confidence", "hardness", "policy_class", "negated",
                        "depends_on", "exception_to",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["instruction", "schema_version", "clauses"],
        "additionalProperties": False,
    }

    SYSTEM_PROMPT = (
        "You are the ECOCOMMIT economic-intent compiler. Return only one JSON object matching the supplied contract. "
        "Your output is an untrusted candidate, never financial authority. Preserve every economically material statement. "
        "Use only clauses needed by the instruction. Treat the clause ontology literally: PRODUCT is the thing being acquired; "
        "QUANTITY is a count/volume; AMOUNT is a monetary bound or stated price; COUNTERPARTY is a named or described supplier; "
        "TEMPORAL is a deadline, delivery window, date, or duration such as 'within five days' or 'by Friday'; CERTIFICATION is an explicit grade/certification; "
        "REVERSIBILITY is a refundable/irreversible/payment-capture exposure constraint; AUTHORIZATION is explicit authority to buy/pay/authorize/capture; "
        "CONDITION is a non-temporal predicate that constrains an action; EXCEPTION is an unless/otherwise carve-out; DEPENDENCY is a prerequisite or ordering relationship between clauses. "
        "Rules: "
        "1) preserve do not/never/reject/excluding with negated=true on the affected clause; "
        "2) encode unless/otherwise/only if/provided that/in which case with EXCEPTION or exception_to, and when that phrase gates another action also preserve the gating relationship with depends_on or a DEPENDENCY clause; "
        "3) encode real if/before/after/until dependencies with DEPENDENCY or depends_on; do not infer 'if' from letters inside other words; a simple 'within N days' delivery deadline is TEMPORAL, not CONDITION or DEPENDENCY; "
        "4) preserve HARD versus SOFT and one-time versus recurring authority; "
        "5) PRODUCT should keep the complete stated product phrase, including grade/certification adjectives; CERTIFICATION may also be emitted; "
        "6) source_span.text must be an exact verbatim substring; the client recomputes offsets; "
        "7) vague terms such as around/reasonable/reliable/best/enough/usual/normal/suitable/appropriate must stay vague, receive lower confidence, and never become invented precision; "
        "8) EXPLICIT_USER requires an exact source span; use INFERENCE only for genuinely inferred meaning; "
        "9) INFERENCE must never create hard AMOUNT, AUTHORIZATION, or COUNTERPARTY authority; "
        "10) dependencies and exceptions must reference valid clause_id values; "
        "11) confidence means certainty that this clause faithfully extracts the user's explicit text, not trust in the supplier or desirability of the commercial term. Exact, unambiguous verbatim requirements should normally have high extraction confidence; lower confidence for genuine ambiguity or inference; "
        "12) emit a non-empty top-level clauses array, and for every emitted clause explicitly include clause_id, clause_type, normalized_value, source_span, provenance, materiality, confidence, hardness, policy_class, negated, depends_on, and exception_to. Never emit a partial clause. Omit a redundant AUTHORIZATION clause when it adds no distinct authorization scope rather than appending an incomplete trailing clause."
    )

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0,
        max_attempts: int = 5,
        reasoning_effort: str | None = None,
        max_retry_delay: float = 900.0,
        max_completion_tokens: int | None = None,
        use_json_schema: bool | None = None,
        allowed_hosts: set[str] | frozenset[str] | None = None,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ):
        self.base_url = self._validated_base_url(base_url, allowed_hosts)
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_attempts = max(1, max_attempts)
        self.reasoning_effort = reasoning_effort or os.getenv("ECOCOMMIT_LLM_REASONING_EFFORT")
        self.max_retry_delay = max(0.0, max_retry_delay)
        self.max_response_bytes = max(1, int(max_response_bytes))

        configured_max = os.getenv("ECOCOMMIT_LLM_MAX_COMPLETION_TOKENS")
        if max_completion_tokens is not None:
            self.max_completion_tokens = max(1, int(max_completion_tokens))
        elif configured_max:
            self.max_completion_tokens = max(1, int(configured_max))
        else:
            self.max_completion_tokens = None

        if use_json_schema is None:
            configured_schema = os.getenv("ECOCOMMIT_LLM_JSON_SCHEMA", "").strip().lower()
            self.use_json_schema = configured_schema in {"1", "true", "yes", "on"}
        else:
            self.use_json_schema = bool(use_json_schema)

    @classmethod
    def _validated_base_url(
        cls,
        base_url: str,
        allowed_hosts: set[str] | frozenset[str] | None,
    ) -> str:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("provider base URL must be an HTTPS origin/path without credentials, query, or fragment")

        configured = {
            item.strip().lower()
            for item in os.getenv("ECOCOMMIT_LLM_ALLOWED_HOSTS", "").split(",")
            if item.strip()
        }
        permitted = set(cls.DEFAULT_ALLOWED_HOSTS if allowed_hosts is None else allowed_hosts) | configured
        if parsed.hostname.lower() not in {host.lower() for host in permitted}:
            raise ValueError("provider host is not allowlisted")
        return base_url.rstrip("/")

    def _read_bounded(self, stream: Any) -> bytes:
        data = stream.read(self.max_response_bytes + 1)
        if len(data) > self.max_response_bytes:
            raise ProviderRequestError("RESPONSE_TOO_LARGE", attempts=1, transient=False)
        return data

    @staticmethod
    def _candidate_metadata(body: dict[str, Any], content: str, attempt: int) -> dict[str, Any]:
        choice = body.get("choices", [{}])[0] if isinstance(body.get("choices"), list) else {}
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        safe_usage = {
            key: int(usage[key])
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            if isinstance(usage.get(key), int) and usage[key] >= 0
        }
        request_id = body.get("id")
        return {
            "attempt": attempt,
            "candidate_sha256": sha256(content.encode("utf-8")).hexdigest(),
            "finish_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
            "request_id": request_id[:200] if isinstance(request_id, str) else None,
            "usage": safe_usage,
        }

    @staticmethod
    def _validation_issues(exc: Exception) -> list[dict[str, str]]:
        if isinstance(exc, _CandidateShapeError):
            return exc.issues[:32]
        if isinstance(exc, ValidationError):
            issues = []
            for item in exc.errors(include_input=False, include_url=False):
                location = ".".join(str(part) for part in item.get("loc", ())) or "root"
                issues.append({"location": location, "code": str(item.get("type", "invalid"))})
            return issues[:32] or [{"location": "root", "code": "invalid_contract"}]
        if isinstance(exc, json.JSONDecodeError):
            return [{"location": "root", "code": "invalid_json"}]
        if isinstance(exc, DuplicateJSONKeyError):
            return [{"location": "root", "code": "duplicate_json_key"}]
        if isinstance(exc, NonFiniteJSONValueError):
            return [{"location": "root", "code": "non_finite_number"}]
        if isinstance(exc, InvalidJSONValueError):
            return [{"location": "root", "code": "invalid_json_value"}]
        return [{"location": "root", "code": "malformed_provider_response"}]

    @classmethod
    def _candidate_shape_issues(cls, payload: Any, instruction: str) -> list[dict[str, str]]:
        """Reject omissions before Pydantic defaults can make a partial candidate look complete."""
        if not isinstance(payload, dict):
            return [{"location": "root", "code": "object_required"}]

        issues: list[dict[str, str]] = []
        top_properties = cls.STRICT_JSON_SCHEMA["properties"]
        for field in cls.STRICT_JSON_SCHEMA["required"]:
            if field not in payload:
                issues.append({"location": field, "code": "missing"})
        for field in payload:
            if field not in top_properties:
                issues.append({"location": field, "code": "unexpected"})
        if "instruction" in payload and payload["instruction"] != instruction:
            issues.append({"location": "instruction", "code": "original_mismatch"})

        clauses = payload.get("clauses")
        if not isinstance(clauses, list):
            return issues
        clause_schema = top_properties["clauses"]["items"]
        required_clause_fields = clause_schema["required"]
        clause_properties = clause_schema["properties"]
        for index, clause in enumerate(clauses):
            location = f"clauses.{index}"
            if not isinstance(clause, dict):
                issues.append({"location": location, "code": "object_required"})
                continue
            for field in required_clause_fields:
                if field not in clause:
                    issues.append({"location": f"{location}.{field}", "code": "missing"})
            for field in clause:
                if field not in clause_properties:
                    issues.append({"location": f"{location}.{field}", "code": "unexpected"})
            span = clause.get("source_span")
            if isinstance(span, dict):
                for field in ("text", "start", "end"):
                    if field not in span:
                        issues.append({"location": f"{location}.source_span.{field}", "code": "missing"})
                for field in span:
                    if field not in {"text", "start", "end"}:
                        issues.append({"location": f"{location}.source_span.{field}", "code": "unexpected"})
        return issues

    @staticmethod
    def _correction_message(issues: list[dict[str, str]]) -> str:
        compact = ", ".join(f"{i['location']} ({i['code']})" for i in issues)
        return (
            "The previous candidate was rejected by the local contract schema at: "
            f"{compact}. Generate a complete replacement from the original instruction. "
            "Return only JSON. The top-level clauses array must be non-empty and every emitted clause must explicitly contain all required fields, including numeric materiality and confidence."
        )

    @staticmethod
    def _repair_source_spans(payload: dict, instruction: str) -> dict:
        """Recompute offsets for exact model-supplied spans without filling candidate fields."""
        clauses = payload.get("clauses", [])
        for clause in clauses:
            span = clause.get("source_span")
            if not isinstance(span, dict):
                continue
            text = span.get("text")
            if not isinstance(text, str) or not text.strip():
                clause["source_span"] = None
                continue
            start = instruction.find(text)
            if start < 0:
                start = instruction.lower().find(text.lower())
                if start >= 0:
                    text = instruction[start:start + len(text)]
            if start < 0:
                clause["source_span"] = None
                continue
            span["text"] = text
            span["start"] = start
            span["end"] = start + len(text)
        return payload

    def interpret_with_metadata(self, instruction: str) -> InterpretationResult:
        user_content: dict[str, object] = {"instruction": instruction}
        if not self.use_json_schema:
            user_content["contract_shape"] = self.COMPACT_SCHEMA

        base_messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_content, separators=(",", ":"))},
        ]
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "messages": base_messages,
            "response_format": (
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "economic_intent_contract",
                        "strict": True,
                        "schema": self.STRICT_JSON_SCHEMA,
                    },
                }
                if self.use_json_schema
                else {"type": "json_object"}
            ),
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.max_completion_tokens is not None:
            payload["max_completion_tokens"] = self.max_completion_tokens

        provider_trace: list[dict[str, Any]] = []
        correction_used = False
        for attempt in range(1, self.max_attempts + 1):
            req = request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "ECOCOMMIT/0.1 (+https://github.com/sasipriya1221/sasipriya1221-ECOCOMMIT)",
                },
                method="POST",
            )
            try:
                with request.urlopen(req, timeout=self.timeout) as resp:
                    body = strict_json_loads(self._read_bounded(resp).decode("utf-8"))
                if not isinstance(body, dict):
                    raise TypeError("response object required")
                choices = body.get("choices")
                if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                    raise TypeError("response choice required")
                message = choices[0].get("message")
                content = message.get("content") if isinstance(message, dict) else None
                if not isinstance(content, str):
                    raise TypeError("candidate content required")
                candidate_meta = self._candidate_metadata(body, content, attempt)
                try:
                    raw = strict_json_loads(content)
                    shape_issues = self._candidate_shape_issues(raw, instruction)
                    if shape_issues:
                        raise _CandidateShapeError(shape_issues)
                    repaired = self._repair_source_spans(raw, instruction)
                    contract = EconomicIntentContract.model_validate(repaired)
                except (
                    json.JSONDecodeError,
                    DuplicateJSONKeyError,
                    InvalidJSONValueError,
                    NonFiniteJSONValueError,
                    ValidationError,
                    _CandidateShapeError,
                    TypeError,
                    KeyError,
                ) as exc:
                    issues = self._validation_issues(exc)
                    provider_trace.append({**candidate_meta, "outcome": "schema_invalid", "issues": issues})
                    if not correction_used and attempt < self.max_attempts:
                        correction_used = True
                        payload["messages"] = base_messages + [
                            {"role": "user", "content": self._correction_message(issues)}
                        ]
                        continue
                    raise CandidateContractError(issues, provider_trace) from exc
                provider_trace.append({**candidate_meta, "outcome": "accepted"})
                return InterpretationResult(contract=contract, provider_trace=tuple(provider_trace))
            except (
                json.JSONDecodeError,
                DuplicateJSONKeyError,
                InvalidJSONValueError,
                NonFiniteJSONValueError,
                TypeError,
                KeyError,
                IndexError,
            ) as exc:
                trace = provider_trace + [{
                    "attempt": attempt,
                    "outcome": "provider_error",
                    "code": "MALFORMED_RESPONSE",
                    "transient": False,
                }]
                raise ProviderRequestError(
                    "MALFORMED_RESPONSE",
                    attempts=attempt,
                    transient=False,
                    provider_trace=trace,
                ) from exc
            except ProviderRequestError as exc:
                trace = provider_trace + [{
                    "attempt": attempt,
                    "outcome": "provider_error",
                    "code": exc.code,
                    "transient": exc.transient,
                }]
                raise ProviderRequestError(
                    exc.code,
                    attempts=attempt,
                    transient=exc.transient,
                    provider_trace=trace,
                ) from exc
            except error.HTTPError as exc:
                try:
                    self._read_bounded(exc)
                except Exception:
                    pass

                retryable = exc.code == 429 or 500 <= exc.code <= 599
                if retryable and attempt < self.max_attempts:
                    provider_trace.append({
                        "attempt": attempt,
                        "outcome": "provider_error",
                        "code": f"HTTP_{exc.code}",
                        "transient": True,
                    })
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    try:
                        provider_delay = float(retry_after) if retry_after is not None else 0.0
                    except ValueError:
                        provider_delay = 0.0
                    exponential = min(8.0, 2.0 ** (attempt - 1))
                    # Respect the provider retry window but retain a hard ceiling so
                    # one request cannot stall CI indefinitely. The default ceiling
                    # is long enough for Groq's rolling free-tier token windows.
                    delay = min(self.max_retry_delay, max(exponential, provider_delay))
                    time.sleep(delay)
                    continue

                trace = provider_trace + [{
                    "attempt": attempt,
                    "outcome": "provider_error",
                    "code": f"HTTP_{exc.code}",
                    "transient": retryable,
                }]
                raise ProviderRequestError(
                    f"HTTP_{exc.code}",
                    attempts=attempt,
                    transient=retryable,
                    provider_trace=trace,
                ) from exc
            except (error.URLError, TimeoutError) as exc:
                if attempt < self.max_attempts:
                    provider_trace.append({
                        "attempt": attempt,
                        "outcome": "provider_error",
                        "code": "TRANSPORT_ERROR",
                        "transient": True,
                    })
                    time.sleep(min(self.max_retry_delay, min(8.0, 2.0 ** (attempt - 1))))
                    continue
                trace = provider_trace + [{
                    "attempt": attempt,
                    "outcome": "provider_error",
                    "code": "TRANSPORT_ERROR",
                    "transient": True,
                }]
                raise ProviderRequestError(
                    "TRANSPORT_ERROR",
                    attempts=attempt,
                    transient=True,
                    provider_trace=trace,
                ) from exc

        raise ProviderRequestError("RETRY_EXHAUSTED", attempts=self.max_attempts, transient=True)

    def interpret(self, instruction: str) -> EconomicIntentContract:
        return self.interpret_with_metadata(instruction).contract

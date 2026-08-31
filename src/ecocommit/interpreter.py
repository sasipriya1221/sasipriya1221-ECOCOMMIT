from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from urllib import error, request

from .contracts import EconomicIntentContract


class IntentProvider(ABC):
    @abstractmethod
    def interpret(self, instruction: str) -> EconomicIntentContract:
        raise NotImplementedError


class OpenAICompatibleIntentProvider(IntentProvider):
    """OpenAI-compatible provider with local grounding and bounded retry behavior."""

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

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0,
        max_attempts: int = 4,
        reasoning_effort: str | None = None,
        max_retry_delay: float = 65.0,
        max_completion_tokens: int | None = None,
        use_json_schema: bool | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_attempts = max(1, max_attempts)
        self.reasoning_effort = reasoning_effort or os.getenv("ECOCOMMIT_LLM_REASONING_EFFORT")
        self.max_retry_delay = max(0.0, max_retry_delay)

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

    @staticmethod
    def _repair_source_spans(payload: dict, instruction: str) -> dict:
        """Repair exact user spans and derive only provenance proven by those spans."""
        for clause in payload.get("clauses", []):
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
            # Exact grounding in the original instruction proves EXPLICIT_USER
            # provenance when the model omitted only that field. We intentionally
            # do not manufacture provenance for ungrounded clauses.
            if not clause.get("provenance"):
                clause["provenance"] = "EXPLICIT_USER"
        payload["instruction"] = instruction
        payload["schema_version"] = "0.1"
        return payload

    def interpret(self, instruction: str) -> EconomicIntentContract:
        system = (
            "You are the ECOCOMMIT economic-intent compiler. Return only one JSON object matching the supplied contract. "
            "Your output is an untrusted candidate, never financial authority. Preserve every economically material statement. "
            "Use only clauses needed by the instruction. Rules: "
            "1) preserve do not/never/reject/excluding with negated=true on the affected clause; "
            "2) encode unless/otherwise/only if/provided that/in which case with EXCEPTION or exception_to; "
            "3) encode real if/before/after/until dependencies with DEPENDENCY or depends_on; do not infer 'if' from letters inside other words; "
            "4) preserve HARD versus SOFT and one-time versus recurring authority; "
            "5) PRODUCT should keep the complete stated product phrase, including grade/certification adjectives; CERTIFICATION may also be emitted; "
            "6) source_span.text must be an exact verbatim substring; the client recomputes offsets; "
            "7) vague terms such as around/reasonable/reliable/best/enough/usual/normal/suitable/appropriate must stay vague, receive lower confidence, and never become invented precision; "
            "8) EXPLICIT_USER requires an exact source span; use INFERENCE only for genuinely inferred meaning; "
            "9) INFERENCE must never create hard AMOUNT, AUTHORIZATION, or COUNTERPARTY authority; "
            "10) dependencies and exceptions must reference valid clause_id values."
        )
        user_content: dict[str, object] = {"instruction": instruction}
        if not self.use_json_schema:
            user_content["contract_shape"] = self.COMPACT_SCHEMA

        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_content, separators=(",", ":"))},
            ],
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
                    body = json.loads(resp.read().decode("utf-8"))
                raw = json.loads(body["choices"][0]["message"]["content"])
                repaired = self._repair_source_spans(raw, instruction)
                return EconomicIntentContract.model_validate(repaired)
            except error.HTTPError as exc:
                try:
                    provider_body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    provider_body = "<unavailable>"

                retryable = exc.code == 429 or 500 <= exc.code <= 599
                if retryable and attempt < self.max_attempts:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    try:
                        provider_delay = float(retry_after) if retry_after is not None else 0.0
                    except ValueError:
                        provider_delay = 0.0
                    exponential = min(8.0, 2.0 ** (attempt - 1))
                    # Respect the provider retry window but retain a hard ceiling so
                    # one request cannot stall CI indefinitely.
                    delay = min(self.max_retry_delay, max(exponential, provider_delay))
                    time.sleep(delay)
                    continue

                raise RuntimeError(f"provider HTTP {exc.code} after {attempt} attempt(s): {provider_body}") from exc
            except (error.URLError, TimeoutError) as exc:
                if attempt < self.max_attempts:
                    time.sleep(min(self.max_retry_delay, min(8.0, 2.0 ** (attempt - 1))))
                    continue
                raise RuntimeError(f"provider transport error after {attempt} attempt(s): {exc}") from exc

        raise RuntimeError("provider request exhausted retry loop")

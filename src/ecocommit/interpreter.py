from __future__ import annotations

import json
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

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30.0, max_attempts: int = 4):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_attempts = max(1, max_attempts)

    @staticmethod
    def _repair_source_spans(payload: dict, instruction: str) -> dict:
        """Recompute offsets from exact quoted source text rather than trusting the LLM."""
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
        payload["instruction"] = instruction
        payload["schema_version"] = "0.1"
        return payload

    def interpret(self, instruction: str) -> EconomicIntentContract:
        system = (
            "You are the ECOCOMMIT economic-intent compiler. Return only one JSON object matching the supplied compact contract shape. "
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
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps({"instruction": instruction, "contract_shape": self.COMPACT_SCHEMA}, separators=(",", ":"))},
            ],
            "response_format": {"type": "json_object"},
        }

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
                    # Bound provider-directed sleeps so a single request cannot stall CI indefinitely.
                    delay = min(30.0, max(exponential, provider_delay))
                    time.sleep(delay)
                    continue

                raise RuntimeError(f"provider HTTP {exc.code} after {attempt} attempt(s): {provider_body}") from exc

        raise RuntimeError("provider request exhausted retry loop")

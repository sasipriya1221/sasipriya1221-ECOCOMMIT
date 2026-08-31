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
    """Minimal provider for an OpenAI-compatible chat endpoint.

    Credentials are supplied at runtime and never stored in the repository.
    Checkpoint A requires a real configured model; offline fixtures do not count.
    Provider-produced source offsets are treated as untrusted metadata: exact source
    text is grounded locally against the original instruction before schema validation.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0,
        max_attempts: int = 4,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_attempts = max(1, max_attempts)

    @staticmethod
    def _repair_source_spans(payload: dict, instruction: str) -> dict:
        """Recompute offsets from exact quoted source text rather than trusting the LLM.

        If the quoted text cannot be found exactly (case-sensitive first, then
        case-insensitive), the span is removed. This fails closed in the fidelity
        validator instead of accepting fabricated offsets.
        """
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
        return payload

    def interpret(self, instruction: str) -> EconomicIntentContract:
        schema = EconomicIntentContract.model_json_schema()
        system = (
            "You are the ECOCOMMIT economic-intent compiler. Return only one JSON object conforming to the supplied schema. "
            "Your output is an untrusted candidate contract, not financial authority. Preserve every economically material statement. "
            "Rules: (1) preserve negations such as do not/never/reject with negated=true on the affected clause; "
            "(2) represent actual exceptions such as unless/otherwise/only if/provided that using EXCEPTION or exception_to; "
            "(3) represent actual conditional or ordering relationships such as if/before/after/until using DEPENDENCY or depends_on; "
            "(4) do not invent dependencies merely because a word contains letters such as 'if'; "
            "(5) preserve hard versus soft requirements and one-time versus recurring authorization; "
            "(6) for PRODUCT keep the complete product phrase stated by the user, including stated grade/certification adjectives, while optionally also emitting CERTIFICATION; "
            "(7) source_span.text MUST be an exact verbatim substring of the instruction; offsets may be approximate because the client recomputes them; "
            "(8) vague terms such as around, reasonable, reliable, best, enough, usual, normal, suitable, appropriate, or similar open-textured commercial language must not be converted into invented precise constraints; encode them with lower confidence and never expand authority; "
            "(9) every EXPLICIT_USER clause must be grounded to the exact user phrase; use INFERENCE only for genuinely inferred meaning; "
            "(10) never invent hard financial authority."
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps({"instruction": instruction, "schema": schema})},
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
                        delay = float(retry_after) if retry_after is not None else min(8.0, 2.0 ** (attempt - 1))
                    except ValueError:
                        delay = min(8.0, 2.0 ** (attempt - 1))
                    time.sleep(delay)
                    continue

                raise RuntimeError(
                    f"provider HTTP {exc.code} after {attempt} attempt(s): {provider_body}"
                ) from exc

        raise RuntimeError("provider request exhausted retry loop")

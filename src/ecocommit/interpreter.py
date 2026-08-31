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

    Transient 429/5xx responses are retried with bounded exponential backoff.
    Permanent HTTP failures include the provider error body in the raised exception
    so CI can distinguish quota/billing/model errors from ECOCOMMIT semantic failures.
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

    def interpret(self, instruction: str) -> EconomicIntentContract:
        schema = EconomicIntentContract.model_json_schema()
        system = (
            "You are the ECOCOMMIT intent interpreter. Produce only JSON conforming to the supplied schema. "
            "Preserve negations, exceptions, dependencies, hard/soft limits, one-time/recurring authority, and exact source spans. "
            "Never invent hard financial authority. If material meaning is uncertain, lower confidence; do not guess."
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
                return EconomicIntentContract.model_validate_json(body["choices"][0]["message"]["content"])
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

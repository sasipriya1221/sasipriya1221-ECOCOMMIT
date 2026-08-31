from __future__ import annotations

import json
from abc import ABC, abstractmethod
from urllib import request

from .contracts import EconomicIntentContract


class IntentProvider(ABC):
    @abstractmethod
    def interpret(self, instruction: str) -> EconomicIntentContract:
        raise NotImplementedError


class OpenAICompatibleIntentProvider(IntentProvider):
    """Minimal provider for an OpenAI-compatible chat endpoint.

    Credentials are supplied at runtime and never stored in the repository.
    Checkpoint A requires a real configured model; offline fixtures do not count.
    """

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

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
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return EconomicIntentContract.model_validate_json(body["choices"][0]["message"]["content"])

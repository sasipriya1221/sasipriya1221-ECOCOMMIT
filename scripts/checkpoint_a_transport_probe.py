from __future__ import annotations

import json
import os

from ecocommit.interpreter import OpenAICompatibleIntentProvider


def main() -> int:
    api_key = os.getenv("ECOCOMMIT_LLM_API_KEY")
    if not api_key:
        raise SystemExit("ECOCOMMIT_LLM_API_KEY is required")

    base_url = os.getenv("ECOCOMMIT_LLM_BASE_URL", "https://api.groq.com/openai/v1")
    model = os.getenv("ECOCOMMIT_LLM_MODEL", "qwen/qwen3.6-27b")
    instruction = "Buy 5 certified bearings from Vendor A for no more than ₹1 lakh."

    provider = OpenAICompatibleIntentProvider(
        base_url,
        api_key,
        model,
        timeout=60.0,
        max_attempts=1,
        reasoning_effort="none",
        max_retry_delay=0.0,
        max_completion_tokens=1024,
        use_json_schema=False,
    )
    contract = provider.interpret(instruction)
    print(json.dumps({
        "transport": "ok",
        "model": model,
        "clause_count": len(contract.clauses),
        "schema_version": contract.schema_version,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

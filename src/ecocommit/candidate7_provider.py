from __future__ import annotations

import json
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from urllib import error, request
from urllib.parse import urlsplit

from pydantic import ValidationError

from ._canonical import strict_json_loads
from .candidate7_flat import (
    FactBatch,
    FactKind,
    LabeledFact,
    RelationBatch,
    assign_fact_ids,
    drop_ungrounded_relations,
    grounded_span,
)
from .candidate7_relation_checklist import (
    Pass2DecisionBatch,
    action_entity_pair_payload,
    validate_and_materialize_pass2,
)
from .candidate7_structure import _ACTION_PATTERNS, _action_kind
from .interpreter import ProviderRequestError


ACTION_TYPE_VALUES = frozenset(kind for kind, _ in _ACTION_PATTERNS)


PASS1_SYSTEM_PROMPT = """You are ECOCOMMIT Candidate 7 pass 1: a semantic fact extractor.
Extract only source-grounded semantic facts from the user's instruction.
Output one flat JSON object with key `facts`.
Each fact has exactly:
  text_span: {quote: exact verbatim substring from the instruction, occurrence: positive integer}
  kind: ENTITY | ACTION | CONSTRAINT | PREDICATE | EXCEPTION | AMBIGUITY
  polarity: POSITIVE | NEGATED
  action_type: required only when kind=ACTION; one of BUY | ORDER | PAY | TRANSFER | HIRE | BOOK | RENEW | RESERVE | SELECT | RELEASE | CANCEL | COMMIT
Rules:
- NO IDs. Do not create identifiers, labels, references, keys, handles, indexes, or names for facts.
- NO cross-references. NO nesting beyond text_span. NO Boolean operators or Boolean trees.
- Do not paraphrase text_span.quote. It must be copied verbatim from the instruction.
- For every ACTION fact, text_span.quote MUST contain the instruction's own explicit action/domain verb verbatim. Never replace, normalize, synonymize, infer, or substitute a different action verb. Use the smallest source span that preserves that explicit action and its directly stated object/quantity when present.
- If the instruction does not contain an explicit action verb, do not invent an ACTION fact merely to fit a known action category.
- Extract entities separately from actions when they participate as an action object or counterparty.
- Extract each economically meaningful action separately.
- Extract monetary caps/exact/minimum constraints as CONSTRAINT facts.
- Extract authorization conditions as PREDICATE facts; preserve lexical negation using polarity=NEGATED only when the predicate itself is negated.
- Extract explicit exception phrases as EXCEPTION facts.
- Extract genuinely unresolved material semantics as AMBIGUITY facts. Absence alone is not ambiguity.
- Never invent optional missing budget, counterparty, time, date, duration, provider, payment method, or location.
JSON only."""


PASS2_SYSTEM_PROMPT = """You are ECOCOMMIT Candidate 7 pass 2: an exhaustive relation classifier.
You receive an ID-labeled flat fact list plus a deterministic `action_entity_pairs` checklist.
Output one flat JSON object with exactly two keys: `action_entity_decisions` and `relations`.

For EVERY supplied ACTION x ENTITY pair, emit exactly one action_entity_decision with exactly:
  action: supplied ACTION F####
  entity: supplied ENTITY F####
  decision: ACTION_OBJECT | ACTION_COUNTERPARTY | NONE
  justification_span: exact verbatim substring establishing the relation, or null when decision=NONE
No supplied pair may be omitted, duplicated, or replaced with a different pair.

The `relations` list is only for non-ACTION×ENTITY relations. Each relation has exactly:
  kind, left, right, justification_span
Allowed relation kinds there:
PREDICATE_SUBJECT, CONSTRAINT_APPLIES_TO, GUARDS_ACTION, BLOCKS_ACTION,
AFTER_COMPLETION, AFTER_SUCCESS, EXCEPTION_TARGET, EXCEPTION_WHEN,
AMBIGUITY_TARGET, ALL_OF, ANY_OF.

Rules:
- ACTION_OBJECT and ACTION_COUNTERPARTY MUST be expressed only through `action_entity_decisions`, never in `relations`.
- `NONE` is a first-class required decision when a supplied ACTION×ENTITY pair has no explicit semantic relationship.
- Every non-NONE justification_span must be an exact verbatim substring of the instruction that establishes the claimed relationship.
- Prefer source-local evidence: an entity contained in or immediately following an action phrase is normally the direct action-object candidate. Do not let a trailing purpose, condition, or sequence phrase beginning with words such as `for`, `if`, or `after` automatically replace a source-local direct object.
- You may reference ONLY the existing F#### IDs supplied in the input.
- Do not create any new identifier of any kind.
- Do not output facts, prose, nested Boolean ASTs, groups, or derived semantic objects.
- ALL_OF and ANY_OF classify pairwise logical relationships between existing PREDICATE facts only.
- GUARDS_ACTION means the predicate must explicitly be an authorization condition for the action to execute. Do not infer GUARDS_ACTION from mere proximity, topic similarity, sequence, or co-occurrence.
- BLOCKS_ACTION means the predicate explicitly prevents the action when it holds.
- AFTER_COMPLETION / AFTER_SUCCESS are directed: left is the later/dependent ACTION, right is the prerequisite ACTION.
- EXCEPTION_WHEN is directed: left is PREDICATE, right is EXCEPTION.
- Other directed relation names follow their English reading.
- Emit only source-supported non-ACTION×ENTITY relations in `relations`; an empty `relations` list is equally valid.
- Example valid empty non-ACTION×ENTITY relation list: {"relations":[]}.
- Do not invent a relation merely to avoid an empty `relations` list.
JSON only."""


@dataclass(frozen=True)
class Candidate7ParseResult:
    facts: tuple[LabeledFact, ...]
    relations: RelationBatch
    provider_trace: tuple[dict[str, Any], ...]


class Candidate7SchemaError(RuntimeError):
    def __init__(self, stage: str, issues: list[dict[str, str]], trace: list[dict[str, Any]]):
        self.stage = stage
        self.issues = tuple(issues)
        self.provider_trace = tuple(trace)
        super().__init__(f"candidate7 {stage} remained schema-invalid")


class GroqCandidate7Provider:
    DEFAULT_ALLOWED_HOSTS = frozenset({"api.groq.com"})
    MAX_RESPONSE_BYTES = 1_048_576
    RATE_LIMIT_HEADER_NAMES = (
        "x-ratelimit-limit-requests",
        "x-ratelimit-remaining-requests",
        "x-ratelimit-reset-requests",
        "x-ratelimit-limit-tokens",
        "x-ratelimit-remaining-tokens",
        "x-ratelimit-reset-tokens",
        "retry-after",
    )

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.groq.com/openai/v1",
        model: str = "qwen/qwen3.6-27b",
        timeout: float = 60.0,
        max_attempts_per_pass: int = 2,
        max_completion_tokens: int = 1536,
        max_retry_delay: float = 900.0,
        min_request_interval_seconds: float = 3.0,
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.hostname not in self.DEFAULT_ALLOWED_HOSTS or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("provider base URL is not permitted")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = float(timeout)
        self.max_attempts_per_pass = max(1, int(max_attempts_per_pass))
        self.max_completion_tokens = max(1, int(max_completion_tokens))
        self.max_retry_delay = max(0.0, float(max_retry_delay))
        self.min_request_interval_seconds = max(0.0, float(min_request_interval_seconds))
        self._last_request_started: float | None = None

    @staticmethod
    def _issues(exc: Exception) -> list[dict[str, str]]:
        if isinstance(exc, ValidationError):
            return [
                {"location": ".".join(str(part) for part in item.get("loc", ())) or "root", "code": str(item.get("type", "invalid"))}
                for item in exc.errors(include_input=False, include_url=False)[:32]
            ]
        code = str(exc) if isinstance(exc, ValueError) and str(exc).startswith("C7_") else type(exc).__name__
        return [{"location": "root", "code": code}]

    @classmethod
    def _rate_limit_headers(cls, headers: Any) -> dict[str, str]:
        if headers is None:
            return {}
        captured: dict[str, str] = {}
        for name in cls.RATE_LIMIT_HEADER_NAMES:
            value = headers.get(name)
            if value is not None:
                captured[name] = str(value).strip()
        return captured

    @staticmethod
    def _validate_action_types_raw(parsed: Any) -> None:
        """Branch 1c: deterministic ACTION vocabulary validation in the existing retry path."""
        if not isinstance(parsed, dict):
            return
        facts = parsed.get("facts")
        if not isinstance(facts, list):
            return
        for item in facts:
            if not isinstance(item, dict):
                continue
            kind = item.get("kind")
            action_type = item.get("action_type")
            if kind == FactKind.ACTION.value:
                if action_type is None:
                    raise ValueError("C7_ACTION_TYPE_MISSING")
                if action_type not in ACTION_TYPE_VALUES:
                    raise ValueError("C7_ACTION_TYPE_OUT_OF_VOCAB")
            elif action_type is not None:
                raise ValueError("C7_ACTION_TYPE_ON_NON_ACTION")

    def _pace_request(self) -> None:
        now = time.monotonic()
        if self._last_request_started is not None:
            remaining = self.min_request_interval_seconds - (now - self._last_request_started)
            if remaining > 0:
                time.sleep(remaining)
                now = time.monotonic()
        self._last_request_started = now

    def _request(self, messages: list[dict[str, str]], attempt: int) -> tuple[dict[str, Any], dict[str, Any]]:
        self._pace_request()
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_completion_tokens": self.max_completion_tokens,
            "response_format": {"type": "json_object"},
            "reasoning_effort": "none",
            "messages": messages,
        }
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, separators=(",", ":")).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "ECOCOMMIT-Candidate7/1"},
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
        except error.HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            rate_headers = self._rate_limit_headers(exc.headers)
            retry_after = 0.0
            try:
                retry_after = min(max(0.0, float(rate_headers.get("retry-after", 0.0))), 3600.0)
            except (TypeError, ValueError):
                pass
            provider_exc = ProviderRequestError(f"HTTP_{exc.code}", attempts=attempt, transient=retryable)
            provider_exc.retry_after_seconds = retry_after
            provider_exc.rate_limit_headers = rate_headers
            raise provider_exc from exc
        except (error.URLError, TimeoutError) as exc:
            raise ProviderRequestError("TRANSPORT_ERROR", attempts=attempt, transient=True) from exc

        body = strict_json_loads(raw.decode())
        choices = body.get("choices") if isinstance(body, dict) else None
        message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise ProviderRequestError("MALFORMED_RESPONSE", attempts=attempt, transient=False)
        metadata = {
            "attempt": attempt,
            "candidate_sha256": sha256(content.encode()).hexdigest(),
            "finish_reason": choices[0].get("finish_reason") if isinstance(choices[0], dict) else None,
        }
        return strict_json_loads(content), metadata

    def _run_stage(self, stage: str, base_messages: list[dict[str, str]], validator) -> tuple[Any, list[dict[str, Any]]]:
        trace: list[dict[str, Any]] = []
        messages = list(base_messages)
        for attempt in range(1, self.max_attempts_per_pass + 1):
            try:
                parsed, metadata = self._request(messages, attempt)
            except ProviderRequestError as exc:
                entry = {"stage": stage, "attempt": attempt, "outcome": "provider_error", "code": exc.code, "transient": exc.transient}
                rate_headers = dict(getattr(exc, "rate_limit_headers", {}) or {})
                if rate_headers:
                    entry["rate_limit_headers"] = rate_headers
                trace.append(entry)
                if exc.transient and attempt < self.max_attempts_per_pass:
                    delay = max(2 ** (attempt - 1), float(getattr(exc, "retry_after_seconds", 0.0) or 0.0))
                    time.sleep(min(self.max_retry_delay, delay))
                    continue
                exc.provider_trace = trace
                raise
            try:
                value = validator(parsed)
            except (ValidationError, ValueError, TypeError) as exc:
                issues = self._issues(exc)
                trace.append({"stage": stage, **metadata, "outcome": "schema_invalid", "issues": issues})
                if attempt < self.max_attempts_per_pass:
                    messages = base_messages + [{
                        "role": "user",
                        "content": "The previous JSON failed schema/reference validation at: "
                        + ", ".join(f"{x['location']} ({x['code']})" for x in issues)
                        + ". Return a complete replacement obeying the same stage contract. Do not use evaluator results or semantic scores. JSON only.",
                    }]
                    continue
                raise Candidate7SchemaError(stage, issues, trace) from exc
            trace.append({"stage": stage, **metadata, "outcome": "accepted"})
            return value, trace
        raise Candidate7SchemaError(stage, [{"location": "root", "code": "attempts_exhausted"}], trace)

    def parse_with_metadata(self, instruction: str) -> Candidate7ParseResult:
        pass1_messages = [
            {"role": "system", "content": PASS1_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"instruction": instruction}, separators=(",", ":"))},
        ]

        def validate_facts(parsed: Any) -> tuple[LabeledFact, ...]:
            self._validate_action_types_raw(parsed)
            batch = FactBatch.model_validate(parsed)
            labeled = assign_fact_ids(batch)
            for fact in labeled:
                grounded_span(instruction, fact.text_span)
                if fact.kind is FactKind.ACTION:
                    if fact.action_type != _action_kind(fact.text_span.quote):
                        raise ValueError("C7_ACTION_TYPE_SPAN_MISMATCH")
            return labeled

        facts, trace1 = self._run_stage("facts", pass1_messages, validate_facts)
        labeled_payload = [fact.model_dump(mode="json") for fact in facts]
        pass2_messages = [
            {"role": "system", "content": PASS2_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({
                "instruction": instruction,
                "facts": labeled_payload,
                "action_entity_pairs": action_entity_pair_payload(facts),
            }, separators=(",", ":"))},
        ]

        def validate_relation_batch(parsed: Any) -> RelationBatch:
            decision_batch = Pass2DecisionBatch.model_validate(parsed)
            return validate_and_materialize_pass2(instruction, facts, decision_batch)

        relations, trace2 = self._run_stage("relations", pass2_messages, validate_relation_batch)
        grounded_relations, grounding_events = drop_ungrounded_relations(instruction, relations)
        trace2.extend({"stage": "relations", **event} for event in grounding_events)
        return Candidate7ParseResult(facts, grounded_relations, tuple(trace1 + trace2))

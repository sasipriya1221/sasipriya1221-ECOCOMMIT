from __future__ import annotations

import json
from datetime import date, datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any

from pydantic import BaseModel


class DuplicateJSONKeyError(ValueError):
    """Strict JSON input contained two members with the same name."""


class NonFiniteJSONValueError(ValueError):
    """Strict JSON input used NaN or Infinity, which JSON does not permit."""


class InvalidJSONValueError(ValueError):
    """Strict JSON input exceeded safe structure or Unicode constraints."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateJSONKeyError("duplicate JSON keys are forbidden")
        value[key] = item
    return value


def _reject_nonfinite(value: str) -> None:
    del value
    raise NonFiniteJSONValueError("non-finite JSON numbers are forbidden")


def strict_json_loads(value: str) -> Any:
    """Decode standards-compliant JSON without duplicate-key overwrites."""

    try:
        decoded = json.loads(
            value,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite,
        )
    except (json.JSONDecodeError, DuplicateJSONKeyError, NonFiniteJSONValueError):
        raise
    except (ValueError, RecursionError) as exc:
        raise InvalidJSONValueError("JSON value is too complex or invalid") from exc

    stack: list[tuple[Any, int]] = [(decoded, 0)]
    visited = 0
    while stack:
        item, depth = stack.pop()
        visited += 1
        if depth > 128 or visited > 100_000:
            raise InvalidJSONValueError("JSON structure exceeds safe limits")
        if isinstance(item, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in item):
                raise InvalidJSONValueError("unpaired Unicode surrogate is forbidden")
        elif isinstance(item, dict):
            stack.extend((key, depth + 1) for key in item)
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
    return decoded


def _json_ready(value: Any) -> Any:
    if isinstance(value, BaseModel):
        # Recurse through Python-mode data so nested and top-level datetimes use
        # one representation. Pydantic JSON mode otherwise emits UTC as ``Z``
        # while datetime.isoformat() emits ``+00:00``, breaking round-trip hashes.
        return _json_ready(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_json_ready(item) for item in value), key=str)
    return value


def canonical_bytes(value: Any) -> bytes:
    """Return a stable representation suitable for hashes and local signatures."""

    return json.dumps(
        _json_ready(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    return sha256(canonical_bytes(value)).hexdigest()

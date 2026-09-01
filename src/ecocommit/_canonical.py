from __future__ import annotations

import json
from datetime import date, datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any

from pydantic import BaseModel


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

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from threading import Condition, RLock, get_ident
from typing import Callable, Generic, Protocol, TypeVar

from ._canonical import sha256_hex


T = TypeVar("T")


class IdempotencyError(RuntimeError):
    pass


class IdempotencyConflict(IdempotencyError):
    pass


class IdempotencyReentry(IdempotencyError):
    pass


class IdempotencyBackend(Protocol):
    def execute(
        self,
        *,
        scope: str,
        key: str,
        fingerprint: str,
        operation: Callable[[], T],
    ) -> T: ...

    def completed_count(self) -> int: ...


class _EntryStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"


@dataclass
class _Entry(Generic[T]):
    fingerprint: str
    status: _EntryStatus
    owner_thread: int
    result: T | None = None


def request_fingerprint(payload) -> str:
    return sha256_hex(payload)


class IdempotencyLedger:
    """Process-local exactly-once execution ledger with request collision checks."""

    def __init__(self):
        self._lock = RLock()
        self._condition = Condition(self._lock)
        self._entries: dict[tuple[str, str], _Entry] = {}

    def execute(
        self,
        *,
        scope: str,
        key: str,
        fingerprint: str,
        operation: Callable[[], T],
    ) -> T:
        if not scope or not key or not fingerprint:
            raise ValueError("idempotency scope, key, and fingerprint are required")
        identity = (scope, key)
        owner = get_ident()

        with self._condition:
            while True:
                entry = self._entries.get(identity)
                if entry is None:
                    self._entries[identity] = _Entry(
                        fingerprint=fingerprint,
                        status=_EntryStatus.PENDING,
                        owner_thread=owner,
                    )
                    break
                if entry.fingerprint != fingerprint:
                    raise IdempotencyConflict(
                        "idempotency key was reused with a different request fingerprint"
                    )
                if entry.status == _EntryStatus.COMPLETED:
                    return deepcopy(entry.result)
                if entry.owner_thread == owner:
                    raise IdempotencyReentry("operation recursively reused its own pending key")
                self._condition.wait()

        try:
            result = operation()
        except BaseException:
            # Failures are deliberately retryable. A later call must execute the
            # operation again rather than replaying a possibly transient failure.
            with self._condition:
                current = self._entries.get(identity)
                if current is not None and current.owner_thread == owner:
                    del self._entries[identity]
                    self._condition.notify_all()
            raise

        with self._condition:
            entry = self._entries[identity]
            entry.result = deepcopy(result)
            entry.status = _EntryStatus.COMPLETED
            self._condition.notify_all()
        return deepcopy(result)

    def completed_count(self) -> int:
        with self._lock:
            return sum(entry.status == _EntryStatus.COMPLETED for entry in self._entries.values())

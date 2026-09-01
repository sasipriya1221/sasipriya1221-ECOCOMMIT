from __future__ import annotations

import json
import os
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Callable, Mapping


GENESIS_HASH = "0" * 64
_RECORD_KEYS = {
    "sequence",
    "timestamp",
    "event_type",
    "correlation_id",
    "actor",
    "payload",
    "previous_hash",
    "event_hash",
}
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_PATH_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


class AuditIntegrityError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _normalized_mapping(value: Mapping[str, object]) -> dict[str, object]:
    if not all(isinstance(key, str) for key in value):
        raise TypeError("audit payload keys must be strings")
    try:
        normalized = json.loads(_canonical_json(dict(value)))
    except (TypeError, ValueError) as exc:
        raise TypeError("audit payload must be finite JSON data") from exc
    if not isinstance(normalized, dict):
        raise TypeError("audit payload must be a JSON object")
    return normalized


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AuditIntegrityError(f"duplicate audit JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str):
    raise AuditIntegrityError(f"non-finite audit JSON constant: {value}")


def _shared_path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    timestamp: str
    event_type: str
    correlation_id: str
    actor: str
    payload: Mapping[str, object]
    previous_hash: str
    event_hash: str

    def as_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "correlation_id": self.correlation_id,
            "actor": self.actor,
            "payload": dict(self.payload),
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
        }


@dataclass(frozen=True)
class AuditVerification:
    valid: bool
    entries: int
    head_hash: str
    error: str | None = None


class AppendOnlyAuditLog:
    """Fsynced hash chain with in-process and OS-level cross-process locking."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        requested = Path(path)
        if requested.exists() and requested.is_symlink():
            raise AuditIntegrityError("symlinked audit log is forbidden")
        self.path = requested.resolve()
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        if self.lock_path.exists() and self.lock_path.is_symlink():
            raise AuditIntegrityError("symlinked audit lock is forbidden")
        self._clock = clock
        # Multiple log objects in one process must serialize against the same
        # file; an instance-local lock permits lost updates and forked chains.
        self._lock = _shared_path_lock(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        verification = self.verify()
        if not verification.valid:
            raise AuditIntegrityError(verification.error or "audit log integrity check failed")

    @contextmanager
    def _exclusive_lock(self):
        """Serialize the read-verify-append transaction across local processes."""

        with self._lock:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open("a+b") as stream:
                if stream.seek(0, os.SEEK_END) == 0:
                    stream.write(b"\0")
                    stream.flush()
                    os.fsync(stream.fileno())
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
                    try:
                        yield
                    finally:
                        stream.seek(0)
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                    try:
                        yield
                    finally:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _event_material(record: Mapping[str, object]) -> dict[str, object]:
        return {key: record[key] for key in _RECORD_KEYS if key != "event_hash"}

    @classmethod
    def _expected_hash(cls, record: Mapping[str, object]) -> str:
        return sha256(_canonical_json(cls._event_material(record)).encode("utf-8")).hexdigest()

    def _read_records(self) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        with self.path.open("r", encoding="utf-8", newline="") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    raise AuditIntegrityError(f"blank audit record at line {line_number}")
                if not line.endswith("\n"):
                    raise AuditIntegrityError(
                        f"incomplete audit record at line {line_number}"
                    )
                try:
                    record = json.loads(
                        line,
                        object_pairs_hook=_unique_object,
                        parse_constant=_reject_constant,
                    )
                except (json.JSONDecodeError, AuditIntegrityError) as exc:
                    raise AuditIntegrityError(
                        f"invalid JSON audit record at line {line_number}"
                    ) from exc
                if not isinstance(record, dict) or set(record) != _RECORD_KEYS:
                    raise AuditIntegrityError(
                        f"unexpected audit record shape at line {line_number}"
                    )
                if line[:-1] != _canonical_json(record):
                    raise AuditIntegrityError(
                        f"non-canonical audit record at line {line_number}"
                    )
                records.append(record)
        return records

    def _verify_records(self, records: list[dict[str, object]]) -> AuditVerification:
        previous_hash = GENESIS_HASH
        for expected_sequence, record in enumerate(records, start=1):
            shape_error = self._record_shape_error(record)
            if shape_error:
                return AuditVerification(
                    False,
                    expected_sequence - 1,
                    previous_hash,
                    f"{shape_error} at entry {expected_sequence}",
                )
            if type(record["sequence"]) is not int or record["sequence"] != expected_sequence:
                return AuditVerification(
                    False,
                    expected_sequence - 1,
                    previous_hash,
                    f"sequence mismatch at entry {expected_sequence}",
                )
            if record["previous_hash"] != previous_hash:
                return AuditVerification(
                    False,
                    expected_sequence - 1,
                    previous_hash,
                    f"hash-chain mismatch at entry {expected_sequence}",
                )
            expected_hash = self._expected_hash(record)
            if record["event_hash"] != expected_hash:
                return AuditVerification(
                    False,
                    expected_sequence - 1,
                    previous_hash,
                    f"event hash mismatch at entry {expected_sequence}",
                )
            previous_hash = expected_hash
        return AuditVerification(True, len(records), previous_hash)

    @staticmethod
    def _record_shape_error(record: Mapping[str, object]) -> str | None:
        for key in ("event_type", "correlation_id", "actor"):
            value = record.get(key)
            if not isinstance(value, str) or not value or value != value.strip():
                return f"invalid {key}"
        timestamp = record.get("timestamp")
        if not isinstance(timestamp, str):
            return "invalid timestamp"
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError:
            return "invalid timestamp"
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return "non-timezone-aware timestamp"
        payload = record.get("payload")
        if not isinstance(payload, Mapping):
            return "invalid payload"
        try:
            normalized = _normalized_mapping(payload)
        except TypeError:
            return "invalid payload"
        if normalized != dict(payload):
            return "non-canonical payload"
        for key in ("previous_hash", "event_hash"):
            value = record.get(key)
            if not isinstance(value, str) or not _SHA256_HEX.fullmatch(value):
                return f"invalid {key}"
        return None

    def verify(self) -> AuditVerification:
        with self._exclusive_lock():
            try:
                records = self._read_records()
            except (AuditIntegrityError, OSError, UnicodeError) as exc:
                return AuditVerification(False, 0, GENESIS_HASH, str(exc))
            return self._verify_records(records)

    def append(
        self,
        event_type: str,
        correlation_id: str,
        payload: Mapping[str, object],
        *,
        actor: str = "ecocommit.service",
    ) -> AuditEvent:
        if not event_type or not event_type.strip():
            raise ValueError("event_type is required")
        if not correlation_id or not correlation_id.strip():
            raise ValueError("correlation_id is required")
        if not actor or not actor.strip():
            raise ValueError("actor is required")
        normalized_payload = _normalized_mapping(payload)

        with self._exclusive_lock():
            try:
                records = self._read_records()
            except (OSError, UnicodeError) as exc:
                raise AuditIntegrityError("audit log could not be read") from exc
            verification = self._verify_records(records)
            if not verification.valid:
                raise AuditIntegrityError(verification.error or "audit log integrity check failed")

            material: dict[str, object] = {
                "sequence": verification.entries + 1,
                "timestamp": self._clock().astimezone(timezone.utc).isoformat(),
                "event_type": event_type.strip(),
                "correlation_id": correlation_id.strip(),
                "actor": actor.strip(),
                "payload": normalized_payload,
                "previous_hash": verification.head_hash,
            }
            event_hash = sha256(_canonical_json(material).encode("utf-8")).hexdigest()
            record = {**material, "event_hash": event_hash}
            encoded = _canonical_json(record)

            try:
                with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(encoded + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError as exc:
                raise AuditIntegrityError("audit event could not be durably appended") from exc

            return AuditEvent(
                sequence=int(material["sequence"]),
                timestamp=str(material["timestamp"]),
                event_type=str(material["event_type"]),
                correlation_id=str(material["correlation_id"]),
                actor=str(material["actor"]),
                payload=normalized_payload,
                previous_hash=str(material["previous_hash"]),
                event_hash=event_hash,
            )
    def events(self) -> tuple[AuditEvent, ...]:
        with self._exclusive_lock():
            records = self._read_records()
            verification = self._verify_records(records)
            if not verification.valid:
                raise AuditIntegrityError(verification.error or "audit log integrity check failed")
            return tuple(
                AuditEvent(
                    sequence=int(record["sequence"]),
                    timestamp=str(record["timestamp"]),
                    event_type=str(record["event_type"]),
                    correlation_id=str(record["correlation_id"]),
                    actor=str(record["actor"]),
                    payload=dict(record["payload"]),
                    previous_hash=str(record["previous_hash"]),
                    event_hash=str(record["event_hash"]),
                )
                for record in records
            )

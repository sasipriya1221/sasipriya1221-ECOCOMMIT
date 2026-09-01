from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Callable, Mapping

from pydantic import BaseModel

from ._canonical import canonical_bytes
from .idempotency import IdempotencyConflict, IdempotencyReentry


class DurableStateError(RuntimeError):
    pass


class DurableStateConflict(DurableStateError):
    pass


class DurableStateIntegrityError(DurableStateError):
    pass


def _reject_constant(value: str):
    raise DurableStateIntegrityError(f"non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DurableStateIntegrityError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _strict_json_loads(encoded: str | bytes):
    return json.loads(
        encoded,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )


@dataclass(frozen=True)
class StoredJSONDocument:
    namespace: str
    key: str
    version: int
    payload_sha256: str
    value: object


@dataclass(frozen=True)
class _CompletedResult:
    value: object


class SQLiteJSONStateStore:
    """Single-host durable JSON store with SQLite WAL and optimistic CAS."""

    def __init__(
        self,
        path: str | Path,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("SQLite timeout must be positive")
        requested = Path(path)
        if requested.exists() and requested.is_symlink():
            raise DurableStateError("symlinked SQLite state database is forbidden")
        requested.parent.mkdir(parents=True, exist_ok=True)
        self.path = requested.resolve()
        self.timeout_seconds = timeout_seconds
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS state_documents (
                    namespace TEXT NOT NULL,
                    document_key TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK(version > 0),
                    payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
                    payload_json TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY(namespace, document_key)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=self.timeout_seconds,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout={int(self.timeout_seconds * 1000)}")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @staticmethod
    def _identity(namespace: str, key: str) -> tuple[str, str]:
        if not isinstance(namespace, str) or not namespace.strip() or len(namespace) > 128:
            raise ValueError("state namespace is invalid")
        if not isinstance(key, str) or not key.strip() or len(key) > 512:
            raise ValueError("state key is invalid")
        return namespace.strip(), key.strip()

    @staticmethod
    def _encode(value: object) -> tuple[str, str]:
        try:
            raw = canonical_bytes(value)
            decoded = _strict_json_loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise TypeError("durable state must be finite canonical JSON") from exc
        encoded = json.dumps(
            decoded,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return encoded, sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _decode(row: sqlite3.Row) -> StoredJSONDocument:
        encoded = str(row["payload_json"])
        digest = sha256(encoded.encode("utf-8")).hexdigest()
        if digest != row["payload_sha256"]:
            raise DurableStateIntegrityError("stored JSON payload digest is invalid")
        try:
            value = _strict_json_loads(encoded)
        except (json.JSONDecodeError, DurableStateIntegrityError) as exc:
            raise DurableStateIntegrityError("stored JSON payload is invalid") from exc
        return StoredJSONDocument(
            namespace=str(row["namespace"]),
            key=str(row["document_key"]),
            version=int(row["version"]),
            payload_sha256=digest,
            value=value,
        )

    def load(self, namespace: str, key: str) -> StoredJSONDocument | None:
        namespace, key = self._identity(namespace, key)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT namespace, document_key, version, payload_sha256, payload_json
                FROM state_documents
                WHERE namespace = ? AND document_key = ?
                """,
                (namespace, key),
            ).fetchone()
        return None if row is None else self._decode(row)

    def create(self, namespace: str, key: str, value: object) -> StoredJSONDocument:
        namespace, key = self._identity(namespace, key)
        encoded, digest = self._encode(value)
        updated = datetime.now(UTC).isoformat()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO state_documents(
                        namespace, document_key, version, payload_sha256,
                        payload_json, updated_at_utc
                    ) VALUES (?, ?, 1, ?, ?, ?)
                    """,
                    (namespace, key, digest, encoded, updated),
                )
                connection.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            raise DurableStateConflict("state document already exists") from exc
        except sqlite3.Error as exc:
            raise DurableStateError("SQLite state create failed") from exc
        return StoredJSONDocument(namespace, key, 1, digest, _strict_json_loads(encoded))

    def compare_and_swap(
        self,
        namespace: str,
        key: str,
        *,
        expected_version: int,
        expected_sha256: str,
        value: object,
    ) -> StoredJSONDocument:
        namespace, key = self._identity(namespace, key)
        if expected_version <= 0:
            raise ValueError("expected state version must be positive")
        if len(expected_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in expected_sha256
        ):
            raise ValueError("expected state SHA-256 is invalid")
        encoded, digest = self._encode(value)
        updated = datetime.now(UTC).isoformat()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    UPDATE state_documents
                    SET version = version + 1,
                        payload_sha256 = ?,
                        payload_json = ?,
                        updated_at_utc = ?
                    WHERE namespace = ? AND document_key = ?
                      AND version = ? AND payload_sha256 = ?
                    """,
                    (
                        digest,
                        encoded,
                        updated,
                        namespace,
                        key,
                        expected_version,
                        expected_sha256,
                    ),
                )
                if cursor.rowcount != 1:
                    connection.execute("ROLLBACK")
                    raise DurableStateConflict("state document changed concurrently")
                connection.execute("COMMIT")
        except DurableStateConflict:
            raise
        except sqlite3.Error as exc:
            raise DurableStateError("SQLite state update failed") from exc
        return StoredJSONDocument(
            namespace,
            key,
            expected_version + 1,
            digest,
            _strict_json_loads(encoded),
        )

    def integrity_check(self) -> bool:
        try:
            with self._connect() as connection:
                result = connection.execute("PRAGMA integrity_check").fetchone()
                if result is None or result[0] != "ok":
                    return False
                rows = connection.execute(
                    """
                    SELECT namespace, document_key, version, payload_sha256, payload_json
                    FROM state_documents
                    """
                ).fetchall()
            for row in rows:
                self._decode(row)
            return True
        except (sqlite3.Error, DurableStateIntegrityError):
            return False


class JSONResultCodec:
    """Strict JSON codec with an explicit allowlist of Pydantic result types."""

    def __init__(self, model_types: Mapping[str, type[BaseModel]] | None = None) -> None:
        self._model_types = dict(model_types or {})
        if any(not name or not issubclass(model, BaseModel) for name, model in self._model_types.items()):
            raise ValueError("result codec model registry is invalid")

    def encode(self, value: object) -> str:
        if isinstance(value, BaseModel):
            names = [name for name, model in self._model_types.items() if type(value) is model]
            if len(names) != 1:
                raise TypeError("idempotency result model type is not explicitly registered")
            payload = {"kind": "pydantic", "model": names[0], "value": value.model_dump(mode="json")}
        else:
            payload = {"kind": "json", "value": value}
        try:
            return canonical_bytes(payload).decode("utf-8")
        except (TypeError, ValueError) as exc:
            raise TypeError("idempotency result is not finite JSON") from exc

    def decode(self, encoded: str) -> object:
        try:
            payload = _strict_json_loads(encoded)
        except (json.JSONDecodeError, DurableStateIntegrityError) as exc:
            raise DurableStateIntegrityError("idempotency result JSON is invalid") from exc
        if not isinstance(payload, dict) or set(payload) not in (
            {"kind", "value"},
            {"kind", "model", "value"},
        ):
            raise DurableStateIntegrityError("idempotency result shape is invalid")
        if payload["kind"] == "json" and set(payload) == {"kind", "value"}:
            return payload["value"]
        if payload["kind"] != "pydantic" or set(payload) != {"kind", "model", "value"}:
            raise DurableStateIntegrityError("idempotency result type is invalid")
        model_name = payload["model"]
        if not isinstance(model_name, str):
            raise DurableStateIntegrityError("idempotency result model name is invalid")
        model = self._model_types.get(model_name)
        if model is None:
            raise DurableStateIntegrityError("idempotency result model is not allowed")
        try:
            return model.model_validate(payload["value"])
        except ValueError as exc:
            raise DurableStateIntegrityError("idempotency result model is invalid") from exc


class SQLiteIdempotencyLedger:
    """Crash-resumable single-host idempotency ledger.

    A stale PENDING lease may be reclaimed. External provider calls must still
    carry their provider-side idempotency token because a process can crash after
    the side effect but before the local COMPLETED transaction commits.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        codec: JSONResultCodec | None = None,
        timeout_seconds: float = 30.0,
        lease_seconds: float = 300.0,
        poll_seconds: float = 0.05,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if timeout_seconds <= 0 or lease_seconds <= 0 or poll_seconds <= 0:
            raise ValueError("SQLite idempotency timing values must be positive")
        requested = Path(path)
        if requested.exists() and requested.is_symlink():
            raise DurableStateError("symlinked SQLite idempotency database is forbidden")
        requested.parent.mkdir(parents=True, exist_ok=True)
        self.path = requested.resolve()
        self.codec = codec or JSONResultCodec()
        self.timeout_seconds = timeout_seconds
        self.lease_seconds = lease_seconds
        self.poll_seconds = poll_seconds
        self.clock = clock
        self._active = threading.local()
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency_operations (
                    scope TEXT NOT NULL,
                    operation_key TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('PENDING', 'COMPLETED')),
                    owner_token TEXT,
                    lease_expires_epoch REAL,
                    result_json TEXT,
                    result_sha256 TEXT,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY(scope, operation_key),
                    CHECK(
                        (status = 'PENDING' AND owner_token IS NOT NULL
                          AND lease_expires_epoch IS NOT NULL
                          AND result_json IS NULL AND result_sha256 IS NULL)
                        OR
                        (status = 'COMPLETED' AND owner_token IS NULL
                          AND lease_expires_epoch IS NULL
                          AND result_json IS NOT NULL AND result_sha256 IS NOT NULL)
                    )
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=self.timeout_seconds,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout={int(self.timeout_seconds * 1000)}")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @staticmethod
    def _validate(scope: str, key: str, fingerprint: str) -> tuple[str, str, str]:
        if not scope or not key or not fingerprint:
            raise ValueError("idempotency scope, key, and fingerprint are required")
        if len(scope) > 512 or len(key) > 512 or len(fingerprint) > 256:
            raise ValueError("idempotency identity is too long")
        return scope, key, fingerprint

    def _active_identities(self) -> set[tuple[str, str]]:
        active = getattr(self._active, "identities", None)
        if active is None:
            active = set()
            self._active.identities = active
        return active

    def _claim(self, scope: str, key: str, fingerprint: str, owner: str) -> object | None:
        now = self.clock()
        updated = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT fingerprint, status, owner_token, lease_expires_epoch,
                       result_json, result_sha256
                FROM idempotency_operations
                WHERE scope = ? AND operation_key = ?
                """,
                (scope, key),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO idempotency_operations(
                        scope, operation_key, fingerprint, status, owner_token,
                        lease_expires_epoch, result_json, result_sha256, updated_at_utc
                    ) VALUES (?, ?, ?, 'PENDING', ?, ?, NULL, NULL, ?)
                    """,
                    (scope, key, fingerprint, owner, now + self.lease_seconds, updated),
                )
                connection.execute("COMMIT")
                return _CLAIMED
            if row["fingerprint"] != fingerprint:
                connection.execute("ROLLBACK")
                raise IdempotencyConflict(
                    "idempotency key was reused with a different request fingerprint"
                )
            if row["status"] == "COMPLETED":
                encoded = str(row["result_json"])
                if sha256(encoded.encode("utf-8")).hexdigest() != row["result_sha256"]:
                    connection.execute("ROLLBACK")
                    raise DurableStateIntegrityError("idempotency result digest is invalid")
                connection.execute("COMMIT")
                return _CompletedResult(self.codec.decode(encoded))
            if float(row["lease_expires_epoch"]) <= now:
                connection.execute(
                    """
                    UPDATE idempotency_operations
                    SET owner_token = ?, lease_expires_epoch = ?, updated_at_utc = ?
                    WHERE scope = ? AND operation_key = ? AND status = 'PENDING'
                    """,
                    (owner, now + self.lease_seconds, updated, scope, key),
                )
                connection.execute("COMMIT")
                return _CLAIMED
            connection.execute("COMMIT")
            return None

    def execute(
        self,
        *,
        scope: str,
        key: str,
        fingerprint: str,
        operation: Callable[[], object],
    ) -> object:
        scope, key, fingerprint = self._validate(scope, key, fingerprint)
        identity = (scope, key)
        active = self._active_identities()
        if identity in active:
            raise IdempotencyReentry("operation recursively reused its own pending key")
        owner = uuid.uuid4().hex

        while True:
            claimed = self._claim(scope, key, fingerprint, owner)
            if claimed is _CLAIMED:
                break
            if isinstance(claimed, _CompletedResult):
                return claimed.value
            time.sleep(self.poll_seconds)

        active.add(identity)
        try:
            result = operation()
            encoded = self.codec.encode(result)
            digest = sha256(encoded.encode("utf-8")).hexdigest()
            updated = datetime.now(UTC).isoformat()
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    UPDATE idempotency_operations
                    SET status = 'COMPLETED', owner_token = NULL,
                        lease_expires_epoch = NULL, result_json = ?,
                        result_sha256 = ?, updated_at_utc = ?
                    WHERE scope = ? AND operation_key = ? AND fingerprint = ?
                      AND status = 'PENDING' AND owner_token = ?
                    """,
                    (encoded, digest, updated, scope, key, fingerprint, owner),
                )
                if cursor.rowcount != 1:
                    connection.execute("ROLLBACK")
                    raise DurableStateConflict("idempotency lease was lost before completion")
                connection.execute("COMMIT")
            return self.codec.decode(encoded)
        except BaseException:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    DELETE FROM idempotency_operations
                    WHERE scope = ? AND operation_key = ?
                      AND status = 'PENDING' AND owner_token = ?
                    """,
                    (scope, key, owner),
                )
                connection.execute("COMMIT")
            raise
        finally:
            active.discard(identity)

    def completed_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM idempotency_operations WHERE status = 'COMPLETED'"
            ).fetchone()
        return int(row[0])

    def integrity_check(self) -> bool:
        try:
            with self._connect() as connection:
                result = connection.execute("PRAGMA integrity_check").fetchone()
                if result is None or result[0] != "ok":
                    return False
                rows = connection.execute(
                    """
                    SELECT result_json, result_sha256
                    FROM idempotency_operations
                    WHERE status = 'COMPLETED'
                    """
                ).fetchall()
            for row in rows:
                encoded = str(row["result_json"])
                if sha256(encoded.encode("utf-8")).hexdigest() != row["result_sha256"]:
                    return False
                self.codec.decode(encoded)
            return True
        except (sqlite3.Error, DurableStateError):
            return False


_CLAIMED = object()

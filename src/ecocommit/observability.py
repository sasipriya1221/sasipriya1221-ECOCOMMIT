from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, Protocol, TextIO


_CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_METRIC_NAME = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Correlation:
    correlation_id: str
    caller_supplied: bool


def resolve_correlation_id(candidate: str | None) -> Correlation:
    if candidate is not None and _CORRELATION_ID.fullmatch(candidate):
        return Correlation(candidate, True)
    return Correlation(uuid.uuid4().hex, False)


def _labels(labels: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    if not labels:
        return ()
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in labels.items()):
        raise TypeError("metric labels must be strings")
    return tuple(sorted(labels.items()))


def _validate_metric_name(name: str) -> None:
    if not _METRIC_NAME.fullmatch(name):
        raise ValueError(f"invalid metric name: {name!r}")


class MetricsRegistry:
    """Small in-process metric registry with deterministic JSON snapshots."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._histograms: dict[
            tuple[str, tuple[tuple[str, str], ...]], dict[str, float]
        ] = {}

    def increment(
        self,
        name: str,
        value: float = 1.0,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        _validate_metric_name(name)
        if value < 0:
            raise ValueError("counter increments cannot be negative")
        key = (name, _labels(labels))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + float(value)

    def set_gauge(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        _validate_metric_name(name)
        key = (name, _labels(labels))
        with self._lock:
            self._gauges[key] = float(value)

    def observe(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        _validate_metric_name(name)
        if value < 0:
            raise ValueError("observations cannot be negative")
        key = (name, _labels(labels))
        with self._lock:
            summary = self._histograms.setdefault(
                key,
                {"count": 0.0, "sum": 0.0, "min": float(value), "max": float(value)},
            )
            summary["count"] += 1.0
            summary["sum"] += float(value)
            summary["min"] = min(summary["min"], float(value))
            summary["max"] = max(summary["max"], float(value))

    @staticmethod
    def _row(
        key: tuple[str, tuple[tuple[str, str], ...]],
        value: float | dict[str, float],
    ) -> dict[str, object]:
        name, labels = key
        return {"name": name, "labels": dict(labels), "value": value}

    def snapshot(self) -> dict[str, list[dict[str, object]]]:
        with self._lock:
            return {
                "counters": [
                    self._row(key, value)
                    for key, value in sorted(self._counters.items())
                ],
                "gauges": [
                    self._row(key, value)
                    for key, value in sorted(self._gauges.items())
                ],
                "histograms": [
                    self._row(key, dict(value))
                    for key, value in sorted(self._histograms.items())
                ],
            }


class EventSink(Protocol):
    def __call__(self, event: Mapping[str, object]) -> None: ...


class InMemoryEventSink:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: list[dict[str, object]] = []

    def __call__(self, event: Mapping[str, object]) -> None:
        normalized = json.loads(json.dumps(event, allow_nan=False))
        with self._lock:
            self._events.append(normalized)

    @property
    def events(self) -> tuple[dict[str, object], ...]:
        with self._lock:
            return tuple(dict(event) for event in self._events)


class JsonLineEventSink:
    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._lock = threading.RLock()

    def __call__(self, event: Mapping[str, object]) -> None:
        encoded = json.dumps(
            event,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        with self._lock:
            self._stream.write(encoded + "\n")
            self._stream.flush()


class StructuredLogger:
    RESERVED_FIELDS = {"timestamp", "level", "event", "correlation_id"}

    def __init__(
        self,
        sink: EventSink | None = None,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._sink = sink or (lambda event: None)
        self._clock = clock

    def emit(
        self,
        level: str,
        event: str,
        correlation_id: str,
        **fields: object,
    ) -> dict[str, object]:
        overlap = self.RESERVED_FIELDS.intersection(fields)
        if overlap:
            raise ValueError(f"reserved structured-log fields: {sorted(overlap)}")
        record = {
            "timestamp": self._clock().astimezone(timezone.utc).isoformat(),
            "level": level.upper(),
            "event": event,
            "correlation_id": correlation_id,
            **fields,
        }
        try:
            normalized = json.loads(json.dumps(record, allow_nan=False))
        except (TypeError, ValueError) as exc:
            raise TypeError("structured event fields must be finite JSON data") from exc
        self._sink(normalized)
        return normalized

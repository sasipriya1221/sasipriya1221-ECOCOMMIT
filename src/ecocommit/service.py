from __future__ import annotations

import json
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Callable, Mapping

from .audit import AppendOnlyAuditLog, AuditIntegrityError
from .checkpoint_status import SafetyStatus
from .observability import MetricsRegistry, StructuredLogger, resolve_correlation_id


_SENSITIVE_KEY_PARTS = (
    "api_key",
    "authorization",
    "card",
    "credential",
    "cvv",
    "password",
    "secret",
    "token",
)
_UNTRUSTED_AUTHORITY_CLAIMS = {
    "accepted",
    "ai_approved",
    "ai_validated",
    "approval",
    "authorized",
    "checkpoint_a_passed",
    "money_movement_enabled",
    "policy_passed",
    "ready",
}


@dataclass(frozen=True)
class ServiceReply:
    status_code: int
    body: Mapping[str, object]


def _redact(value: object, *, key: str | None = None) -> object:
    normalized_key = (key or "").lower()
    if any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        if not all(isinstance(child_key, str) for child_key in value):
            raise TypeError("request object keys must be strings")
        return {
            child_key: _redact(child_value, key=child_key)
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    return value


def _request_summary(payload: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise TypeError("request must be a JSON object")
    if not all(isinstance(key, str) for key in payload):
        raise TypeError("request object keys must be strings")
    redacted = _redact(payload)
    try:
        encoded = json.dumps(
            redacted,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypeError("request must contain finite JSON data") from exc
    lowered = {key.lower() for key in payload}
    return {
        "request_sha256": sha256(encoded).hexdigest(),
        "request_keys": sorted(payload),
        "ignored_untrusted_authority_claims": sorted(
            lowered.intersection(_UNTRUSTED_AUTHORITY_CLAIMS)
        ),
        "sensitive_values_redacted_before_hashing": True,
    }


class CheckpointDService:
    """Safe orchestration facade for status, simulation, and denied commit attempts.

    This scaffold has no execution adapter. It treats all request fields as
    untrusted—including fields claiming validation or authorization—and cannot
    call a payment provider or move money.
    """

    def __init__(
        self,
        status: SafetyStatus | Callable[[], SafetyStatus],
        audit_log: AppendOnlyAuditLog,
        *,
        metrics: MetricsRegistry | None = None,
        logger: StructuredLogger | None = None,
        monotonic: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._status_source = status if callable(status) else lambda: status
        self.audit_log = audit_log
        self.metrics = metrics or MetricsRegistry()
        self.logger = logger or StructuredLogger()
        self._monotonic = monotonic

    def _status(self) -> SafetyStatus:
        status = self._status_source()
        if not isinstance(status, SafetyStatus):
            raise TypeError("status source must return SafetyStatus")
        return status

    @staticmethod
    def _service_snapshot(status: SafetyStatus) -> dict[str, object]:
        snapshot = status.snapshot()
        prerequisites_ready = bool(snapshot["irreversible_commit_ready"])
        blockers = list(snapshot["blockers"])
        blockers.append("EXECUTION_ADAPTER_NOT_IMPLEMENTED")
        return {
            **snapshot,
            "gate_and_provider_prerequisites_ready": prerequisites_ready,
            "service_execution_adapter_configured": False,
            "irreversible_commit_ready": False,
            "blockers": blockers,
        }

    def _finish(
        self,
        *,
        route: str,
        outcome: str,
        started: float,
        correlation_id: str,
        status_code: int,
    ) -> None:
        elapsed = max(0.0, self._monotonic() - started)
        labels = {"route": route, "outcome": outcome}
        self.metrics.increment("ecocommit_api_requests_total", labels=labels)
        self.metrics.observe("ecocommit_api_request_duration_seconds", elapsed, labels=labels)
        self.logger.emit(
            "INFO",
            "api.request.completed",
            correlation_id,
            route=route,
            outcome=outcome,
            status_code=status_code,
            duration_seconds=elapsed,
        )

    def health(self, correlation_id: str | None = None) -> ServiceReply:
        started = self._monotonic()
        correlation = resolve_correlation_id(correlation_id)
        status = self._status()
        snapshot = self._service_snapshot(status)
        body = {
            "correlation_id": correlation.correlation_id,
            "health": "ALIVE",
            "health_scope": "PROCESS_LIVENESS_ONLY",
            "does_not_imply_checkpoint_acceptance": True,
            "checkpoint_gates": snapshot["checkpoint_gates"],
            "irreversible_commit_ready": False,
            "service_execution_adapter_configured": False,
            "safe_to_move_real_money": False,
        }
        self._finish(
            route="health",
            outcome="alive",
            started=started,
            correlation_id=correlation.correlation_id,
            status_code=200,
        )
        return ServiceReply(200, body)

    def readiness(self, correlation_id: str | None = None) -> ServiceReply:
        started = self._monotonic()
        correlation = resolve_correlation_id(correlation_id)
        status = self._status()
        snapshot = self._service_snapshot(status)
        ready = False
        status_code = 200 if ready else 503
        body = {
            "correlation_id": correlation.correlation_id,
            "ready": ready,
            "readiness_scope": "IRREVERSIBLE_COMMIT_PATH",
            "does_not_imply_checkpoint_acceptance": True,
            **snapshot,
        }
        self._finish(
            route="readiness",
            outcome="ready" if ready else "blocked",
            started=started,
            correlation_id=correlation.correlation_id,
            status_code=status_code,
        )
        return ServiceReply(status_code, body)

    def status(self, correlation_id: str | None = None) -> ServiceReply:
        started = self._monotonic()
        correlation = resolve_correlation_id(correlation_id)
        body = {
            "correlation_id": correlation.correlation_id,
            **self._service_snapshot(self._status()),
        }
        self._finish(
            route="status",
            outcome="reported",
            started=started,
            correlation_id=correlation.correlation_id,
            status_code=200,
        )
        return ServiceReply(200, body)

    def metrics_snapshot(self, correlation_id: str | None = None) -> ServiceReply:
        started = self._monotonic()
        correlation = resolve_correlation_id(correlation_id)
        body = {
            "correlation_id": correlation.correlation_id,
            "metrics": self.metrics.snapshot(),
            "safe_to_move_real_money": False,
        }
        self._finish(
            route="metrics",
            outcome="reported",
            started=started,
            correlation_id=correlation.correlation_id,
            status_code=200,
        )
        return ServiceReply(200, body)

    def simulate(
        self,
        payload: Mapping[str, object],
        correlation_id: str | None = None,
    ) -> ServiceReply:
        started = self._monotonic()
        correlation = resolve_correlation_id(correlation_id)
        try:
            summary = _request_summary(payload)
            self.audit_log.append(
                "simulation.requested",
                correlation.correlation_id,
                summary,
            )
        except (AuditIntegrityError, OSError):
            return self._audit_failure(
                route="simulate",
                started=started,
                correlation_id=correlation.correlation_id,
            )
        except (TypeError, ValueError) as exc:
            body = {
                "correlation_id": correlation.correlation_id,
                "outcome": "REJECTED_INVALID_REQUEST",
                "reason": str(exc),
                "simulated": True,
                "money_moved": False,
                "provider_called": False,
            }
            self._finish(
                route="simulate",
                outcome="invalid",
                started=started,
                correlation_id=correlation.correlation_id,
                status_code=400,
            )
            return ServiceReply(400, body)

        body = {
            "correlation_id": correlation.correlation_id,
            "outcome": "SIMULATED_ONLY",
            "simulated": True,
            "simulation_label": "NO REAL PROVIDER CALL; NO MONEY MOVEMENT",
            "authority_evaluated": False,
            "money_moved": False,
            "provider_called": False,
            "ignored_untrusted_authority_claims": summary[
                "ignored_untrusted_authority_claims"
            ],
            "checkpoint_snapshot": self._service_snapshot(self._status()),
        }
        try:
            self.audit_log.append(
                "simulation.completed",
                correlation.correlation_id,
                {
                    "outcome": "SIMULATED_ONLY",
                    "authority_evaluated": False,
                    "money_moved": False,
                    "provider_called": False,
                },
            )
        except (AuditIntegrityError, OSError):
            return self._audit_failure(
                route="simulate",
                started=started,
                correlation_id=correlation.correlation_id,
            )
        self._finish(
            route="simulate",
            outcome="simulated_only",
            started=started,
            correlation_id=correlation.correlation_id,
            status_code=200,
        )
        return ServiceReply(200, body)

    def request_commit(
        self,
        payload: Mapping[str, object],
        correlation_id: str | None = None,
    ) -> ServiceReply:
        started = self._monotonic()
        correlation = resolve_correlation_id(correlation_id)
        try:
            summary = _request_summary(payload)
            self.audit_log.append(
                "commit.requested",
                correlation.correlation_id,
                summary,
            )
        except (AuditIntegrityError, OSError):
            return self._audit_failure(
                route="commit",
                started=started,
                correlation_id=correlation.correlation_id,
            )
        except (TypeError, ValueError) as exc:
            body = {
                "correlation_id": correlation.correlation_id,
                "outcome": "DENIED",
                "reason": "INVALID_REQUEST",
                "detail": str(exc),
                "default_deny": True,
                "money_moved": False,
                "provider_called": False,
            }
            self._finish(
                route="commit",
                outcome="invalid_denied",
                started=started,
                correlation_id=correlation.correlation_id,
                status_code=400,
            )
            return ServiceReply(400, body)

        status = self._status()
        checkpoint_snapshot = self._service_snapshot(status)
        blockers = list(checkpoint_snapshot["blockers"])
        reason = blockers[0]
        body = {
            "correlation_id": correlation.correlation_id,
            "outcome": "DENIED",
            "reason": reason,
            "blockers": blockers,
            "default_deny": True,
            "request_fields_are_untrusted": True,
            "ignored_untrusted_authority_claims": summary[
                "ignored_untrusted_authority_claims"
            ],
            "money_moved": False,
            "provider_called": False,
            "checkpoint_snapshot": checkpoint_snapshot,
        }
        try:
            self.audit_log.append(
                "commit.denied",
                correlation.correlation_id,
                {
                    "reason": reason,
                    "blockers": blockers,
                    "money_moved": False,
                    "provider_called": False,
                },
            )
        except (AuditIntegrityError, OSError):
            return self._audit_failure(
                route="commit",
                started=started,
                correlation_id=correlation.correlation_id,
            )
        self.metrics.increment(
            "ecocommit_commit_attempts_total",
            labels={"outcome": "denied", "reason": reason},
        )
        self._finish(
            route="commit",
            outcome="denied",
            started=started,
            correlation_id=correlation.correlation_id,
            status_code=423,
        )
        return ServiceReply(423, body)

    def _audit_failure(
        self,
        *,
        route: str,
        started: float,
        correlation_id: str,
    ) -> ServiceReply:
        body = {
            "correlation_id": correlation_id,
            "outcome": "DENIED",
            "reason": "AUDIT_INTEGRITY_UNAVAILABLE",
            "default_deny": True,
            "money_moved": False,
            "provider_called": False,
        }
        self.metrics.increment(
            "ecocommit_audit_failures_total",
            labels={"route": route},
        )
        self.logger.emit(
            "ERROR",
            "audit.unavailable",
            correlation_id,
            route=route,
            default_deny=True,
        )
        self._finish(
            route=route,
            outcome="audit_failure_denied",
            started=started,
            correlation_id=correlation_id,
            status_code=503,
        )
        return ServiceReply(503, body)

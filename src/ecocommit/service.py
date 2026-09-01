from __future__ import annotations

import json
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Callable, Mapping

from .audit import AppendOnlyAuditLog, AuditIntegrityError
from .checkpoint_d_workflow import (
    CheckpointDSimulatedWorkflow,
    SimulationInputError,
)
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
        simulation_workflow: CheckpointDSimulatedWorkflow | None = None,
        monotonic: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._status_source = status if callable(status) else lambda: status
        self.audit_log = audit_log
        self.metrics = metrics or MetricsRegistry()
        self.logger = logger or StructuredLogger()
        self.simulation_workflow = simulation_workflow or CheckpointDSimulatedWorkflow()
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

        scenario = payload.get("scenario", "HAPPY_PATH")
        if not isinstance(scenario, str):
            return self._simulation_input_failure(
                started=started,
                correlation_id=correlation.correlation_id,
                detail="scenario must be a string",
            )
        try:
            workflow = self.simulation_workflow.run(scenario)
        except SimulationInputError as exc:
            return self._simulation_input_failure(
                started=started,
                correlation_id=correlation.correlation_id,
                detail=str(exc),
            )
        except Exception:
            try:
                self.audit_log.append(
                    "simulation.failed_closed",
                    correlation.correlation_id,
                    {
                        "reason": "SIMULATION_WORKFLOW_FAILURE",
                        "money_moved": False,
                        "real_provider_called": False,
                    },
                )
            except (AuditIntegrityError, OSError):
                return self._audit_failure(
                    route="simulate",
                    started=started,
                    correlation_id=correlation.correlation_id,
                )
            self.logger.emit(
                "ERROR",
                "simulation.workflow.failed_closed",
                correlation.correlation_id,
                scenario=scenario,
                money_moved=False,
                real_provider_called=False,
            )
            self._finish(
                route="simulate",
                outcome="workflow_failure_closed",
                started=started,
                correlation_id=correlation.correlation_id,
                status_code=503,
            )
            return ServiceReply(
                503,
                {
                    "correlation_id": correlation.correlation_id,
                    "outcome": "SIMULATION_FAILED_CLOSED",
                    "reason": "SIMULATION_WORKFLOW_FAILURE",
                    "simulated": True,
                    "money_moved": False,
                    "provider_called": False,
                },
            )

        body = {
            "correlation_id": correlation.correlation_id,
            "outcome": workflow["outcome"],
            "simulated": True,
            "simulation_label": "NO REAL PROVIDER CALL; NO MONEY MOVEMENT",
            "authority_evaluated": False,
            "synthetic_authority_fixture_evaluated": True,
            "authority_scope": "SYNTHETIC_FIXTURE_ONLY",
            "authoritative_checkpoint_evidence_used": False,
            "money_moved": False,
            "provider_called": False,
            "simulation_input_contract": "SCENARIO_SELECTOR_ONLY",
            "ignored_simulation_request_fields": sorted(
                key for key in payload if key != "scenario"
            ),
            "ignored_untrusted_authority_claims": summary[
                "ignored_untrusted_authority_claims"
            ],
            "workflow": workflow,
            "checkpoint_snapshot": self._service_snapshot(self._status()),
        }
        try:
            self.audit_log.append(
                "simulation.completed",
                correlation.correlation_id,
                {
                    "outcome": workflow["outcome"],
                    "scenario": workflow["scenario"],
                    "final_commitment_stage": workflow["final_commitment_stage"],
                    "authority_scope": "SYNTHETIC_FIXTURE_ONLY",
                    "ignored_request_fields": sorted(
                        key for key in payload if key != "scenario"
                    ),
                    "money_moved": False,
                    "real_provider_called": False,
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

    def _simulation_input_failure(
        self,
        *,
        started: float,
        correlation_id: str,
        detail: str,
    ) -> ServiceReply:
        try:
            self.audit_log.append(
                "simulation.rejected",
                correlation_id,
                {
                    "reason": "INVALID_SIMULATION_SCENARIO",
                    "money_moved": False,
                    "real_provider_called": False,
                },
            )
        except (AuditIntegrityError, OSError):
            return self._audit_failure(
                route="simulate",
                started=started,
                correlation_id=correlation_id,
            )
        self._finish(
            route="simulate",
            outcome="invalid_scenario",
            started=started,
            correlation_id=correlation_id,
            status_code=400,
        )
        return ServiceReply(
            400,
            {
                "correlation_id": correlation_id,
                "outcome": "REJECTED_INVALID_REQUEST",
                "reason": "INVALID_SIMULATION_SCENARIO",
                "detail": detail,
                "simulated": True,
                "money_moved": False,
                "provider_called": False,
            },
        )

    def record_boundary_rejection(
        self,
        *,
        correlation_id: str,
        method: str,
        path: str,
        reason: str,
        status_code: int,
    ) -> None:
        """Record a side-effect-free rejection at the HTTP parsing boundary."""

        labels = {"reason": reason, "status_code": str(status_code)}
        try:
            self.metrics.increment("ecocommit_api_boundary_rejections_total", labels=labels)
        except Exception:
            pass
        try:
            self.logger.emit(
                "WARNING",
                "api.request.rejected",
                correlation_id,
                method=method,
                path=path,
                reason=reason,
                status_code=status_code,
                default_deny=True,
            )
        except Exception:
            pass
        try:
            self.audit_log.append(
                "api.request.rejected",
                correlation_id,
                {
                    "method": method,
                    "path": path,
                    "reason": reason,
                    "status_code": status_code,
                    "default_deny": True,
                    "money_moved": False,
                    "provider_called": False,
                },
            )
        except (AuditIntegrityError, OSError):
            try:
                self.metrics.increment(
                    "ecocommit_audit_failures_total",
                    labels={"route": "api_boundary"},
                )
            except Exception:
                pass
            try:
                self.logger.emit(
                    "ERROR",
                    "audit.unavailable",
                    correlation_id,
                    route="api_boundary",
                    default_deny=True,
                )
            except Exception:
                pass

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

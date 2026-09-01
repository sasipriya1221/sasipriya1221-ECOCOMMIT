from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path
from wsgiref.simple_server import make_server

from ecocommit.api import CheckpointDApi, SlidingWindowRateLimiter
from ecocommit.audit import AppendOnlyAuditLog
from ecocommit.commitment import SQLiteCommitmentStateStore
from ecocommit.checkpoint_d_evidence import (
    AuthoritativeEvidenceStatusSource,
    load_authoritative_evidence,
)
from ecocommit.checkpoint_status import CHECKPOINTS, GateReport, GateState, SafetyStatus
from ecocommit.demo_server import CheckpointDLocalDemoApplication
from ecocommit.durable import JSONResultCodec, SQLiteIdempotencyLedger, SQLiteJSONStateStore
from ecocommit.execution import (
    RazorpayPreparedTestExecutionAdapter,
    TestExecutionResult,
    load_prepared_test_operation,
)
from ecocommit.payments import SQLitePaymentStateStore
from ecocommit.razorpay import (
    RazorpayOrderResult,
    RazorpayPaymentResult,
    RazorpayTestCredentials,
    RazorpayTestPaymentAdapter,
    RazorpayWebhookVerifier,
)
from ecocommit.service import CheckpointDService
from ecocommit.webhook import (
    BoundRazorpayWebhookProcessor,
    SQLiteWebhookEvidenceStore,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class PreparedExecutionRuntime:
    __slots__ = ("adapter", "webhook_processor")

    def __init__(
        self,
        adapter: RazorpayPreparedTestExecutionAdapter,
        webhook_processor: BoundRazorpayWebhookProcessor,
    ) -> None:
        self.adapter = adapter
        self.webhook_processor = webhook_processor


def build_application(
    audit_path: str | Path,
    *,
    evidence_root: str | Path | None = None,
    pins_path: str | Path | None = None,
    pins_sha256: str | None = None,
    execution_adapter: RazorpayPreparedTestExecutionAdapter | None = None,
    provider_credentials_verified: bool = False,
    api_bearer_token: str | None = None,
    webhook_processor: BoundRazorpayWebhookProcessor | None = None,
    audit_log: AppendOnlyAuditLog | None = None,
) -> CheckpointDLocalDemoApplication:
    if (execution_adapter is None) != (webhook_processor is None):
        raise ValueError("prepared execution adapter and webhook processor are inseparable")
    evidence_values = (evidence_root, pins_path, pins_sha256)
    if any(value is not None for value in evidence_values) and not all(
        value is not None for value in evidence_values
    ):
        raise ValueError(
            "evidence_root, pins_path, and pins_sha256 must be supplied together"
        )
    if all(value is not None for value in evidence_values):
        status = AuthoritativeEvidenceStatusSource(
            evidence_root,
            pins_path,
            pins_sha256,
            provider_credentials_verified=provider_credentials_verified,
            provider_calls_enabled=execution_adapter is not None,
        )
    else:
        if execution_adapter is not None or provider_credentials_verified:
            raise ValueError("prepared execution requires pinned authoritative evidence")
        # The default demo intentionally loads no authoritative checkpoint
        # evidence. Every gate is blocked regardless of caller claims.
        status = SafetyStatus(
            gates={
                checkpoint: GateReport(
                    checkpoint,
                    GateState.BLOCKED,
                    detail="LOCAL_DEMO_HAS_NO_AUTHORITATIVE_GATE_EVIDENCE",
                )
                for checkpoint in CHECKPOINTS
            }
        )
    if execution_adapter is not None and api_bearer_token is None:
        raise ValueError("prepared execution requires an environment-only API bearer token")
    if execution_adapter is not None and webhook_processor is None:
        raise ValueError("prepared execution requires a signed webhook processor")
    service = CheckpointDService(
        status,
        audit_log or AppendOnlyAuditLog(audit_path),
        execution_adapter=execution_adapter,
    )
    return CheckpointDLocalDemoApplication(
        CheckpointDApi(
            service,
            commit_bearer_token=api_bearer_token,
            commit_rate_limiter=(
                SlidingWindowRateLimiter(max_attempts=5, window_seconds=60)
                if execution_adapter is not None
                else None
            ),
            webhook_processor=webhook_processor,
        ),
        REPOSITORY_ROOT / "ui",
    )


def serve(
    port: int,
    audit_path: str | Path,
    *,
    evidence_root: str | Path | None = None,
    pins_path: str | Path | None = None,
    pins_sha256: str | None = None,
    prepared_operation_path: str | Path | None = None,
    prepared_operation_sha256: str | None = None,
    state_db_path: str | Path | None = None,
) -> None:
    audit_log = AppendOnlyAuditLog(audit_path)
    execution_values = (
        prepared_operation_path,
        prepared_operation_sha256,
        state_db_path,
    )
    evidence_values = (evidence_root, pins_path, pins_sha256)
    if any(value is not None for value in execution_values) and not all(
        value is not None for value in execution_values
    ):
        raise ValueError("prepared operation path, SHA-256, and state DB are inseparable")
    if all(value is not None for value in execution_values) and not all(
        value is not None for value in evidence_values
    ):
        raise ValueError("prepared execution requires pinned A/B/C evidence")
    execution_adapter = None
    webhook_processor = None
    provider_credentials_verified = False
    api_bearer_token = None
    if all(value is not None for value in execution_values):
        # Validate the complete authoritative prerequisite chain before any
        # provider preflight, even though the status source will also reload it
        # on every request to detect later tampering.
        load_authoritative_evidence(
            evidence_root,
            pins_path,
            expected_pins_file_sha256=pins_sha256,
        )
        api_bearer_token = os.environ.get("ECOCOMMIT_D_API_TOKEN")
        if api_bearer_token is None:
            raise ValueError(
                "ECOCOMMIT_D_API_TOKEN must be supplied through the environment"
            )
        if len(api_bearer_token.encode("utf-8")) < 32 or any(
            character.isspace() for character in api_bearer_token
        ):
            raise ValueError(
                "ECOCOMMIT_D_API_TOKEN must contain at least 32 non-space bytes"
            )
        runtime = build_prepared_execution_runtime(
            prepared_operation_path,
            prepared_operation_sha256,
            state_db_path,
            audit_log=audit_log,
        )
        execution_adapter = runtime.adapter
        webhook_processor = runtime.webhook_processor
        provider_credentials_verified = True
    application = build_application(
        audit_path,
        evidence_root=evidence_root,
        pins_path=pins_path,
        pins_sha256=pins_sha256,
        execution_adapter=execution_adapter,
        provider_credentials_verified=provider_credentials_verified,
        api_bearer_token=api_bearer_token,
        webhook_processor=webhook_processor,
        audit_log=audit_log,
    )
    with make_server("127.0.0.1", port, application) as server:
        print(
            f"Checkpoint D local simulation console: http://127.0.0.1:{port}/\n"
            "Status evidence is accepted only when explicitly pinned. "
            + (
                "A startup-pinned Razorpay Test operation is enabled; real money remains disabled."
                if execution_adapter is not None
                else "The execution adapter is disabled and no provider is called."
            )
        )
        server.serve_forever()


def build_prepared_execution_runtime(
    prepared_operation_path: str | Path,
    prepared_operation_sha256: str,
    state_db_path: str | Path,
    *,
    audit_log: AppendOnlyAuditLog,
) -> PreparedExecutionRuntime:
    operation = load_prepared_test_operation(
        prepared_operation_path,
        expected_file_sha256=prepared_operation_sha256,
    )
    credentials = RazorpayTestCredentials.from_environment()
    if operation.handoff.public_key_id != credentials.key_id:
        raise ValueError("prepared operation belongs to a different Razorpay Test key")
    signing_secret = os.environ.get("ECOCOMMIT_D_SIGNING_SECRET", "").encode("utf-8")
    if len(signing_secret) < 32:
        raise ValueError(
            "ECOCOMMIT_D_SIGNING_SECRET must contain at least 32 bytes and remain environment-only"
        )
    # Validate every remaining secret/configuration dependency before making
    # the read-only provider credential preflight.
    webhook_verifier = RazorpayWebhookVerifier.from_environment()

    shared_state = SQLiteJSONStateStore(state_db_path)
    ledger = SQLiteIdempotencyLedger(
        state_db_path,
        codec=JSONResultCodec({
            "RazorpayOrderResult": RazorpayOrderResult,
            "RazorpayPaymentResult": RazorpayPaymentResult,
            "TestExecutionResult": TestExecutionResult,
        }),
    )
    payment_adapter = RazorpayTestPaymentAdapter(
        credentials=credentials,
        idempotency=ledger,
        state_store=SQLitePaymentStateStore(shared_state),
    )
    correlation_id = f"startup-preflight-{operation.operation_sha256[:16]}"
    audit_log.append(
        "provider.credentials.preflight.started",
        correlation_id,
        {
            "provider_mode": "RAZORPAY_TEST_MODE",
            "read_only": True,
            "provider_called": False,
            "real_money_moved": False,
        },
    )
    try:
        payment_adapter.verify_credentials()
    except Exception:
        audit_log.append(
            "provider.credentials.preflight.failed",
            correlation_id,
            {
                "provider_mode": "RAZORPAY_TEST_MODE",
                "credentials_verified": False,
                "response_body_retained": False,
                "provider_call_status": "STARTED_OR_UNKNOWN",
                "real_money_moved": False,
            },
        )
        raise
    audit_log.append(
        "provider.credentials.preflight.completed",
        correlation_id,
        {
            "provider_mode": "RAZORPAY_TEST_MODE",
            "credentials_verified": True,
            "response_body_retained": False,
            "provider_called": True,
            "real_money_moved": False,
        },
    )
    execution_adapter = RazorpayPreparedTestExecutionAdapter(
        {operation.operation_id: operation},
        payment_adapter=payment_adapter,
        signing_secret=signing_secret,
        commitment_store=SQLiteCommitmentStateStore(shared_state),
        idempotency=ledger,
    )
    webhook_processor = BoundRazorpayWebhookProcessor(
        operation,
        verifier=webhook_verifier,
        store=SQLiteWebhookEvidenceStore(shared_state),
        audit_log=audit_log,
    )
    return PreparedExecutionRuntime(
        adapter=execution_adapter,
        webhook_processor=webhook_processor,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Serve the loopback-only Checkpoint D simulation console."
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--audit-path", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--pins", type=Path)
    parser.add_argument("--pins-sha256")
    parser.add_argument("--prepared-operation", type=Path)
    parser.add_argument("--prepared-operation-sha256")
    parser.add_argument("--state-db", type=Path)
    args = parser.parse_args()
    if not (1 <= args.port <= 65_535):
        parser.error("port must be between 1 and 65535")

    evidence_values = (args.evidence_root, args.pins, args.pins_sha256)
    if any(value is not None for value in evidence_values) and not all(
        value is not None for value in evidence_values
    ):
        parser.error("--evidence-root, --pins, and --pins-sha256 are required together")

    execution_values = (
        args.prepared_operation,
        args.prepared_operation_sha256,
        args.state_db,
    )
    if any(value is not None for value in execution_values) and not all(
        value is not None for value in execution_values
    ):
        parser.error(
            "--prepared-operation, --prepared-operation-sha256, and --state-db are required together"
        )
    if all(value is not None for value in execution_values):
        if not all(value is not None for value in evidence_values):
            parser.error("prepared execution requires pinned A/B/C evidence")
        if args.audit_path is None:
            parser.error("prepared execution requires a persistent --audit-path")

    if args.audit_path is not None:
        serve(
            args.port,
            args.audit_path,
            evidence_root=args.evidence_root,
            pins_path=args.pins,
            pins_sha256=args.pins_sha256,
            prepared_operation_path=args.prepared_operation,
            prepared_operation_sha256=args.prepared_operation_sha256,
            state_db_path=args.state_db,
        )
        return 0
    with tempfile.TemporaryDirectory(prefix="ecocommit-d-demo-") as directory:
        serve(
            args.port,
            Path(directory) / "audit.ndjson",
            evidence_root=args.evidence_root,
            pins_path=args.pins,
            pins_sha256=args.pins_sha256,
            prepared_operation_path=args.prepared_operation,
            prepared_operation_sha256=args.prepared_operation_sha256,
            state_db_path=args.state_db,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

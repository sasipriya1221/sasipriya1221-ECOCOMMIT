from __future__ import annotations

import argparse
from pathlib import Path
from wsgiref.simple_server import make_server

from ecocommit.api import CheckpointDApi
from ecocommit.audit import AppendOnlyAuditLog
from ecocommit.checkpoint_status import SafetyStatus
from ecocommit.execution import load_prepared_test_operation
from ecocommit.razorpay import RazorpayWebhookVerifier
from ecocommit.service import CheckpointDService
from ecocommit.webhook import (
    BoundRazorpayWebhookProcessor,
    SQLiteWebhookEvidenceStore,
)


def build_application(
    prepared_operation_path: str | Path,
    prepared_operation_sha256: str,
    state_db_path: str | Path,
    audit_path: str | Path,
    *,
    verifier: RazorpayWebhookVerifier | None = None,
) -> CheckpointDApi:
    operation = load_prepared_test_operation(
        prepared_operation_path,
        expected_file_sha256=prepared_operation_sha256,
    )
    audit_log = AppendOnlyAuditLog(audit_path)
    processor = BoundRazorpayWebhookProcessor(
        operation,
        verifier=verifier or RazorpayWebhookVerifier.from_environment(),
        store=SQLiteWebhookEvidenceStore(state_db_path),
        audit_log=audit_log,
    )
    return CheckpointDApi(
        CheckpointDService(SafetyStatus(), audit_log),
        webhook_processor=processor,
    )


def serve(
    port: int,
    prepared_operation_path: str | Path,
    prepared_operation_sha256: str,
    state_db_path: str | Path,
    audit_path: str | Path,
) -> None:
    application = build_application(
        prepared_operation_path,
        prepared_operation_sha256,
        state_db_path,
        audit_path,
    )
    with make_server("127.0.0.1", port, application) as server:
        print(
            f"ECOCOMMIT B8 signed webhook receiver: http://127.0.0.1:{port}/v1/razorpay/webhook\n"
            "Loopback development server only; public HTTPS routing and Test Dashboard configuration are external."
        )
        server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Receive bound Razorpay Test capture/refund webhooks after the "
            "human Checkout and before/during the B8 continuation."
        )
    )
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--prepared-operation", type=Path, required=True)
    parser.add_argument("--prepared-operation-sha256", required=True)
    parser.add_argument("--state-db", type=Path, required=True)
    parser.add_argument("--audit-path", type=Path, required=True)
    args = parser.parse_args()
    if not (1 <= args.port <= 65_535):
        parser.error("port must be between 1 and 65535")
    serve(
        args.port,
        args.prepared_operation,
        args.prepared_operation_sha256,
        args.state_db,
        args.audit_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

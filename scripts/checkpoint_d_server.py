from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from wsgiref.simple_server import make_server

from ecocommit.api import CheckpointDApi
from ecocommit.audit import AppendOnlyAuditLog
from ecocommit.checkpoint_status import CHECKPOINTS, GateReport, GateState, SafetyStatus
from ecocommit.demo_server import CheckpointDLocalDemoApplication
from ecocommit.service import CheckpointDService


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def build_application(audit_path: str | Path) -> CheckpointDLocalDemoApplication:
    # The demo intentionally loads no authoritative checkpoint evidence. Every
    # gate is blocked regardless of repository or caller claims.
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
    service = CheckpointDService(status, AppendOnlyAuditLog(audit_path))
    return CheckpointDLocalDemoApplication(
        CheckpointDApi(service),
        REPOSITORY_ROOT / "ui",
    )


def serve(port: int, audit_path: str | Path) -> None:
    application = build_application(audit_path)
    with make_server("127.0.0.1", port, application) as server:
        print(
            f"Checkpoint D local simulation console: http://127.0.0.1:{port}/\n"
            "SIMULATED_LOCAL only; no real provider call; no checkpoint acceptance."
        )
        server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Serve the loopback-only Checkpoint D simulation console."
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--audit-path", type=Path)
    args = parser.parse_args()
    if not (1 <= args.port <= 65_535):
        parser.error("port must be between 1 and 65535")

    if args.audit_path is not None:
        serve(args.port, args.audit_path)
        return 0
    with tempfile.TemporaryDirectory(prefix="ecocommit-d-demo-") as directory:
        serve(args.port, Path(directory) / "audit.ndjson")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

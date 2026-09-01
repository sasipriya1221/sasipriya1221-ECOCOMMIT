from __future__ import annotations

import argparse
import json
from pathlib import Path

from ecocommit.checkpoint_d_evidence import (
    AuthoritativeEvidenceError,
    load_authoritative_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a trusted, digest-pinned A/B/C[/D] evidence bundle and emit "
            "its fail-closed runtime status. This command never calls a provider."
        )
    )
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--pins", type=Path, required=True)
    parser.add_argument("--pins-sha256", required=True)
    args = parser.parse_args()

    try:
        bundle = load_authoritative_evidence(
            args.evidence_root,
            args.pins,
            expected_pins_file_sha256=args.pins_sha256,
        )
    except AuthoritativeEvidenceError as exc:
        print(json.dumps({"verified": False, "reason": str(exc)}, sort_keys=True))
        return 1

    print(
        json.dumps(
            {
                "verified": True,
                "repository": bundle.pins.repository,
                "integrated_revision": bundle.pins.integrated_revision,
                "file_sha256": dict(bundle.file_sha256),
                "status": bundle.safety_status().snapshot(),
                "provider_called": False,
                "money_moved": False,
            },
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import os
from pathlib import Path

from ecocommit.b8_provenance import create_certificate_key_boundary_reference


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create the non-secret B8 certificate-key boundary reference before "
            "any Razorpay order is created."
        )
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument(
        "--run-attempt", default=os.environ.get("GITHUB_RUN_ATTEMPT", "")
    )
    args = parser.parse_args()

    reference = create_certificate_key_boundary_reference(
        source_revision=args.source_revision,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
    )
    if args.output.exists():
        raise SystemExit("refusing to overwrite existing B8 provenance evidence")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        reference.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        "B8_CERTIFICATE_KEY_REFERENCE "
        f"source_revision={reference.source_revision} "
        "key_material_retained=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

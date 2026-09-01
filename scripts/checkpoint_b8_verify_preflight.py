from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ecocommit.github_actions import (
    GitHubRunVerificationError,
    fetch_razorpay_preflight_run,
    write_preflight_receipt,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that a Razorpay credential-preflight run succeeded for the "
            "expected repository, workflow, and source revision."
        )
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        receipt = fetch_razorpay_preflight_run(
            repository=args.repository,
            run_id=args.run_id,
            expected_sha=args.expected_sha,
            token=os.environ.get("GITHUB_TOKEN", ""),
        )
        write_preflight_receipt(args.output, receipt)
    except GitHubRunVerificationError as exc:
        print(f"B8_PREFLIGHT_VERIFICATION_FAILED code={exc.code}", file=sys.stderr)
        return 2

    print(
        "B8_PREFLIGHT_REFERENCE_VERIFIED "
        f"run_id={receipt['run_id']} receipt_sha256={receipt['receipt_sha256']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ecocommit.razorpay import RazorpayTestCredentials, RazorpayTestPaymentAdapter
from ecocommit.razorpay_checkout import (
    RazorpayCheckoutCallback,
    RazorpayCheckoutHandoff,
    complete_test_lifecycle,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Continue a human-authorized Razorpay Test Checkout through capture and refund."
    )
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--callback", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    credentials = RazorpayTestCredentials.from_environment()
    handoff = RazorpayCheckoutHandoff.model_validate_json(
        args.handoff.read_text(encoding="utf-8")
    )
    callback = RazorpayCheckoutCallback.model_validate_json(
        args.callback.read_text(encoding="utf-8")
    )
    if handoff.public_key_id != credentials.key_id:
        raise SystemExit("Checkout handoff belongs to a different Razorpay Test key")

    result = complete_test_lifecycle(
        handoff,
        callback,
        adapter=RazorpayTestPaymentAdapter(credentials=credentials),
        now=datetime.now(timezone.utc),
    )
    encoded = result.model_dump_json(indent=2) + "\n"
    if credentials.key_id in encoded or credentials.key_secret in encoded:
        raise RuntimeError("refusing to retain B8 lifecycle evidence containing credentials")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")
    print(json.dumps({
        "checkpoint_b8_lifecycle_passed": result.checkpoint_b8_lifecycle_passed,
        "refund_state": result.refund_state,
        "webhook_verified": result.webhook_verified,
    }))
    return 0 if result.checkpoint_b8_lifecycle_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

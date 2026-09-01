from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from ecocommit.commitment import SQLiteCommitmentStateStore
from ecocommit.durable import JSONResultCodec, SQLiteIdempotencyLedger, SQLiteJSONStateStore
from ecocommit.payments import SQLitePaymentStateStore
from ecocommit.razorpay import (
    RazorpayOrderResult,
    RazorpayPaymentResult,
    RazorpayTestCredentials,
    RazorpayTestPaymentAdapter,
)
from ecocommit.razorpay_checkout import (
    RazorpayCheckoutCallback,
    RazorpayCheckoutHandoff,
    complete_test_lifecycle,
)


MAX_INPUT_BYTES = 256 * 1024


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON keys are forbidden")
        result[key] = value
    return result


def _load(path: Path, model: type[BaseModel]):
    if path.is_symlink():
        raise ValueError("symlinked B8 input is forbidden")
    raw = path.resolve().read_bytes()
    if not raw or len(raw) > MAX_INPUT_BYTES:
        raise ValueError("B8 input size is invalid")
    payload = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError("B8 input must contain one JSON object")
    return model.model_validate(payload)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Continue a human-authorized Razorpay Test Checkout through capture and refund."
    )
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--callback", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--state-db",
        type=Path,
        required=True,
        help="SQLite WAL database for idempotency, payment, and commitment state",
    )
    args = parser.parse_args()

    credentials = RazorpayTestCredentials.from_environment()
    handoff = _load(args.handoff, RazorpayCheckoutHandoff)
    callback = _load(args.callback, RazorpayCheckoutCallback)
    if handoff.public_key_id != credentials.key_id:
        raise SystemExit("Checkout handoff belongs to a different Razorpay Test key")
    signing_secret = os.environ.get("ECOCOMMIT_B8_SIGNING_SECRET", "").encode("utf-8")
    if len(signing_secret) < 32:
        raise SystemExit(
            "ECOCOMMIT_B8_SIGNING_SECRET must contain at least 32 bytes and remain environment-only"
        )

    shared_state = SQLiteJSONStateStore(args.state_db)
    idempotency = SQLiteIdempotencyLedger(
        args.state_db,
        codec=JSONResultCodec({
            "RazorpayOrderResult": RazorpayOrderResult,
            "RazorpayPaymentResult": RazorpayPaymentResult,
        }),
    )
    payment_state = SQLitePaymentStateStore(shared_state)
    commitment_state = SQLiteCommitmentStateStore(shared_state)

    result = complete_test_lifecycle(
        handoff,
        callback,
        adapter=RazorpayTestPaymentAdapter(
            credentials=credentials,
            idempotency=idempotency,
            state_store=payment_state,
        ),
        now=datetime.now(timezone.utc),
        signing_secret=signing_secret,
        commitment_store=commitment_state,
    )
    encoded = result.model_dump_json(indent=2) + "\n"
    if credentials.key_id in encoded or credentials.key_secret in encoded:
        raise RuntimeError("refusing to retain B8 lifecycle evidence containing credentials")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open("x", encoding="utf-8", newline="\n") as output:
            output.write(encoded)
    except FileExistsError:
        parser.error("--output already exists; refusing to overwrite lifecycle evidence")
    print(json.dumps({
        "checkpoint_b8_lifecycle_passed": result.checkpoint_b8_lifecycle_passed,
        "refund_state": result.refund_state,
        "webhook_verified": result.webhook_verified,
    }))
    return 0 if result.checkpoint_b8_lifecycle_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

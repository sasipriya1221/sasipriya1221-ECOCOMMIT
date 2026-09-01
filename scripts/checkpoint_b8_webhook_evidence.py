from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from ecocommit.webhook import SQLiteWebhookEvidenceStore


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Export the exact verified payment.captured + refund.processed "
            "Razorpay Test webhook set from durable state."
        )
    )
    parser.add_argument("--state-db", type=Path, required=True)
    parser.add_argument("--transaction-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    verified = SQLiteWebhookEvidenceStore(args.state_db).verified_set(
        args.transaction_id
    )
    raw = (
        json.dumps(
            verified.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open("xb") as output:
            output.write(raw)
    except FileExistsError:
        parser.error("--output already exists; refusing to overwrite webhook evidence")
    print(json.dumps({
        "verified": True,
        "webhook_set_sha256": verified.set_sha256,
        "evidence_file_sha256": sha256(raw).hexdigest(),
        "event_count": 2,
        "raw_webhook_bodies_retained": False,
        "real_money_moved": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

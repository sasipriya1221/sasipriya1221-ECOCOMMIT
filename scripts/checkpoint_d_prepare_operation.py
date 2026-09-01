from __future__ import annotations

import argparse
import json
import os
import secrets
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel

from ecocommit.execution import PreparedRazorpayTestOperation
from ecocommit.razorpay_checkout import RazorpayCheckoutCallback, RazorpayCheckoutHandoff


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
        raise ValueError("symlinked operation input is forbidden")
    raw = path.resolve().read_bytes()
    if not raw or len(raw) > MAX_INPUT_BYTES:
        raise ValueError("operation input size is invalid")
    payload = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError("operation input must contain one JSON object")
    return model.model_validate(payload)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Combine one bound Razorpay Test handoff and human callback into a "
            "startup-pinned Checkpoint D operation."
        )
    )
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--callback", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--operation-id")
    args = parser.parse_args()

    operation = PreparedRazorpayTestOperation.create(
        operation_id=args.operation_id or f"prepared_{secrets.token_urlsafe(24)}",
        handoff=_load(args.handoff, RazorpayCheckoutHandoff),
        callback=_load(args.callback, RazorpayCheckoutCallback),
    )
    raw = (
        json.dumps(
            operation.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            args.output,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
    except FileExistsError:
        parser.error("--output already exists; refusing to overwrite a prepared callback")
    print(json.dumps({
        "prepared": True,
        "operation_id": operation.operation_id,
        "prepared_operation_file_sha256": sha256(raw).hexdigest(),
        "callback_signature_printed": False,
        "real_money_moved": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hmac
import json
import os
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from ecocommit._canonical import strict_json_loads
from ecocommit.b8_provenance import (
    CertificateKeyBoundaryReference,
    verify_certificate_key_boundary_reference,
)
from ecocommit.razorpay import (
    RazorpayHTTPTransport,
    RazorpayTestCredentials,
    RazorpayTestPaymentAdapter,
    RazorpayTransport,
)
from ecocommit.razorpay_checkout import (
    RazorpayCheckoutCallback,
    RazorpayCheckoutHandoff,
)


class ReadOnlyEvidenceTransport:
    """Allow only GETs and retain only safe method/path metadata."""

    def __init__(self, inner: RazorpayTransport):
        self.inner = inner
        self.calls: list[dict[str, str]] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        normalized = method.upper()
        if normalized != "GET" or payload is not None:
            raise ValueError("B8 authorization verifier permits GET-only provider access")
        self.calls.append({"method": "GET", "path": path})
        return self.inner.request("GET", path, headers=headers)


def _load_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    raw = path.read_bytes()
    if not raw or len(raw) > 2 * 1024 * 1024:
        raise ValueError(f"{label} has invalid size")
    decoded = strict_json_loads(raw.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError(f"{label} must contain one JSON object")
    return decoded


def _strict_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    return value


def _expected_source_revision(order_evidence: Mapping[str, Any], explicit: str) -> str:
    github = order_evidence.get("github")
    if not isinstance(github, dict):
        raise ValueError("order evidence omits GitHub source binding")
    source = github.get("sha")
    if not isinstance(source, str) or len(source) != 40:
        raise ValueError("order evidence source revision is invalid")
    expected = explicit or os.environ.get("GITHUB_SHA", "")
    if expected and source != expected:
        raise ValueError("authorization verifier is not running at the order source revision")
    return source


def run(
    *,
    order_evidence_path: Path,
    handoff_path: Path,
    callback_path: Path,
    key_reference_path: Path,
    output_path: Path,
    expected_source_revision: str = "",
) -> int:
    if output_path.exists():
        raise ValueError("refusing to overwrite existing B8 authorization evidence")
    evidence: dict[str, Any] = {
        "schema_version": "B8.AUTHORIZATION.READ_ONLY.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": "RAZORPAY",
        "provider_mode": "TEST",
        "source_revision": None,
        "transaction_digest": None,
        "order_id": None,
        "payment_id": None,
        "checkout_hmac_verified": False,
        "certificate_key_reference_verified": False,
        "provider_order_verified": False,
        "provider_payment_verified": False,
        "provider_calls": [],
        "mutating_provider_calls": 0,
        "authorization_subgate_passed": False,
        "capture": {"executed": False},
        "refund": {"executed": False},
        "settlement": {"executed": False},
        "checkout_signature_retained": False,
        "credentials_retained": False,
        "status": "STARTED",
        "blocker": None,
    }
    secrets_to_reject: tuple[str, ...] = ()
    callback_signature = ""
    recorder: ReadOnlyEvidenceTransport | None = None
    exit_code = 0
    try:
        order_evidence = _load_object(order_evidence_path, "order evidence")
        if (
            order_evidence.get("schema_version") != "B8.1"
            or order_evidence.get("checkpoint") != "B8_RAZORPAY_TEST_MODE"
            or order_evidence.get("provider_mode") != "TEST"
        ):
            raise ValueError("order evidence is not the canonical B8 Test order boundary")
        source_revision = _expected_source_revision(
            order_evidence, expected_source_revision
        )
        evidence["source_revision"] = source_revision

        handoff = RazorpayCheckoutHandoff.model_validate(
            _load_object(handoff_path, "Checkout handoff")
        )
        callback = RazorpayCheckoutCallback.model_validate(
            _load_object(callback_path, "Checkout callback")
        )
        reference = CertificateKeyBoundaryReference.model_validate(
            _load_object(key_reference_path, "certificate-key reference")
        )

        github = order_evidence["github"]
        order = order_evidence.get("order")
        handoff_evidence = order_evidence.get("checkout_handoff")
        transaction_evidence = order_evidence.get("transaction")
        if not all(
            isinstance(value, dict)
            for value in (github, order, handoff_evidence, transaction_evidence)
        ):
            raise ValueError("order evidence binding objects are incomplete")
        if order.get("order_id") != handoff.order.order_id:
            raise ValueError("Checkout handoff order does not match server order evidence")
        if handoff_evidence.get("handoff_sha256") != handoff.handoff_sha256:
            raise ValueError("Checkout handoff digest does not match order evidence")
        if transaction_evidence.get("transaction_digest") != handoff.transaction.digest():
            raise ValueError("Checkout transaction digest does not match order evidence")
        if callback.razorpay_order_id != handoff.order.order_id:
            raise ValueError("Checkout callback belongs to another order")

        run_id = github.get("run_id")
        run_attempt = github.get("run_attempt")
        if not isinstance(run_id, str) or not isinstance(run_attempt, str):
            raise ValueError("order evidence run identity is missing")
        verify_certificate_key_boundary_reference(
            reference,
            source_revision=source_revision,
            run_id=run_id,
            run_attempt=run_attempt,
            transaction_digest=handoff.transaction.digest(),
        )
        evidence["certificate_key_reference_verified"] = True
        evidence["certificate_key_reference_sha256"] = reference.key_reference_sha256
        evidence["transaction_digest"] = handoff.transaction.digest()
        evidence["order_id"] = handoff.order.order_id
        evidence["payment_id"] = callback.razorpay_payment_id

        credentials = RazorpayTestCredentials.from_environment()
        secrets_to_reject = tuple(
            value for value in (credentials.key_id, credentials.key_secret) if value
        )
        callback_signature = callback.razorpay_signature
        expected_signature = hmac.new(
            credentials.key_secret.encode("utf-8"),
            f"{handoff.order.order_id}|{callback.razorpay_payment_id}".encode("utf-8"),
            sha256,
        ).hexdigest()
        if not hmac.compare_digest(
            callback.razorpay_signature.casefold(), expected_signature
        ):
            raise ValueError("Checkout HMAC signature is invalid")
        evidence["checkout_hmac_verified"] = True

        recorder = ReadOnlyEvidenceTransport(RazorpayHTTPTransport(credentials))
        adapter = RazorpayTestPaymentAdapter(
            credentials=credentials,
            transport=recorder,
        )
        fetched_order = adapter.fetch_order(
            handoff.transaction,
            order_id=handoff.order.order_id,
        )
        if fetched_order.provider_status != "attempted":
            raise ValueError("Razorpay Test order is not in attempted state")
        evidence["provider_order_verified"] = True
        evidence["provider_order_status"] = fetched_order.provider_status

        observed = adapter.fetch_payments_for_order(
            handoff.transaction,
            order_id=handoff.order.order_id,
        )
        matching = [
            item for item in observed
            if item.payment_id == callback.razorpay_payment_id
        ]
        if len(matching) != 1:
            raise ValueError("exact Checkout payment is not uniquely bound to the order")
        payment = matching[0]
        if (
            payment.provider_status != "authorized"
            or payment.captured
            or payment.amount_captured != 0
            or payment.amount_refunded != 0
        ):
            raise ValueError("Razorpay Test payment is not cleanly authorized and reversible")

        raw_payment = recorder.request(
            "GET", f"/payments/{callback.razorpay_payment_id}"
        )
        if (
            raw_payment.get("id") != callback.razorpay_payment_id
            or raw_payment.get("order_id") != handoff.order.order_id
            or _strict_int(raw_payment.get("amount"), "payment amount")
            != handoff.transaction.amount_minor
            or raw_payment.get("currency") != handoff.transaction.currency
            or raw_payment.get("status") != "authorized"
            or raw_payment.get("captured") is not False
            or _strict_int(
                raw_payment.get("amount_captured", 0), "captured amount"
            ) != 0
            or _strict_int(
                raw_payment.get("amount_refunded", 0), "refunded amount"
            ) != 0
            or raw_payment.get("refund_status") is not None
        ):
            raise ValueError("exact Razorpay Test payment state failed authorization checks")

        evidence["provider_payment_verified"] = True
        evidence["provider_payment_status"] = "authorized"
        evidence["captured"] = False
        evidence["amount_minor"] = handoff.transaction.amount_minor
        evidence["currency"] = handoff.transaction.currency
        evidence["amount_refunded"] = 0
        evidence["refund_status"] = None
        evidence["authorization_subgate_passed"] = True
        evidence["status"] = "PASSED_AUTHORIZATION_READ_ONLY"
    except Exception as exc:
        exit_code = 2
        evidence["status"] = "BLOCKED_AUTHORIZATION_READ_ONLY"
        evidence["blocker"] = {
            "code": type(exc).__name__,
            "boundary": "ECOCOMMIT_B8_AUTHORIZATION_VERIFIER",
        }
    finally:
        if recorder is not None:
            evidence["provider_calls"] = recorder.calls
            evidence["mutating_provider_calls"] = sum(
                call["method"] != "GET" for call in recorder.calls
            )
        serialized = json.dumps(
            evidence,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        forbidden = tuple(
            value
            for value in (*secrets_to_reject, callback_signature)
            if value
        )
        if any(value in serialized for value in forbidden):
            raise RuntimeError("refusing to retain credential or Checkout signature")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized, encoding="utf-8", newline="\n")

    print(
        "B8_AUTHORIZATION_READ_ONLY "
        f"status={evidence['status']} "
        f"passed={str(evidence['authorization_subgate_passed']).lower()} "
        "mutations=0 credentials=redacted"
    )
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify one Razorpay Test Checkout authorization with HMAC and GET-only "
            "provider reads. This command never captures or refunds."
        )
    )
    parser.add_argument("--order-evidence", type=Path, required=True)
    parser.add_argument("--checkout-handoff", type=Path, required=True)
    parser.add_argument("--checkout-callback", type=Path, required=True)
    parser.add_argument("--certificate-key-reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-source-revision", default="")
    args = parser.parse_args()
    return run(
        order_evidence_path=args.order_evidence,
        handoff_path=args.checkout_handoff,
        callback_path=args.checkout_callback,
        key_reference_path=args.certificate_key_reference,
        output_path=args.output,
        expected_source_revision=args.expected_source_revision,
    )


if __name__ == "__main__":
    raise SystemExit(main())

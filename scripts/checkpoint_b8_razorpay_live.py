from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from ecocommit.exposure import TransactionBinding
from ecocommit.github_actions import GitHubRunVerificationError, load_preflight_receipt
from ecocommit.razorpay import (
    RazorpayAPIError,
    RazorpayConfigurationError,
    RazorpayHTTPTransport,
    RazorpayTestCredentials,
    RazorpayTestPaymentAdapter,
    RazorpayTransport,
    RazorpayTransportError,
)
from ecocommit.razorpay_checkout import RazorpayCheckoutHandoff, render_checkout_html


class EvidenceTransport:
    """Record only safe method/path metadata around the credentialed transport."""

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
        self.calls.append({"method": method.upper(), "path": path})
        return self.inner.request(method, path, payload=payload, headers=headers)


class PreflightReferenceError(ValueError):
    pass


def _base_evidence() -> dict[str, Any]:
    return {
        "schema_version": "B8.1",
        "checkpoint": "B8_RAZORPAY_TEST_MODE",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": "RAZORPAY",
        "provider_mode": "TEST",
        "credentials": {
            "injected_from_environment": False,
            "test_prefix_validated": False,
            "key_id_retained": False,
            "key_secret_retained": False,
        },
        "github": {
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "sha": os.environ.get("GITHUB_SHA"),
            "ref_name": os.environ.get("GITHUB_REF_NAME"),
            "credential_preflight_run_id": os.environ.get("B8_PREFLIGHT_RUN_ID"),
        },
        "authentication": {
            "credential_preflight_run_reference_present": bool(
                os.environ.get("B8_PREFLIGHT_RUN_ID")
            ),
            "credential_preflight_run_verified": False,
            "preflight_response_body_retained": False,
            "credentialed_order_api_succeeded": False,
        },
        "provider_calls": [],
        "transaction": None,
        "order": {"executed": False},
        "idempotency": {"validated": False},
        "payments_for_order": {"executed": False},
        "authorization": {"executed": False},
        "capture": {"executed": False},
        "refund": {"executed": False},
        "settlement": {"executed": False},
        "checkpoint_b8_passed": False,
        "status": "STARTED",
        "external_blocker": None,
    }


def run(
    output: Path,
    *,
    preflight_receipt: Path | None = None,
    checkout_handoff: Path | None = None,
    checkout_html: Path | None = None,
) -> int:
    evidence = _base_evidence()
    key_id = ""
    key_secret = ""
    secrets_to_reject: tuple[str, ...] = ()
    recorder: EvidenceTransport | None = None
    exit_code = 0
    try:
        preflight_run_id = os.environ.get("B8_PREFLIGHT_RUN_ID", "")
        if not re.fullmatch(r"[0-9]{6,20}", preflight_run_id):
            raise PreflightReferenceError(
                "a numeric successful credential-preflight run id is required"
            )
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        source_sha = os.environ.get("GITHUB_SHA", "")
        if preflight_receipt is None:
            raise PreflightReferenceError("a verified preflight receipt is required")
        try:
            verified_preflight = load_preflight_receipt(
                preflight_receipt,
                repository=repository,
                run_id=int(preflight_run_id),
                expected_sha=source_sha,
            )
        except GitHubRunVerificationError as exc:
            raise PreflightReferenceError("preflight receipt verification failed") from exc
        evidence["authentication"]["credential_preflight_run_verified"] = True
        evidence["authentication"]["preflight_verification_source"] = (
            verified_preflight["verification_source"]
        )
        evidence["authentication"]["preflight_reference_receipt_sha256"] = (
            verified_preflight["receipt_sha256"]
        )
        evidence["authentication"]["preflight_source_revision"] = (
            verified_preflight["head_sha"]
        )
        credentials = RazorpayTestCredentials.from_environment()
        key_id = credentials.key_id
        key_secret = credentials.key_secret
        secrets_to_reject = tuple(
            value for value in (key_id, key_secret) if value
        )
        evidence["credentials"]["injected_from_environment"] = True
        evidence["credentials"]["test_prefix_validated"] = True
        recorder = EvidenceTransport(RazorpayHTTPTransport(credentials))
        payments = RazorpayTestPaymentAdapter(
            credentials=credentials,
            transport=recorder,
        )

        run_identity = "-".join(
            filter(
                None,
                (
                    os.environ.get("GITHUB_RUN_ID"),
                    os.environ.get("GITHUB_RUN_ATTEMPT"),
                ),
            )
        ) or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        transaction = TransactionBinding(
            transaction_id=f"tx-b8-{run_identity}",
            merchant_id="razorpay-test-mode-boundary",
            amount_minor=100,
            currency="INR",
            contract_hash=sha256(
                f"ECOCOMMIT-B8-RAZORPAY-TEST:{run_identity}".encode()
            ).hexdigest(),
        )
        evidence["transaction"] = {
            "transaction_id": transaction.transaction_id,
            "transaction_digest": transaction.digest(),
            "merchant_id": transaction.merchant_id,
            "amount_minor": transaction.amount_minor,
            "currency": transaction.currency,
            "contract_hash": transaction.contract_hash,
        }

        idempotency_key = f"b8-order-{run_identity}"
        first = payments.create_order(
            transaction,
            idempotency_key=idempotency_key,
        )
        replay = payments.create_order(
            transaction,
            idempotency_key=idempotency_key,
        )
        fetched = payments.fetch_order(transaction, order_id=first.order_id)
        if replay != first or fetched.order_id != first.order_id:
            raise RuntimeError("ECOCOMMIT order idempotency or fetch binding failed")
        evidence["authentication"]["credentialed_order_api_succeeded"] = True
        create_posts = sum(
            call == {"method": "POST", "path": "/orders"}
            for call in recorder.calls
        )
        if create_posts != 1:
            raise RuntimeError("ECOCOMMIT boundary did not create exactly one provider order")
        evidence["order"] = {
            "executed": True,
            "order_id": first.order_id,
            "receipt": first.receipt,
            "provider_status": fetched.provider_status,
            "amount_minor": first.amount_minor,
            "currency": first.currency,
            "transaction_digest": first.transaction_digest,
            "provider_response_recovered": first.recovered,
        }
        if checkout_handoff is not None or checkout_html is not None:
            if checkout_handoff is None or checkout_html is None:
                raise ValueError("both Checkout handoff and HTML paths are required")
            created_at = datetime.now(timezone.utc)
            handoff = RazorpayCheckoutHandoff.create(
                public_key_id=key_id,
                transaction=transaction,
                order=first,
                created_at=created_at,
                expires_at=created_at + timedelta(hours=24),
            )
            checkout_handoff.parent.mkdir(parents=True, exist_ok=True)
            checkout_html.parent.mkdir(parents=True, exist_ok=True)
            checkout_handoff.write_text(
                handoff.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
            checkout_html.write_text(render_checkout_html(handoff), encoding="utf-8")
            evidence["checkout_handoff"] = {
                "generated": True,
                "schema_version": handoff.schema_version,
                "handoff_sha256": handoff.handoff_sha256,
                "expires_at": handoff.expires_at.isoformat(),
                "public_key_id_retained_only_in_handoff": True,
                "secret_key_retained": False,
            }
        evidence["idempotency"] = {
            "validated": True,
            "identical_replay_returned_same_order": True,
            "provider_create_order_post_count": create_posts,
            "idempotency_key_retained": False,
        }

        observed = payments.fetch_payments_for_order(
            transaction,
            order_id=first.order_id,
        )
        evidence["payments_for_order"] = {
            "executed": True,
            "count": len(observed),
            "payment_ids": [item.payment_id for item in observed],
            "statuses": [item.provider_status for item in observed],
        }
        if observed:
            raise RuntimeError("a newly created validation order unexpectedly contains a payment")

        evidence["authorization"] = {
            "executed": False,
            "reason": (
                "Razorpay Payments API cannot collect a payment; a successful "
                "Test Checkout callback with order id, payment id, and signature is required"
            ),
        }
        evidence["capture"] = {
            "executed": False,
            "reason": "no authorized payment id/signature exists; capture API was not called",
        }
        evidence["refund"] = {
            "executed": False,
            "reason": "no captured payment exists",
        }
        evidence["settlement"] = {
            "executed": False,
            "reason": "Test Mode order creation is not capture or settlement evidence",
        }
        evidence["status"] = "ORDER_API_VALIDATED_PAYMENT_LIFECYCLE_BLOCKED"
        evidence["external_blocker"] = {
            "code": "RAZORPAY_CHECKOUT_AUTHORIZATION_REQUIRED",
            "boundary": "RAZORPAY_PRODUCT_API",
            "detail": (
                "The server-side Payments API can fetch/capture payments but cannot "
                "collect one. This run has no genuine authorized payment or Checkout signature."
            ),
        }
    except PreflightReferenceError:
        exit_code = 2
        evidence["status"] = "BLOCKED_PREFLIGHT_REFERENCE"
        evidence["external_blocker"] = {
            "code": "RAZORPAY_PREFLIGHT_REFERENCE_REQUIRED",
            "boundary": "ECOCOMMIT_B8_VALIDATOR",
        }
    except RazorpayConfigurationError:
        exit_code = 2
        evidence["status"] = "BLOCKED_CONFIGURATION"
        evidence["external_blocker"] = {
            "code": "RAZORPAY_TEST_CREDENTIAL_CONFIGURATION_REJECTED",
            "boundary": "GITHUB_ACTIONS_SECRET_INJECTION",
        }
    except RazorpayAPIError as exc:
        exit_code = 2
        evidence["status"] = "BLOCKED_RAZORPAY_API"
        evidence["external_blocker"] = {
            "code": "RAZORPAY_API_REJECTED_REQUEST",
            "boundary": "RAZORPAY_API",
            "http_status": exc.status_code,
            "provider_code": exc.provider_code,
        }
    except RazorpayTransportError:
        exit_code = 2
        evidence["status"] = "BLOCKED_RAZORPAY_TRANSPORT"
        evidence["external_blocker"] = {
            "code": "RAZORPAY_TRANSPORT_OR_RESPONSE_INVALID",
            "boundary": "RAZORPAY_API",
        }
    except Exception as exc:
        exit_code = 3
        evidence["status"] = "FAILED_ECOCOMMIT_VALIDATION"
        evidence["external_blocker"] = {
            "code": type(exc).__name__,
            "boundary": "ECOCOMMIT_B8_VALIDATOR",
        }
    finally:
        if recorder is not None:
            evidence["provider_calls"] = recorder.calls
        serialized = json.dumps(
            evidence,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        if any(secret in serialized for secret in secrets_to_reject):
            raise RuntimeError("refusing to retain evidence containing a credential value")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8", newline="\n")

    print(
        "B8_RAZORPAY_TEST_EVIDENCE "
        f"status={evidence['status']} "
        f"checkpoint_b8_passed={str(evidence['checkpoint_b8_passed']).lower()} "
        "credentials=redacted"
    )
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the redacted ECOCOMMIT B8 Razorpay Test Mode boundary validation."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/checkpoint-b8-razorpay-test.json"),
    )
    parser.add_argument("--preflight-receipt", type=Path, required=True)
    parser.add_argument("--checkout-handoff", type=Path)
    parser.add_argument("--checkout-html", type=Path)
    args = parser.parse_args()
    return run(
        args.output,
        preflight_receipt=args.preflight_receipt,
        checkout_handoff=args.checkout_handoff,
        checkout_html=args.checkout_html,
    )


if __name__ == "__main__":
    sys.exit(main())

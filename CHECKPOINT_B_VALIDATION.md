# ECOCOMMIT Checkpoint B Validation Report

- Validation date: 2026-09-01
- Local implementation under test: `3d4a14300c66d6ed775321048ab20af9182ebc68`
- Live Razorpay validation snapshot: `596001c` on the isolated validation branch
- Overall verdict: **BLOCKED — NOT PASSED**
- Payment backends: **`SIMULATED_LOCAL`** and **`RAZORPAY_TEST_MODE`**

No acceptance threshold was changed. Razorpay Test Mode authentication and the
order-level boundary were exercised with credentials injected only by GitHub
Actions. No payment was authorized, captured, refunded, or settled, and no such
outcome is claimed. Test Mode moved no real money.

## Acceptance rule

Checkpoint B may pass only when all of the following are true together:

1. the real Checkpoint A gate is accepted with retained evidence;
2. a current A contract can enter B only through the fidelity and policy
   admission boundary;
3. deterministic policy mapping, authoritative evidence, exposure, progressive
   commitment, TOCTOU protection, certificates, idempotency, reconciliation, and
   compensation pass their adversarial tests;
4. required state and idempotency records are durable enough for the claimed
   execution environment, and signing-key handling satisfies the claimed
   security boundary; and
5. Razorpay Test Mode is exercised through the dedicated adapter with provider
   identifiers plus authorization, capture, webhook/reconciliation, failure, and
   compensation evidence as applicable.

Unit tests, credential presence, order creation, or simulated payment results
alone cannot satisfy this rule.

## Live Razorpay Test Mode evidence

| Validation | Evidence | Result |
|---|---|---:|
| Redacted credential preflight | GitHub Actions run `33534255136` | **PASS** — read-only `GET /v1/orders?count=1` returned HTTP 200 in Test Mode; secret values, headers, and provider body were not printed or retained |
| Independent repeat preflight at the adapter snapshot | GitHub Actions run `33535533432` | **PASS** — authenticated Test Mode probe repeated successfully |
| Order-boundary lifecycle validator | GitHub Actions run `33535533557`, job `validate-order-api-boundary-without-capture-claim` | **PASS FOR THE ORDER SUBGATE ONLY** — one INR 1.00 Test Mode order was created, fetched, and rebound to the exact transaction digest, amount, currency, contract hash, and merchant digest |
| ECOCOMMIT idempotency boundary | Same lifecycle run | **PASS FOR IDENTICAL REPLAY** — the replay returned the same provider order and the recorder observed exactly one provider `POST /orders` |
| Newly-created order payment listing | Same lifecycle run | **PASS** — the bound order was revalidated before its payments were fetched; zero payments were attached |
| Redacted evidence artifact | Artifact `checkpoint-b8-razorpay-test-evidence-33535533557`, ID `9811456771` | **RETAINED** — 1,408-byte archive; GitHub artifact SHA-256 `6d8cdcabbc78093f2638c8fbefd2e7bcd4d566d1eb807cd6fa0abf709d700f4d` |
| Payment authorization/reservation | No genuine Checkout callback | **NOT RUN / EXTERNALLY BLOCKED** |
| Capture, refund, webhook, reconciliation, settlement | No authorized payment or separately configured webhook endpoint/secret | **NOT RUN / BLOCKED** |

The pushed Candidate 3 source now also has a fresh same-revision evidence pair:

| Validation | Evidence | Result |
|---|---|---:|
| Exact-source redacted credential preflight | GitHub Actions run `33592456896` at `fd26a52a…` | **PASS** — the read-only Test authentication probe completed successfully without retaining the provider body or credentials |
| Exact-source order boundary | GitHub Actions run `33592499084` at `fd26a52a…` | **PASS FOR THE ORDER SUBGATE ONLY** — one INR 1.00 Test order, one provider create across identical replay, zero payments, no capture, and a generated Checkout handoff |
| Exact-source artifact | Artifact `checkpoint-b8-razorpay-test-evidence-33592499084`, ID `9832232980` | **RETAINED** — downloaded archive SHA-256 `56ca57750589d41cbf4b9ea717d0b48d7dfb16344702a5f0b6d7d5d1a350000d` matched GitHub; `checkpoint_b8_passed=false` and blocker `RAZORPAY_CHECKOUT_AUTHORIZATION_REQUIRED` |
| Checkout handoff | Same artifact; expires `2026-09-03T04:53:12.35686Z` | **READY FOR HUMAN TEST INTERACTION** — Checkout HTML SHA-256 `ad7c60fd53490693a6fc878a140a21e11be9bccbde997016e385e58c53d97fe5`; no callback exists yet |

The historical order-boundary workflow's successful conclusion means its truthful validation
script completed and retained the blocked result; it does **not** mean B8 or
Checkpoint B passed. Its evidence field `checkpoint_b8_passed` remained `false`.

Exact external blocker:
`RAZORPAY_CHECKOUT_AUTHORIZATION_REQUIRED`. Razorpay's
[server-side Payments API](https://razorpay.com/docs/api/payments/) can fetch and
capture a payment but cannot collect one. Continuing requires a successful
[Test Checkout callback](https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/integration-steps/)
containing the bound `razorpay_order_id`, `razorpay_payment_id`, and
`razorpay_signature`. ECOCOMMIT then verifies the signature and provider entities
before representing the authorization as `RESERVED`. The account must also use
[manual capture](https://razorpay.com/docs/payments/payments/capture-settings/);
the final evidence contract requires the exact three-day timeout and Normal
Refund action. Auto-capture or another timeout action would bypass or change
ECOCOMMIT's delayed-capture safety boundary and is rejected.

The current local tree closes the earlier software handoff and single-host
durability gaps. The order
validator can emit a digest-bound Test Checkout JSON handoff and standalone HTML
page. The page downloads a typed callback file after the human Test Checkout. A
continuation command verifies the callback and exact provider entities, captures
only behind ECOCOMMIT's certificate/TOCTOU boundary, issues an idempotent full
refund through compensation, and reconciles the final state. Payment,
commitment, idempotency, and completed-operation results can be held in one
SQLite WAL/FULL-sync database. A raw-body webhook endpoint verifies the separate
webhook HMAC, binds `payment.captured` and `refund.processed` to the exact pinned
operation, deduplicates `X-Razorpay-Event-Id`, accepts either arrival order, and
exports a digest-bound two-event set without retaining raw bodies. This path has
deterministic fake-transport regression evidence only; it has not been exercised
against the provider and is not added to the live evidence table above.

A write-once finalizer now cross-validates that lifecycle against the exact A
receipt, source-bound preflight/order/handoff, verified webhook set, audit chain,
complete deterministic/durability manifests, non-secret signing-key reference,
and two Dashboard screenshot attestations. It derives the B receipt without a
caller pass flag. The manual-capture attestation requires Test Mode, manual
capture, exactly 259,200 seconds, and `NORMAL_REFUND`; the webhook attestation
requires HTTPS and exactly `payment.captured` plus `refund.processed`. Both bind
the Test account, source, observation time, screenshot digest, and verifier
reference. Final outputs publish atomically, allow only byte-identical replay,
recover a one-file crash boundary, and require an exact same-repository GitHub
Actions artifact reference. This is locally tested preparation, not an attested
Dashboard state or provider result.

The isolated live snapshot was used so the active frozen Checkpoint A retry and
its main-branch inputs were not changed. The local implementation commit adds
follow-up hardening: permanent manual-only preflight/order-boundary workflows,
an API-verified same-repository/same-workflow/same-revision preflight receipt,
commit-pinned actions, protected HTTP authentication headers, and coherent
provider-result validation. Those follow-up changes have local test evidence but
were not relabeled as part of the earlier live run.

## Local deterministic validation

| Validation | Result |
|---|---:|
| Focused Checkpoint B suite | **80 / 80 passed** |
| Focused Razorpay adapter/workflow suite | **27 / 27 passed** |
| Full deterministic regression suite | **224 / 224 passed** |
| Source/script/test bytecode compilation | **Passed** |
| Installed dependency consistency | **Passed** |
| Current-tree credential-value marker scan | **Passed** |
| Fresh clone at `68d6798ecf1577529a07ef8585bea7d9999bd863` with a new virtual environment | **224 / 224 passed**; compilation, `pip check`, JavaScript syntax, readiness structure, diff check, and clean status passed |
| Current Checkpoint B-focused suite | **115 / 115 passed** |
| Current workflow-security suite | **7 / 7 passed** |
| Current full deterministic suite | **369 / 369 passed** |
| Current no-hardlink clone at `60c85f0b75574007a7bf1de9a8b4be7214c69a75` using its hash-locked virtual environment | **369 / 369 passed**; compilation, `pip check`, JavaScript syntax, readiness structure, diff check, and clean status passed |
| Current B8 finalizer regression | **25 / 25 passed** |
| Current integrated local suite after finalizer/provenance hardening | **465 / 465 passed** |

Validation environment: Windows, Python 3.14.6, Pydantic 2.13.5, pytest 8.4.2.

Commands used for the current deterministic evidence:

```powershell
.venv\Scripts\python.exe -m compileall -q src scripts tests
.venv\Scripts\python.exe -m pytest -o addopts="" -q -p no:cacheprovider --basetemp=.test-tmp-b8-focused-3d4a143 tests -k checkpoint_b
.venv\Scripts\python.exe -m pytest -o addopts="" -q -p no:cacheprovider --basetemp=.test-tmp-b8-full-3d4a143
.venv\Scripts\python.exe -m pip check
```

The clean clone was created without hardlinks, installed from
`requirements-dev.lock`, and validated on the same host/operator; it is a clean
environment check, not independent-machine reproduction. The Razorpay tests use
deterministic fake transports to exercise binding and failure branches. They
never count as live provider evidence.

The current validator verifies the same-revision preflight receipt before it
reads either Razorpay credential through the credential factory. The
tampered-receipt regression supplies credential values, replaces that factory
with a fail-on-access trap, and proves the rejected path reaches neither the
credential loader nor provider construction.

The GitHub run verifier, Razorpay API transport, and inline Razorpay credential
preflight also keep `Authorization` outside the header set copied by Python's
redirect handler and reject a changed final URL. Cross-origin and same-origin
redirect regressions prove the verifier cannot accept redirected run evidence;
the Razorpay transport regression proves its Basic value is non-redirectable.
These are local controls for future runs, not new Razorpay evidence.
Both Razorpay workflows and every other secret-bearing workflow are manual-only;
a source push cannot independently authorize a credentialed call.

## Gate results

| Gate | Evidence and result | Status |
|---|---|---:|
| A prerequisite | Candidate 1 in run `33493409547` is mathematically failed at attempt 15: 21 passes, 11 terminal contract failures, 48 provider deferrals, maximum 69/80. Candidate 2 run `33583323178` is incomplete and exposed a runner classification defect. Candidate 3 run `33590028177` attempt 2 has `C002` passed, `A002` unchanged failed, 78 provider-deferred cases, and no complete receipt. | **NOT PASSED / PROVIDER-BLOCKED** |
| B1 — Policy Class Mapper | Exhaustive mapping and fail-closed A admission tests pass | **LOCAL PASS** |
| B2 — Evidence Registry | Authority, identity, version, time, freshness, revocation, subject, and exact-claim adversarial tests pass | **LOCAL PASS** |
| B3 — Evidence-to-Exposure Policy | Only trusted caps and authoritative exact claims determine exposure | **LOCAL PASS** |
| B4 — Progressive Commitment | Illegal transitions and capture without the exact reservation/certificate/state are denied | **LOCAL PASS** |
| B5 — Freshness / TOCTOU | Bound-field mutation and concurrent evidence changes fail closed | **LOCAL PASS** |
| B6 — Commit Certificates | Transaction/evidence/policy/expiry/nonce binding and tamper tests pass | **LOCAL PASS — HMAC TEST BOUNDARY ONLY** |
| B7 — Idempotency / Compensation | Execute-once, collision, cross-process concurrency, durable restart replay, crash-window reconstruction, reconciliation, and compensation tests pass | **LOCAL PASS — SQLITE SINGLE-HOST BOUNDARY** |
| B8a — Test credentials/authentication | Two redacted Actions preflights authenticated successfully | **LIVE SUBGATE PASS** |
| B8b — Order/binding/idempotency | Real Test Mode order creation, exact binding, fetch, and identical replay validated | **LIVE SUBGATE PASS** |
| B8c — Authorization/capture/refund/webhook lifecycle | Checkout authorization and the downstream provider lifecycle were not executed | **BLOCKED / NOT PASSED** |

## B8 implementation boundary

The Test Mode adapter:

- verifies the referenced preflight through GitHub's bounded Actions API before
  loading Razorpay credentials; repository, workflow path, `workflow_dispatch`
  event, successful conclusion, run ID, attempt, and exact source SHA are bound
  into a strict digest-checked receipt;
- loads only `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` from the environment and
  refuses non-test key IDs;
- rejects credential values before writing the redacted evidence object; the
  later summary and artifact-upload steps receive no Razorpay credentials;
- fixes the provider origin to `https://api.razorpay.com/v1`, protects its
  authentication/host/content-length headers, emits only safe error metadata,
  and never logs credentials or provider bodies;
- binds orders and payments to the exact transaction ID digest, amount, currency,
  contract hash, merchant digest, provider receipt, order ID, and payment ID;
- recovers an ambiguous order create only through an exact provider-side receipt
  and binding match;
- verifies the Checkout HMAC before fetching and binding a genuinely authorized,
  uncaptured payment;
- retains ECOCOMMIT's existing `CAPTURE_ALLOWED` certificate, freshness, and
  TOCTOU gate before an exact-amount provider capture;
- uses the provider's refund idempotency header and distinguishes pending from
  processed refunds; the shared compensation boundary remains
  `COMPENSATION_PENDING` until the provider confirms `processed`; retries poll
  the exact bound refund by ID instead of replaying a terminal pending result;
- explicitly rejects immediate void because Razorpay exposes no immediate void
  API for an authorization; and
- provides a raw-body HMAC endpoint for a separately configured webhook secret,
  durable official event-ID deduplication, exact order/payment/refund binding,
  out-of-order capture/refund handling, and redacted evidence export, without
  claiming that a live webhook was delivered;
- persists payment, commitment, idempotency, and completed execution results in
  SQLite WAL with `synchronous=FULL`, uses optimistic CAS, and resumes a fully
  completed lifecycle without another provider call; and
- keeps pending compensation retryable instead of caching it as a terminal
  operation result, including after handoff expiry when exact durable capture or
  prior capture-authority state proves that the lifecycle had already started.

`SIMULATED_LOCAL` remains an explicit local/test backend and was not silently
replaced by provider behavior.

## Remaining blockers

1. **Checkpoint A has not passed.** The real A-to-B admission path remains locked.
2. **B8 payment execution is incomplete.** A genuine Test Checkout authorization
   and signature are required before the locally implemented continuation can be
   validated against Razorpay. Manual capture must be configured first.
   After the current tree is pushed, a fresh same-revision credential preflight
   and order-boundary run must precede that Checkout.
3. **Webhook and asynchronous reconciliation evidence is absent.** The user
   supplied API credentials, not a webhook secret/endpoint or delivered events.
4. **Live durability/recovery evidence is absent.** The SQLite implementation is
   locally cross-process/restart tested, but there is no retained provider-run
   crash injection, backup/restore, disk-loss, multi-host, or high-availability
   evidence. It is not a malicious-database-tamper boundary.
5. **Key management is not production-grade.** The environment-only certificate HMAC
   boundary is not a KMS, rotation, or production access-control claim.

Until every blocker is cleared and the complete gate is rerun, B8 and Checkpoint
B remain **blocked / not passed**.

# ECOCOMMIT Checkpoint B Validation Report

- Validation date: 2026-09-01
- Implementation under test: `6877a817f458f1ea7294566931fcf89b9a8eb4cc`
- Overall verdict: **BLOCKED — NOT PASSED**
- Payment mode: **`SIMULATED_LOCAL` only**

No acceptance threshold was changed. No Razorpay API request was made, no
Razorpay outcome is claimed, and no local simulation is counted as provider
evidence.

## Acceptance rule

Checkpoint B may pass only when all of the following are true together:

1. the real Checkpoint A gate is accepted with retained evidence;
2. a current A contract can enter B only through the fidelity and policy
   admission boundary;
3. deterministic policy mapping, authoritative evidence, exposure, progressive
   commitment, TOCTOU protection, certificates, idempotency, reconciliation, and
   compensation pass their adversarial tests;
4. required state and idempotency records are durable enough for the claimed
   execution environment, and signing-key handling satisfies the security
   boundary being claimed;
5. Razorpay Test Mode is exercised with a dedicated adapter, verified test
   credentials, provider/webhook reconciliation, and retained end-to-end evidence.

Unit tests or simulated payment results alone cannot satisfy this rule.

## Validation evidence

| Validation | Result |
|---|---:|
| Focused Checkpoint B suite | **53 / 53 passed** |
| Full deterministic regression suite | **147 / 147 passed** |
| Repeated concurrency adversarial runs | **20 / 20 runs passed** (2 race tests per run) |
| Source/test bytecode compilation | **Passed** |
| Installed dependency consistency | **Passed** |
| Razorpay credential variables | **Not present** |
| Razorpay adapter/API calls | **Not implemented / not run** |

Validation environment: Windows, Python 3.14.6, Pydantic 2.13.5, pytest 8.4.2.

Commands used for the final deterministic evidence:

```powershell
.venv\Scripts\python -m compileall -q src tests
.venv\Scripts\python -m pytest -q -p no:cacheprovider --basetemp=.test-tmp-b-final tests/test_checkpoint_b_a_integration.py tests/test_checkpoint_b_policy_exposure.py tests/test_checkpoint_b_evidence_certificates.py tests/test_checkpoint_b_commitment_idempotency.py tests/test_checkpoint_b_compensation_reconciliation.py
.venv\Scripts\python -m pytest -q -p no:cacheprovider --basetemp=.test-tmp-full-final
.venv\Scripts\python -m pip check
```

The first unrestricted full-suite attempt encountered a Windows temporary-folder
permission error in pytest setup. It was rerun with an isolated workspace-local
temporary directory and passed 147/147; the setup error is not counted as a
product failure or as passing evidence.

## Gate results

| Gate | Pass criterion | Evidence and result | Status |
|---|---|---|---|
| A prerequisite | One real full A run passes every frozen A threshold together | Latest real full gate, GitHub Actions run `33477953132`, failed enforcement | **BLOCKED** |
| B1 — Policy Class Mapper | Every A clause type maps deterministically to exactly one closed policy class; non-validated contracts release no obligations | Exhaustive 11/11 class matrix; mapper now consumes the current `FidelityReport`; the integration boundary recomputes A validation | **LOCAL PASS** |
| A-to-B admission | A failure, clarification, rejection, or contract-hash substitution cannot produce B authority | Actual failed-A fixture releases no obligations/certificate; synthetic passed-A fixture proves interface compatibility only and is explicitly not A evidence | **LOCAL PASS; REAL RUN BLOCKED BY A** |
| B2 — Evidence Registry | Only registered issuer/kind/subject identities, monotonic versions/times, unrevoked current records, and fresh exact claims can be used | Authority takeover, timestamp rollback, conflicting version, mutation, revocation, stale/future, wrong subject, and negative-claim tests pass | **LOCAL PASS** |
| B3 — Evidence-to-Exposure Policy | Only trusted policy caps plus exact authoritative claim predicates determine exposure; payload/model values cannot raise the cap | Negative authorization and injected `max_exposure_minor` fail closed; wrong authority, subject, currency, expiry, and over-cap requests deny | **LOCAL PASS** |
| B4 — Progressive Commitment | Capture cannot skip `PROPOSED -> AUTHORIZED -> RESERVED -> CAPTURE_ALLOWED`; state history, certificate, and reservation reference must match | Illegal history/state jumps, irreversible reserve, wrong stage, wrong hold, cancellation-after-capture, and stranded-failure tests pass | **LOCAL PASS** |
| B5 — Freshness / TOCTOU | Transaction and evidence mutations deny; a concurrent evidence update cannot land between final verification and local capture | All transaction fields, evidence digest/version/revocation/expiry, contract hash, and atomic capture-boundary race tests pass; race tests repeated 20 times | **LOCAL PASS** |
| B6 — Commit Certificates | A denied/forged decision or any signed-payload mutation cannot authorize capture; certificate is transaction/evidence/policy/time/nonce bound | Trusted-policy recomputation, HMAC/id/nonce/signature tampering, expiry, key ID, and full transaction-binding tests pass | **LOCAL PASS — HMAC TEST BOUNDARY ONLY** |
| B7 — Idempotency / Compensation | Identical retries do not duplicate side effects; collisions deny; failed and ambiguous outcomes remain recoverable and auditable | Concurrent execute-once, full-request collision, retry, refund, duplicate-refund denial, capture-journal recovery, existing-refund recovery, and reconciliation tests pass | **LOCAL PASS — PROCESS-LOCAL ONLY** |
| B8 — Razorpay Test Mode | Real Razorpay Test Mode adapter executes permitted transitions and rejects forbidden ones with retained provider/webhook evidence | No credentials are available and no adapter exists | **NOT RUN / BLOCKED** |

## Defects found and fixed during validation

- Replaced the bare A status handoff with a fail-closed bridge that recomputes the
  current fidelity report and honors the actual Checkpoint A gate.
- Added exact claim predicates so authoritative evidence with `approved: false`
  cannot satisfy an exposure tier, while arbitrary monetary claims cannot raise a
  trusted cap.
- Prevented an evidence ID from changing authority, issuer, kind, subject, or
  moving its observation time backwards across versions.
- Held the evidence version lock through the final simulated capture mutation,
  closing the concurrent freshness check/use window.
- Required capture to carry the exact `CAPTURE_ALLOWED` commitment, certificate,
  transaction, and real reservation reference; a certificate alone can no longer
  bypass the progressive state machine.
- Included the complete signed certificate and commitment in capture idempotency
  identity, so a tampered request collides instead of replaying success.
- Validated the legality and stored references of reconstructed commitment
  histories and prevented captured funds from entering a terminal failed state
  that makes compensation impossible.
- Added recovery for capture-before-journal and refund-before-journal crash windows,
  plus immutable compensation-reason and duplicate-refund checks.

## Remaining blockers

1. **Checkpoint A has not passed.** The real A-to-B admission path therefore
   remains locked, even though a synthetic passed-gate fixture proves interface
   compatibility.
2. **B8 is unavailable.** There is no Razorpay adapter, no verified Test Mode
   credential set, no webhook path, and no retained provider evidence.
3. **Durability is not proven.** Evidence, commitment/payment state, and the
   idempotency ledger remain process-local; restart/crash persistence is not
   claimed.
4. **Key management is not production-grade.** The local HMAC key boundary is not
   a KMS, rotation, access-control, or production-secret-handling claim.

Until every blocker is cleared and the complete gate is rerun, Checkpoint B must
remain **not passed**.

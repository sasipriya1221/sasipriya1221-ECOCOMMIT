# ECOCOMMIT Architecture

This document describes the implemented local architecture and the boundaries
still required for final integration. It is not evidence that A, B, C, D, or E
passed.

## Safety thesis

ECOCOMMIT separates interpretation from authority:

> A probabilistic model may propose a contract. Only deterministic policy, fresh
> authoritative evidence, and transaction-bound authorization may increase
> irreversible economic exposure.

Missing, ambiguous, stale, conflicting, unregistered, or unverifiable inputs fail
closed. They lead to clarification, rejection, or no-op behavior; they do not
remove checks or guess a payment amount.

## Trust-boundary flow

```text
Natural-language procurement mandate
                  |
                  v
       [Untrusted intent provider]
                  |
       candidate contract + spans
                  v
      [Fidelity / ambiguity validator]
                  |
       validated candidate only
                  v
       [Closed policy-class mapper]
                  |
                  +-------------------------------+
                  |                               |
                  v                               v
       [Trusted exposure policy] <--- [Registered evidence registry]
                  |                    issuer / kind / subject /
                  |                    version / freshness / claims
                  v
       [Deterministic exposure decision]
                  |
                  v
       [Progressive commitment state]
                  |
                  v
       [Transaction-bound certificate]
                  |
       final verification + idempotency
                  v
    [SIMULATED_LOCAL | guarded RAZORPAY_TEST_MODE]

Audit and observability describe the D API boundary and outcomes.
They never grant authority.
```

## Components and authority

| Component | May do | Must never do |
|---|---|---|
| Intent provider | Propose structured clauses and source spans | Grant payment authority or choose an exposure cap |
| Fidelity validator | Check structure, grounding, risk, ambiguity, and abstention | Repair material meaning by guessing |
| A-to-B bridge | Recompute fidelity and release closed policy obligations only after a typed, digest-bound passing A receipt | Trust a caller-supplied `VALIDATED`, evidence string, test fixture, or `checkpoint_a_passed` flag |
| Policy mapper | Map each current clause type to one fixed policy class | Execute model-generated free-form rules |
| Evidence registry | Enforce registered authority/issuer/kind/subject, monotonic versions/time, freshness, revocation, and exact claims | Treat arbitrary request payloads as evidence |
| Exposure policy | Compute a cap from trusted configuration and verified evidence | Accept a model- or evidence-supplied monetary ceiling |
| Commitment engine | Enforce explicit legal state transitions | Skip stages or silently move backward |
| Certificate signer/verifier | Bind policy, evidence, contract, merchant, amount, currency, transaction, time, and nonce | Authorize a changed/replayed transaction |
| Payment adapter | Simulate locally or call the explicitly verified Razorpay Test Mode boundary | Present simulation/order-only evidence as a completed payment or enable live money |
| Reconciliation/compensation | Detect divergence and record cleanup/reversal | Erase the original attempt |
| D API/UI | Report gate truth, run fixed synthetic scenarios, deny real commits | Infer acceptance from health or caller claims |
| Audit/observability | Record D boundary requests, denials, workflow summaries, correlations, and metrics | Change decisions or suppress blockers |
| Benchmark harness | Execute frozen roles/scenarios and validate complete artifacts | Promote preliminary/synthetic results to final |

## Current implemented paths

### Live Checkpoint A path

The live runner calls an allowlisted HTTPS OpenAI-compatible provider, validates
every model-supplied required field before defaults, permits one bounded schema
correction, scores frozen cases, and writes redacted trace metadata. Candidate 2
binds rows to dataset/case/prompt/schema/evaluator/runner/criteria/provider/source
digests and recomputes semantic results during aggregation. Immutable attempt
artifacts support resume of pure provider deferrals and reject conflicts.

Candidate 1 is mathematically failed. Candidate 2 is locally validated but has
not run remotely, so A has not passed the frozen gate.

### Deterministic B path

The B integration boundary accepts a complete current contract plus a matching
typed Checkpoint A receipt. It recomputes fidelity, maps obligations, evaluates
registered evidence and exposure, and may issue a transaction-bound certificate.
The commitment engine and explicit `SIMULATED_LOCAL` adapter enforce the local
reserve/capture sequence. A separate `RAZORPAY_TEST_MODE` adapter creates and
validates bound orders, binds a genuine Checkout-authorized payment only after
HMAC and provider checks, and preserves the same certificate/freshness gate before
capture. It is not wired into the D endpoint.

The Test-order validator can generate a digest-bound public Checkout handoff and
standalone page. Its callback continuation verifies the Checkout signature and
provider entities, captures behind the same certificate/freshness gate, performs
an idempotent compensating refund, and reconciles the result. That continuation
has local fake-transport evidence only and is not wired into D.

A synthetic passed-A fixture proves interface compatibility only. The actual A
gate releases no B authority until it passes. Live evidence currently stops at
Test authentication and order creation/fetch/idempotency; no provider payment
lifecycle was executed.

### Preliminary C path

The benchmark runner accepts an explicitly frozen plan and suite, exact code
revision and tree state, and required comparator roles. It retains every scheduled
row, including errors, computes deterministic loss/latency metrics, and validates
the artifact by semantic recomputation.

The checked-in fixture is synthetic and `PRELIMINARY_NOT_FINAL`. The runner
rejects final-held-out scenarios. A separate final preregistration/evidence model
binds A/B receipts, suite/case/cost/metric hashes, comparator/candidate identity,
and quantitative acceptance rules before outcomes, and refuses fixtures or
simulated final inputs. No real final registration or result exists.

### D local product path

The real endpoint `/v1/commit` has no execution adapter and always denies. The
simulation endpoint accepts only a named scenario selector; all other request
fields are ignored for authority. Its fixed fixture exercises the current local
A-to-B, exposure, certificate, commitment, and `SIMULATED_LOCAL` components.

```text
GET  /healthz             -> process liveness only
GET  /readyz              -> 503 while irreversible path is blocked
GET  /v1/status           -> A–E gate/provider/blocker snapshot
GET  /v1/metrics          -> finite in-process metric snapshot
POST /v1/commit/simulate  -> fixed synthetic scenario only
POST /v1/commit           -> always denied; no execution adapter
```

The loopback demo server loads every gate as blocked because it has no
authoritative evidence source. Browser health, a green synthetic trace, or an
operator-supplied field cannot change this.

## Progressive economic state

The implemented normal sequence is:

```text
PROPOSED -> AUTHORIZED -> RESERVED -> CAPTURE_ALLOWED -> CAPTURED
```

Explicit terminal/recovery states include `CANCELLED`, `FAILED`,
`COMPENSATION_PENDING`, and `COMPENSATED`. Capture requires the exact current
transaction, certificate, `CAPTURE_ALLOWED` state, and real local reservation
reference. Certificate verification holds the evidence version lock through the
simulated capture mutation.

## Invariants

1. Model output is always untrusted data.
2. A contract that requires clarification or is rejected releases no B
   obligations.
3. Policy classes and exposure ceilings come from trusted configuration.
4. Evidence is registered, scoped, versioned, fresh, unrevoked, and exact-claim
   checked.
5. Certificates bind all economically relevant transaction and evidence fields.
6. Any bound-field or evidence change requires a new decision and certificate.
7. Capture cannot bypass the progressive state machine or reversible hold.
8. Idempotency includes the complete signed request; collisions do not replay
   success.
9. Compensation appends a new state/event; it does not rewrite history.
10. Simulation is labeled in API, UI, payment results, traces, and artifacts.
11. Health is liveness only; it never proves acceptance or readiness.
12. Final checkpoint claims require retained evidence, not component existence.

## Audit and observability boundary

The D API uses a local JSONL SHA-256 chain with strict row validation, fsync, and
shared in-process locks. It detects modification/reordering when verified against
the retained chain, but it is not immutable storage: deletion of an unanchored
tail, multi-process races, host compromise, and disaster recovery remain outside
the claim.

D records parser denials and service workflow summaries. The B components do not
yet emit a durable per-boundary D event stream during a real integrated run. That
integration, external collection, retention, alerts, and SLO evidence remain D
blockers.

## Runtime modes

| Mode | External provider | Real money | Current availability |
|---|---:|---:|---|
| `SIMULATED` / `SIMULATED_LOCAL` | No | No | Implemented for local tests/demo |
| `REAL_PROVIDER_TEST` + verified `RAZORPAY_TEST_MODE` | Test provider only | No real money | Adapter implemented; authentication and order subgates have retained live evidence; payment lifecycle blocked |
| Live/production | Disabled and out of current scope | Not allowed | No code path |

A configuration string or credential presence is not provider-mode proof. The
Test Mode adapter refuses non-test key IDs and validates provider entities, but
only the redacted authentication and order-level subgates have run. A genuine
Checkout authorization plus capture, webhook/reconciliation, and compensation
evidence are still required. Ambiguous order/capture outcomes recover only from
an exact provider-side binding match.

## Repository map

| Area | Implementation |
|---|---|
| A contracts/interpretation | `contracts.py`, `interpreter.py`, `validator.py`, `evaluation.py`, Candidate 2 protocol scripts |
| A-to-B admission | `checkpoint_a_evidence.py`, `checkpoint_b_integration.py` |
| B deterministic safety | `policy.py`, `evidence.py`, `exposure.py`, `certificates.py`, `commitment.py`, `idempotency.py`, `payments.py`, `razorpay.py`, `razorpay_checkout.py`, `reconciliation.py` |
| C benchmark | `checkpoint_c_models.py`, `checkpoint_c_baselines.py`, `checkpoint_c_metrics.py`, `checkpoint_c_runner.py`, `checkpoint_c_final.py` |
| D product/operations | `checkpoint_status.py`, `audit.py`, `observability.py`, `service.py`, `api.py`, `checkpoint_d_workflow.py`, `demo_server.py`, `ui/` |
| E evidence discipline | `REPRODUCIBILITY.md`, `ENGINEERING_LOG.md`, `SUBMISSION_EVIDENCE.md`, `DEMO_RUNBOOK.md`, `PITCH_OUTLINE.md`, readiness checker |

## Checkpoint dependencies

Independent construction is allowed when it does not trust an unmet prerequisite.
Acceptance stays sequential:

```text
A PASS
  -> B real A-to-B + provider Test Mode PASS
      -> C frozen integrated final comparison PASS
          -> D final integrated product/operations PASS
              -> E retained submission bundle PASS
```

Local B/C/D/E work can pass its own engineering checks while remaining blocked.
No later checkpoint is inferred from an earlier implementation or test result.

## Non-goals and missing production boundaries

- Production or live-money execution.
- Autonomous selection of evidence authorities or policy caps.
- Durable database/queue/ledger, multi-process locking, KMS, or key rotation.
- Hosted authentication/authorization, rate limiting, deployment, SLOs, or
  disaster recovery.
- Treating the synthetic C fixture or D demo as final evidence.
- Lowering A thresholds or tuning C after final held-out outcomes.

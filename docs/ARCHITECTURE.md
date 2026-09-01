# ECOCOMMIT Architecture (Checkpoint E Scaffold)

This document describes the intended trust boundaries while Checkpoint A is still
under evaluation. It is architecture evidence, not evidence that any later
checkpoint has passed.

## Safety thesis

ECOCOMMIT separates interpretation from authority:

> A probabilistic model may propose a contract. Only deterministic policy, fresh
> authoritative evidence, and a transaction-bound authorization may increase
> irreversible economic exposure.

The system fails closed. Missing, ambiguous, stale, conflicting, unregistered, or
unverifiable inputs result in clarification, rejection, or no-op behavior. They do
not result in a smaller set of checks or a guessed payment amount.

## Trust boundaries

```text
Natural-language mandate
        |
        v
[Untrusted intent provider] --candidate--> [Contract + fidelity gate]
                                                |
                                                | validated candidate only
                                                v
                                     [Deterministic policy mapper]
                                                |
Registered authoritative evidence ------------>|
                                                v
                                      [Exposure calculation]
                                                |
                                                v
                                   [Progressive commitment state]
                                                |
                                                v
                             [Transaction-bound commit certificate]
                                                |
                              verified certificate + idempotency key
                                                v
                         [Payment adapter: simulated or test-mode only]

Every boundary emits a correlated, tamper-evident audit event. Observability may
describe decisions, but it never grants authority.
```

## Components and responsibilities

| Component | May do | Must never do |
|---|---|---|
| Intent provider | Propose structured economic meaning | Grant payment authority |
| Fidelity gate | Validate structure, grounding, and abstention requirements | Repair material authority by guessing |
| Policy mapper | Map validated clauses to a closed policy-class vocabulary | Execute free-form model instructions |
| Evidence registry | Resolve registered sources, versions, freshness, and scope | Treat arbitrary payloads as authoritative |
| Exposure policy | Compute permitted exposure from policy and evidence | Accept a model-selected exposure ceiling |
| Commitment engine | Enforce legal state transitions | Skip stages or move backward implicitly |
| Commit certificate | Bind contract, evidence, merchant, amount, currency, transaction, and expiry | Authorize a changed or replayed transaction |
| Payment adapter | Simulate locally or call an explicitly configured test-mode provider | Present simulation as real or use live money by default |
| Audit/observability | Record correlation, decisions, denials, and operational signals | Change decisions or hide gate status |
| Benchmark harness | Compare frozen scenarios and deterministic baselines | Publish preliminary runs as final evidence |

## Repository map

| Area | Current implementation |
|---|---|
| A contract boundary | `contracts.py`, `interpreter.py`, `validator.py`, `evaluation.py` |
| A-to-B admission | `checkpoint_b_integration.py` recomputes the current A fidelity report and keeps B locked unless the A gate is accepted |
| B deterministic safety | `policy.py`, `evidence.py`, `exposure.py`, `certificates.py`, `commitment.py`, `idempotency.py`, `payments.py`, `reconciliation.py` |
| C preliminary evaluation | `checkpoint_c_models.py`, `checkpoint_c_baselines.py`, `checkpoint_c_metrics.py`, `checkpoint_c_runner.py` |
| D product/operations boundary | `checkpoint_status.py`, `audit.py`, `observability.py`, `service.py`, `api.py`, `checkpoint_d_workflow.py`, `demo_server.py`, and `ui/` |
| E evidence discipline | This document, `THREAT_MODEL.md`, and `REPRODUCIBILITY.md` |

The A-to-B authorization boundary is wired and adversarially tested locally, but
the actual incomplete A gate releases no obligations or certificate. Checkpoint D
now exercises that boundary through fixed synthetic local scenarios only. D's
real commit endpoint still always denies, and the only payment adapter is the
explicit `SIMULATED_LOCAL` adapter. Synthetic fixture success is never loaded as
authoritative checkpoint evidence.

## Invariants

1. **No probabilistic financial authority.** Model output is data. It cannot set
   exposure, waive evidence, select a payment mode, or advance a commitment.
2. **Evidence is scoped and fresh.** Source identity, subject, version, monotonic
   observation time, expiry, exact claim predicates, and content digest are
   checked at the decision boundary.
3. **Authorization is transaction-specific.** Certificates bind contract hash,
   evidence digests, policy version, merchant, transaction ID, amount, currency,
   allowed state, issue time, and expiry.
4. **TOCTOU changes deny.** Any bound-field change after authorization requires a
   new decision and certificate. The local capture boundary holds the evidence
   version lock from final verification through the simulated side effect.
5. **Transitions are explicit.** The implemented lifecycle is `PROPOSED ->
   AUTHORIZED -> RESERVED -> CAPTURE_ALLOWED -> CAPTURED`, with explicit
   `CANCELLED`, `FAILED`, `COMPENSATION_PENDING`, and `COMPENSATED` outcomes.
   Certificate expiry blocks capture; reversible-hold cleanup is recorded by the
   payment and reconciliation layers.
6. **At-most-once side effects.** Repeating the same idempotency key and identical
   request returns the recorded result. Reusing a key for a different request is
   rejected.
7. **Compensation is not erasure.** A reversal or release is a new auditable event;
   it never rewrites the original attempt. Capture-before-journal and
   refund-before-journal windows are reconciled into explicit transitions.
8. **Simulation is unmistakable.** Local runs and fixtures carry an explicit
   simulated mode marker in results, UI, audit records, and artifacts.
9. **Acceptance is gated.** Independent construction may proceed in parallel, but
   B, C, D, and E remain unpassed until their prerequisites and final integration
   gates pass.

## Modes

| Mode | External money movement | Intended use |
|---|---:|---|
| `SIMULATED` | None | Local development, adversarial tests, demo scaffolding |
| `REAL_PROVIDER_TEST` with provider status `RAZORPAY_TEST_MODE` | Test Mode only | Credentialed end-to-end integration evidence |
| `LIVE` | Disabled and out of current scope | No current code path should enable this |

A configuration string alone is not proof of provider mode. A future Razorpay
adapter must validate test credentials/account context, record provider response
identifiers, and fail closed when mode cannot be proven.

## Checkpoint dependencies

Implementation work is allowed before its prerequisite passes only when it can be
tested without trusting the prerequisite output.

| Checkpoint | Independent work allowed now | Acceptance still requires |
|---|---|---|
| B | Policy/evidence/exposure kernel, state machine, certificates, local adversarial tests | Checkpoint A pass, full A-to-B integration, credentialed Razorpay Test Mode tests when applicable |
| C | Harness, loss accounting, deterministic baselines, seeded preliminary runs | Frozen evaluation set/protocol and valid integrated system results |
| D | Locally validated API/UI/audit/observability and synthetic end-to-end workflow in default-deny simulated mode | Authoritative upstream evidence, real integrated product/provider tests, durable operations, and security/operational review |
| E | Architecture, threat model, runbooks, reproducibility scaffold | Reproduced end-to-end demo and complete evidence bundle |

## Current non-goals

- Production payment execution or live Razorpay credentials.
- Autonomous selection of evidence authorities.
- Treating the current benchmark scaffold as the final held-out benchmark.
- Declaring any checkpoint passed from unit tests alone.
- Weakening Checkpoint A's frozen thresholds to unblock later work.

# ECOCOMMIT — Razorpay AI Buildathon Submission

## Selected track

**Track 1 — AI Growth & Agentic Commerce.** ECOCOMMIT makes an AI buyer or
operator transactable without giving a probabilistic model direct financial
authority. This matches the track's published bar: every money action should be
explainable, bounded and gated, with an audit trail and graceful failure
handling. Source: [Razorpay AI Buildathon](https://razorpay.com/buildathon/).

## The problem that matters

AI agents can turn natural language into plausible actions, but a plausible
interpretation is not authorization to pay, buy, book, hire, renew, release or
transfer. A hallucinated amount, missed condition, stale approval or replayed
request can become an irreversible financial loss when an LLM is connected
directly to a payment API.

ECOCOMMIT treats this as an **economic-authority problem**, not merely a prompt
quality problem. It inserts a deterministic control plane between AI
interpretation and a Razorpay Test Mode or simulated transaction boundary.

## What was built

```text
User instruction
  -> source-grounded AI fact extraction
  -> typed relation classification
  -> deterministic IDs and Boolean/dependency AST
  -> conservation and ambiguity checks
  -> canonical economic contract
  -> registered evidence and exposure policy
  -> transaction-bound certificate
  -> guarded payment lifecycle
  -> reconciliation, compensation and audit trail
```

The runnable local console demonstrates three end-to-end outcomes:

| Scenario | Expected outcome | Safety property demonstrated |
|---|---|---|
| `HAPPY_PATH` | `SIMULATED_CAPTURED` | Valid authority and amount within cap can progress through the legal state machine |
| `CHECKPOINT_A_BLOCKED` | `SIMULATED_BLOCKED` | A valid-looking contract cannot execute without authoritative upstream evidence |
| `CAPTURE_FAILURE` | `SIMULATED_FAILED_CLOSED` | Capture failure records the failure, captures zero and voids the reversible hold |

The console is intentionally labelled **SIMULATION MODE — NO PROVIDER CALLS ·
NO MONEY MOVEMENT**. It proves runnable integration and fail-closed behavior; it
is not represented as an authoritative Checkpoint A–E PASS.

## Architecture and trust boundary

| Layer | Uses AI? | Authority |
|---|---:|---|
| Fact and relation extraction | Yes | Proposes source-grounded meaning only |
| Typed IR/AST and conservation | No | Rejects dangling, contradictory or dropped material meaning |
| Policy, evidence and exposure | No | Computes permission and caps from trusted configuration/evidence |
| Commitment state machine | No | Enforces legal transitions and idempotency |
| Certificate and transaction binding | No | Prevents replay and TOCTOU substitution |
| Razorpay adapter | No | Test Mode only; Live Mode is rejected |
| Reconciliation and audit | No | Preserves outcomes and compensation without granting authority |

**AI judgment:** AI is used where fuzzy language understanding is necessary.
It is deliberately not used for monetary limits, permission, evidence validity,
state transitions, cryptographic verification, reconciliation or recovery.
Unknown and materially ambiguous states fail closed.

Detailed component boundaries are in [Technical Overview](TECHNICAL_OVERVIEW.md),
[Architecture](ARCHITECTURE.md) and [Threat Model](THREAT_MODEL.md).

## Build quality and why it is trustworthy

- Python 3.11+ package with hash-locked development dependencies.
- Deterministic validators, compiler, state machine and receipt loaders.
- Exact-source CI and digest bindings for datasets, evaluators and evidence.
- Explicit idempotency, replay protection and TOCTOU checks.
- SQLite-backed single-host persistence and typed restart recovery.
- HMAC-verified webhook boundary and Test-only Razorpay enforcement.
- Provenance is created before order creation; missing receipts never unlock a
  downstream checkpoint.
- Simulation, provider deferral, semantic failure and authoritative PASS are
  represented as different states.

Quick verification:

```bash
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m pytest -p no:cacheprovider
python scripts/checkpoint_d_server.py --port 8765
```

Open `http://127.0.0.1:8765/` and follow the
[five-minute demo runbook](DEMO_RUNBOOK.md).

## Failure recovery: what broke and how we got out

1. Candidate 7 initially received HTTP 429 before producing semantic output.
   Sanitized Groq logs identified the real dimension: a 1,424-token requested
   output ceiling exceeded the free-tier 1,000 OTPM limit. The team did not
   rotate keys or retry until lucky; it preregistered a 900-token infrastructure
   amendment.
2. With the provider blocker removed, Candidate 7 completed and exposed a real
   semantic failure: D003 scored 0/5 while D009 scored 5/5. Candidate 7 was
   frozen as **FAILED** rather than rewritten after qualification.
3. Candidate 8 was opened under a separate visible-development protocol. Its
   visible results improved from 6/24 (25%), to 18/24 (75%), to 23/24 (95.83%).
   Iteration 3 met all percentage thresholds but remained `passed: false`
   because C8D020 dropped one guard and was rejected fail-closed.
4. Sealed preflight, formal Candidate-8 qualification and official Checkpoint A
   remain locked. This preserves evidence integrity instead of converting a
   near-pass into a claim.

See [Failure Recovery](FAILURE_RECOVERY.md) for exact runs, sources and artifact
digests.

## Current evidence truth

| Gate | Truthful state |
|---|---|
| Runnable deterministic product | **LOCALLY VALIDATED** |
| Candidate 7 | **FAILED** |
| Candidate 8 visible development | **23/24; NOT READY because one dropped guard remains** |
| Candidate 8 sealed preflight / qualification | **NOT RUN** |
| Checkpoint A | **BLOCKED / NOT PASSED** |
| Checkpoint B | **IMPLEMENTED AND LOCALLY VALIDATED / FINAL EXECUTION BLOCKED** |
| Checkpoint C | **IMPLEMENTED AND LOCALLY VALIDATED / FINAL EXPERIMENT BLOCKED** |
| Checkpoint D | **LOCAL PRODUCT RUNNABLE / AUTHORITATIVE PROOF BLOCKED** |
| Checkpoint E | **SUBMISSION PACKAGE READY / FINAL GATED EVIDENCE BLOCKED** |

The machine-readable artifact, not a green workflow badge, decides semantic
status. Full evidence references are indexed in
[Submission Evidence](SUBMISSION_EVIDENCE.md) and [Submission Status](../SUBMISSION_STATUS.md).

## Five-minute judge path

1. State the problem and the AI/deterministic trust boundary.
2. Run `HAPPY_PATH` and show cap, state transitions and correlation ID.
3. Run `CHECKPOINT_A_BLOCKED` and show zero authorization/capture.
4. Run `CAPTURE_FAILURE` and show zero capture plus hold cleanup.
5. Show the architecture, deterministic tests and failure chronology.
6. End with the current limitations: simulation is not real money movement and
   Candidate 8/formal A–E evidence remains pending.

## Security and limitations

- Razorpay **Test Mode only**; Live Mode and real financial data are prohibited.
- The local console makes no provider or payment call.
- The bundled deployment templates are not evidence of a hosted production
  service, high availability or managed key custody.
- Final checkpoint status requires typed, source-bound receipts and retained
  artifacts; screenshots and prose cannot promote a gate.
- Candidate 8's remaining visible guard defect must be corrected and pass its
  preregistered sequence before official A can begin.

## Repository map

| Path | Purpose |
|---|---|
| `src/ecocommit/` | Semantic IR, deterministic validation, compilation, policy, transaction and evidence logic |
| `tests/` | Regression, security, property/metamorphic and workflow tests |
| `data/` | Frozen evaluation inputs and isolated candidate-development partitions |
| `scripts/` | Qualification, checkpoint, demo and reproducibility tooling |
| `ui/` | Integrated local safety console |
| `evidence/` | Retained machine-readable evidence and failure records |
| `docs/` | Architecture, threat model, runbooks, chronology and submission manifest |

## License

Apache License 2.0. See [`LICENSE`](../LICENSE).

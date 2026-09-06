# ECOCOMMIT Technical Overview

## Problem

AI agents can translate natural language into actions, but economic commitments
are unusually costly to get wrong. A fluent model response is not sufficient
authority to pay, buy, book, hire, renew, release, transfer or cancel. ECOCOMMIT
adds a verifiable control plane between semantic interpretation and irreversible
execution.

## Design rule

The model proposes meaning; deterministic code decides authority.

| Layer | Responsibility | Authority boundary |
|---|---|---|
| Semantic parser | Extract source-grounded facts and classify relations | Cannot execute or grant permission |
| Typed IR/AST | Represent objects, counterparties, constraints, guards, Boolean structure and dependencies | Rejects missing/dangling/contradictory structure |
| Conservation and static validation | Prove material source facts survive compilation | Fails closed on dropped guards, exceptions or unknown authorization |
| Contract compiler | Produce a canonical economic contract | Uses explicit grounded facts only |
| Evidence and exposure policy | Verify registered evidence and compute configured caps | Ignores caller/model-supplied authority claims |
| Commitment engine | Enforce legal state transitions | Cannot skip authorization/reservation/capture gates |
| Certificate boundary | Bind contract, evidence, amount, merchant, transaction, time and nonce | Rejects replay and TOCTOU changes |
| Payment adapter | Simulate locally or use Razorpay Test Mode | Live Mode and real financial data are prohibited |
| Reconciliation and audit | Preserve outcomes, webhook identity, compensation and correlation | Records history; never changes authority |

## Candidate-8 semantic path

Candidate 8 is developed on a separate branch and remains gated until its
qualification passes:

1. Pass 1 extracts a flat, source-grounded fact inventory.
2. Fact IDs are assigned deterministically.
3. Pass 2 classifies typed action/entity and non-entity relations.
4. Source-only normalization reconstructs grammatical roles, Boolean guards,
   dependencies, quantities and explicit irrelevance.
5. A deterministic typed AST verifies relation and fact conservation.
6. The existing compiler and safety pipeline produce or reject the contract.

Model output is schema checked and grounded. Invalid relation proposals may fall
back only to the deterministic source grammar; material uncertainty does not fall
back to authorization.

## Runtime paths

- `POST /v1/commit/simulate` runs one fixed synthetic scenario and ignores
  caller-supplied authority fields.
- `POST /v1/commit` denies by default. The prepared Test path requires pinned
  A/B/C evidence, an environment-only token and a startup-bound operation.
- `POST /v1/razorpay/webhook` verifies raw HMAC, event identity and transaction
  binding when explicitly configured.
- `GET /v1/status` reports receipt-derived gate truth; file presence alone is
  never a PASS.

## Build-quality properties

- Hash-locked development dependencies and deterministic tests.
- Exact-source CI and source/evaluator/dataset bindings.
- Explicit idempotency, replay protection and TOCTOU checks.
- SQLite durable state with typed restart recovery for the single-host path.
- Test-only payment enforcement and provenance-before-order sequencing.
- Typed, digest-bound receipts with downstream prerequisite validation.
- Fail-closed UI and API behavior when authoritative evidence is absent.

## Honest limitations

The local console is a simulation, not proof of real money movement. Razorpay is
restricted to Test Mode. The bundled server/deployment templates are not a claim
of high availability, managed key custody or public production operations.
Checkpoint status is authoritative only when the required source-bound receipt
and artifact chain validates.

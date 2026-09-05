# ECOCOMMIT

**Evidence-calibrated safety controls for AI agents that can create irreversible economic commitments.**

**Razorpay AI Buildathon:** Track 1 — AI Growth & Agentic Commerce. Start with
the concise [judge-facing submission](docs/BUILDATHON_SUBMISSION.md), then run
the [five-minute demonstration](docs/DEMO_RUNBOOK.md).

## Why ECOCOMMIT

ECOCOMMIT sits between an AI agent and an economic action such as buying, paying, booking, hiring, transferring, renewing, reserving, releasing, cancelling, or committing. The language model may interpret semantics, but it does **not** own economic authority. Deterministic code owns validation, Boolean authorization logic, normalization, dependency handling, ambiguity blocking, semantic conservation, transaction eligibility, evidence, and execution permission.

The core principle is simple: **LLM for semantic interpretation; deterministic controls for economic authority.** Unknown or materially ambiguous authorization state fails closed. A missing or invalid receipt never unlocks a downstream checkpoint.

## What a reviewer can verify in five minutes

1. Clone the repository and install the hash-locked dependencies.
2. Run the deterministic test suite.
3. Start the local safety console.
4. Exercise a successful simulation, an upstream-gate denial, and an injected capture failure.
5. Inspect the correlation ID, state transitions, cleanup result, and blocked A–E evidence cards.

The demo is deliberately safe: it performs **no provider call and no money movement**. It proves that the product runs and that missing authority fails closed; it is not presented as an authoritative A/B/C/D/E PASS.

## Architecture

The implemented boundary is:

`instruction → untrusted semantic proposal → grounded typed facts/relations → deterministic Boolean and dependency AST → conservation/static validation → economic contract → evidence and exposure policy → transaction-bound certificate → guarded Test/simulated execution → reconciliation and audit`

The model may identify meaning. It cannot grant economic authority, choose a policy ceiling, bypass evidence, advance transaction state, or turn an unknown condition into permission. See [Technical Overview](docs/TECHNICAL_OVERVIEW.md) for the component and data-flow description.

The repository is organized around that boundary:

- `src/ecocommit/` — protocol implementation, Semantic IR, validation, compilation, conservation, execution and evidence logic.
- `tests/` — deterministic regression, property/metamorphic, security, workflow and qualification tests.
- `data/` — frozen evaluation inputs and versioned candidate-development partitions.
- `scripts/` — qualification, checkpoint, reproducibility and evidence tooling.
- `ui/` — integrated safety-console demonstration.
- `docs/ARCHITECTURE.md` and `docs/THREAT_MODEL.md` — architecture and trust/safety boundaries.

## Checkpoint truth

Checkpoint status is determined only by typed receipts, frozen protocols, exact-source workflow evidence and retained artifacts. A green CI job is not by itself a benchmark PASS. Provider failures such as HTTP 429/timeouts/5xx remain infrastructure evidence and are not silently converted into semantic success or failure.

Candidate history remains visible and immutable. The latest branch result is not rewritten into a PASS merely because its workflow is green:

- Candidate 1 — **FAILED**
- Candidate 3 — **FAILED**
- Candidate 4 — **PREREGISTERED / SUPERSEDED / NEVER RUN**
- Candidate 5 — **FAILED**
- Candidate 6 — **SUPERSEDED after bounded development**
- Candidate 7 — **FAILED** after the provider-limit remediation exposed a repeatable D003 semantic error
- Candidate 8 — **ITERATIVE VISIBLE DEVELOPMENT** on PR #7; iteration 3 reached
  23/24 (95.83%) with 100% selective reliability, 79.17% autonomous coverage
  and 100% clarification accuracy, but remains `passed: false` because one guard
  was dropped in C8D020. Qualification and official A remain locked.

Before any candidate can open a sealed preflight or qualification, it must be frozen and bound by SHA-256 evidence covering its parser prompts, schemas, deterministic normalizer/compiler, conservation checker, provider policy, datasets, evaluator and protocol.

The one-shot internal holdout requires all gates simultaneously:

| Gate | Requirement |
| --- | ---: |
| Case pass rate | ≥ 95% |
| Selective semantic reliability | ≥ 97% |
| Autonomous coverage | ≥ 60% |
| Ambiguous clarification accuracy | ≥ 90% |
| Fail-open errors | 0 |
| Dropped guards | 0 |
| Dropped exceptions | 0 |
| Semantic-conservation failures | 0 |
| UNKNOWN → authorized | 0 |

Only an internal qualification PASS can unlock the official frozen Checkpoint-A run. Official A remains one-shot with case pass ≥ 90%, selective reliability ≥ 95%, autonomous coverage ≥ 55%, and ambiguous clarification accuracy ≥ 80%.

## Quick start

Requires Python 3.11+.

```bash
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m pip check
python -m pytest -p no:cacheprovider
python -m compileall -q src scripts tests
node --check ui/app.js
```

Follow `docs/REPRODUCIBILITY.md` for the clean-machine procedure, source/evidence binding and artifact expectations.

## Local safety-console demo

The `ui/` application demonstrates the economic-control boundary without weakening qualification gates. Use the exact [five-minute demo runbook](docs/DEMO_RUNBOOK.md). Demo output is not treated as benchmark evidence unless a checkpoint protocol explicitly binds it.

## Failure recovery

The failure trail is part of the work, not hidden history. Candidate 7 first hit a Groq output-token-per-minute rejection because the request ceiling exceeded the free-tier OTPM limit. Reducing the bound ceiling to 900 removed the infrastructure failure and exposed the real semantic defect: D003 failed 5/5 while D009 passed 5/5. Candidate 7 was frozen as failed rather than retried until lucky. Candidate 8 then moved into a separate, visible-data-only development protocol. Its three visible iterations improved from 25%, to 75%, to 95.83%. Iteration 3 still failed the safety gate because C8D020 dropped one guard; the rejection remained fail-closed. See [Failure Recovery](docs/FAILURE_RECOVERY.md) for the evidence-linked chronology and engineering lessons.

## Evidence and reports

Key evidence documents are:

- `docs/BUILDATHON_SUBMISSION.md` — Track-1 fit and direct judge rubric mapping.
- `docs/SUBMISSION_EVIDENCE.md` — authoritative evidence index and checkpoint status.
- `docs/REPRODUCIBILITY.md` — exact-source reproduction instructions.
- `docs/ARCHITECTURE.md` — system architecture.
- `docs/TECHNICAL_OVERVIEW.md` — concise implementation and trust-boundary description.
- `docs/FAILURE_RECOVERY.md` — provider, semantic and development-failure chronology.
- `docs/THREAT_MODEL.md` — threat and safety model.
- `docs/DEPLOYMENT_READINESS.md` — deployment/readiness constraints.
- `docs/ENGINEERING_LOG.md` — engineering chronology.

Machine-verifiable receipts and GitHub Actions artifacts remain authoritative over narrative summaries.

## Submission evidence status

The repository intentionally does **not** claim that every checkpoint is green. Final A/B/C/D/E status must be read from the latest committed receipts and `docs/SUBMISSION_EVIDENCE.md`. Frozen failures and blocked gates remain visible rather than being rewritten.

The unattended Candidate-6 supervisor is designed to fail closed: it may advance only when machine-verifiable prerequisite evidence proves eligibility, and it cannot turn missing, invalid, failed, blocked or incomplete evidence into a PASS.

## Safety and limitations

ECOCOMMIT is designed to refuse unsupported economic authority rather than guess. Qualification thresholds are not lowered to improve presentation results, and frozen benchmark/evaluator data are not altered after results are observed.

Payment lifecycle demonstrations use **Razorpay TEST MODE only**. Provenance must exist before test transaction creation. Qualification must never use Razorpay Live Mode, real money, or real bank/card/UPI information. Human-only login, OTP, secret-entry or sandbox interactions remain human boundaries rather than automation targets.

## License

Apache-2.0. See `LICENSE` and `docs/LICENSE_DECISION.md`.

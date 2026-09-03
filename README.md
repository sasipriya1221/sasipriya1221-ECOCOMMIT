# ECOCOMMIT

**Evidence-calibrated safety controls for AI agents that can create irreversible economic commitments.**

## Why ECOCOMMIT

ECOCOMMIT sits between an AI agent and an economic action such as buying, paying, booking, hiring, transferring, renewing, reserving, releasing, cancelling, or committing. The language model may interpret semantics, but it does **not** own economic authority. Deterministic code owns validation, Boolean authorization logic, normalization, dependency handling, ambiguity blocking, semantic conservation, transaction eligibility, evidence, and execution permission.

The core principle is simple: **LLM for semantic interpretation; deterministic controls for economic authority.** Unknown or materially ambiguous authorization state fails closed. A missing or invalid receipt never unlocks a downstream checkpoint.

## Architecture

Candidate 6 follows this boundary:

`user instruction → semantic parser → typed Semantic IR → Boolean guard AST → static validation → deterministic normalization → deterministic ECOCOMMIT compiler → semantic-conservation verification → contract validator/evaluator → execution gates`

The repository is organized around that boundary:

- `src/ecocommit/` — protocol implementation, Semantic IR, validation, compilation, conservation, execution and evidence logic.
- `tests/` — deterministic regression, property/metamorphic, security, workflow and qualification tests.
- `data/` — evaluation inputs plus Candidate-6 development and sealed-holdout material.
- `scripts/` — qualification, checkpoint, reproducibility and evidence tooling.
- `ui/` — integrated safety-console demonstration.
- `docs/ARCHITECTURE.md` and `docs/THREAT_MODEL.md` — architecture and trust/safety boundaries.

## Checkpoint truth

Checkpoint status is determined only by typed receipts, frozen protocols, exact-source workflow evidence and retained artifacts. A green CI job is not by itself a benchmark PASS. Provider failures such as HTTP 429/timeouts/5xx remain infrastructure evidence and are not silently converted into semantic success or failure.

Candidate history remains visible and immutable:

- Candidate 1 — **FAILED**
- Candidate 3 — **FAILED**
- Candidate 4 — **PREREGISTERED / SUPERSEDED / NEVER RUN**
- Candidate 5 — **FAILED**
- Candidate 6 — final serious attempt; final status is determined only by legitimate qualification evidence

Before Candidate 6 can open its sealed internal holdout, it must be frozen and bound by SHA-256 evidence covering the Semantic IR schema, parser prompt, Boolean semantics, validator, normalizer, compiler, conservation checker, provider policy, development suite, sealed holdout suite/gold, evaluator and protocol.

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

Only an internal qualification PASS can unlock Candidate-6's official frozen Checkpoint-A run. Official A remains one-shot with case pass ≥ 90%, selective reliability ≥ 95%, autonomous coverage ≥ 55%, and ambiguous clarification accuracy ≥ 80%.

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

The `ui/` application demonstrates the economic-control boundary without weakening qualification gates. Use `docs/DEMO_RUNBOOK.md` for the intended walkthrough and `docs/PITCH_OUTLINE.md` for a concise presentation sequence. Demo output is not treated as benchmark evidence unless a checkpoint protocol explicitly binds it.

## Evidence and reports

Key evidence documents are:

- `docs/SUBMISSION_EVIDENCE.md` — authoritative evidence index and checkpoint status.
- `docs/REPRODUCIBILITY.md` — exact-source reproduction instructions.
- `docs/ARCHITECTURE.md` — system architecture.
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

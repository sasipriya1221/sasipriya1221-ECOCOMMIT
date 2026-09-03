# ECOCOMMIT

**Evidence-calibrated safety controls for AI agents that can create irreversible economic commitments.**

ECOCOMMIT sits between an AI agent and an economic action such as buying, paying, booking, hiring, transferring, renewing, reserving, releasing, cancelling, or committing. The language model may interpret semantics, but it does **not** own economic authority. Deterministic code owns validation, Boolean authorization logic, normalization, dependency handling, ambiguity blocking, semantic conservation, transaction eligibility, evidence, and execution permission.

## Core safety principle

> **LLM for semantic interpretation; deterministic controls for economic authority.**

The Candidate-6 architecture is:

`user instruction → semantic parser → typed Semantic IR → Boolean guard AST → static validation → deterministic normalization → deterministic ECOCOMMIT compiler → semantic-conservation verification → contract validator/evaluator → execution gates`

Unknown or materially ambiguous authorization state fails closed. A missing or invalid receipt never unlocks a downstream checkpoint.

## Repository map

- `src/ecocommit/` — protocol implementation, Semantic IR, validation, compilation, conservation, execution and evidence logic.
- `tests/` — deterministic regression, property/metamorphic, security, workflow and qualification tests.
- `data/` — frozen/public evaluation inputs and Candidate-6 development/holdout material.
- `scripts/` — qualification, checkpoint, reproducibility and evidence tooling.
- `ui/` — integrated product demonstration UI.
- `docs/ARCHITECTURE.md` — system architecture and trust boundaries.
- `docs/THREAT_MODEL.md` — safety/security model.
- `docs/REPRODUCIBILITY.md` — exact-source reproduction instructions.
- `docs/SUBMISSION_EVIDENCE.md` — authoritative evidence index and checkpoint status.
- `docs/DEMO_RUNBOOK.md` — demo execution procedure.
- `docs/PITCH_OUTLINE.md` — concise project presentation structure.

## Evidence discipline

Checkpoint status is determined only by the repository's typed receipts, frozen protocols, exact-source workflow evidence and retained artifacts. A green CI job is not by itself a benchmark PASS. Provider failures such as HTTP 429/timeouts/5xx are preserved as infrastructure evidence and are not silently converted into semantic success or failure.

Candidate history is intentionally retained:

- Candidate 1 — **FAILED**
- Candidate 3 — **FAILED**
- Candidate 4 — **PREREGISTERED / SUPERSEDED / NEVER RUN**
- Candidate 5 — **FAILED**
- Candidate 6 — final serious attempt; status is determined only by legitimate qualification evidence

For the latest authoritative state, use `docs/SUBMISSION_EVIDENCE.md` and committed evidence receipts rather than assuming all checkpoints are green.

## Candidate-6 qualification gates

Before the sealed internal holdout can run, Candidate 6 must be frozen and bound by SHA-256 evidence covering its semantic schema, parser prompt, Boolean semantics, validator, normalizer, compiler, conservation checker, provider policy, development suite, sealed holdout suite/gold, evaluator and protocol.

The sealed 60-case internal holdout is one-shot and requires all of the following simultaneously:

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

Only an internal qualification PASS may unlock Candidate-6's official frozen Checkpoint-A run. The official Checkpoint-A requirements remain: case pass ≥ 90%, selective reliability ≥ 95%, autonomous coverage ≥ 55%, ambiguous clarification accuracy ≥ 80%, with one official run and no resume-to-pass.

## Reproduce locally

Requires Python 3.11+.

```bash
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m pip check
python -m pytest -p no:cacheprovider
python -m compileall -q src scripts tests
node --check ui/app.js
```

For the independent clean-machine process and exact artifact expectations, follow `docs/REPRODUCIBILITY.md`.

## Economic execution safety

Payment lifecycle demonstrations use **Razorpay TEST MODE only**. Provenance must exist before test transaction creation. The project must never use real money, Razorpay Live Mode, or real bank/card/UPI information for qualification evidence.

## License

Apache-2.0. See `LICENSE` and `docs/LICENSE_DECISION.md`.

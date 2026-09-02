# ECOCOMMIT

**Evidence-Calibrated Economic Commitment Protocol for Autonomous Commerce**

> AI may propose economic meaning. Deterministic policy and authoritative evidence decide whether irreversible exposure can advance.

ECOCOMMIT is a research-grade Buildathon project for autonomous enterprise procurement. It turns natural-language mandates into provenance-preserving economic contracts, abstains on unresolved material ambiguity, and places a deterministic safety boundary between model output and payment commitment.

## Checkpoint truth

ECOCOMMIT separates **built**, **locally validated**, and **passed**. A component can be implemented and heavily tested without being promoted to an acceptance pass until its frozen, source-bound evidence exists.

| Checkpoint | Engineering state | Acceptance state |
|---|---|---|
| A — semantic/fidelity gate | Frozen candidate machinery built; Candidate 3 public run retained | **NOT PASSED** |
| B — deterministic economic safety | B1–B7 and B8 machinery built; pre-authorization provenance defect fixed | **BLOCKED / NOT PASSED** |
| C — comparative final benchmark | Final raw-row/preregistration runner built | **BLOCKED / NOT PASSED** |
| D — integrated product/deployment | API/UI/audit/deployment contracts built | **BLOCKED / NOT PASSED** |
| E — release/submission readiness | Public CI green; Apache-2.0 selected | **BLOCKED / NOT PASSED** |

### Checkpoint A

Candidate 1 is mathematically failed and Candidate 2 is not promotable. Candidate 3 preserves the frozen 80-case dataset, prompt, provider/model configuration, contract schema, semantic evaluator, and four thresholds while correcting only resumability/execution classification.

The latest retained Candidate 3 aggregate is artifact `9857872102`, `checkpoint-a-candidate-3-results-attempt-10`, from workflow run `33590028177` at source `fd26a52a21dc8431133c50be76d7d1ecaf0d099b`. GitHub publishes archive digest `sha256:917e74372b46f7727b565b335f4a6f23427b9f718d7948d137dcea8b304d900d`; the downloaded aggregate JSON independently hashes to `a5b807d02d69283e5e14c209661f8f2e4e027e0abe55e276e3d46032dcf0f723`.

That aggregate is still incomplete: **18 terminal rows, 12 passes, 6 failures, and 62 missing cases**. Its own `full_frozen_gate_run` flag is false, `gate_passed` is false, and no Checkpoint A receipt exists. Partial zero-valued aggregate metrics are not treated as final scores. No provider retry is authorized merely because the workflow is terminal; the retry policy still requires a fresh, digest-bound healthy-provider observation before another provider-consuming continuation.

### Checkpoint B / Razorpay Test Mode

`SIMULATED_LOCAL` remains the no-money backend. `RAZORPAY_TEST_MODE` sits behind the same deterministic boundary.

The earlier Razorpay Test order/Checkout authorization attempt from workflow run `33645687964` is retained as failed evidence but is permanently **non-promotable** because the required source/run/transaction-bound certificate/key reference did not exist before that order and authorization.

Public `main` at `36bd3b28cafcb915c41e07e792550e33fd0a54a1` fixed that defect by creating the provenance reference **before any provider order call** and added a secret-safe, GET-only authorization verifier. Exact-source Offline Regression run `33663013490` passed with **471/471 tests**. No fresh post-fix Test order, authorization, capture, refund, webhook, reconciliation, settlement, or real-money action is claimed. B8 and Checkpoint B therefore remain blocked/not passed.

## Why ECOCOMMIT

LLMs are useful interpreters but unsafe sources of financial authority. A fluent response can still omit a limit, invert an exception, use stale approval, or replay a transaction. ECOCOMMIT separates those concerns:

- probabilistic interpretation proposes a structured contract;
- fidelity validation checks grounding, material completeness, and ambiguity;
- a closed mapper turns validated clauses into known policy obligations;
- registered evidence and trusted policy calculate maximum exposure;
- progressive state and a transaction-bound certificate guard capture; and
- idempotency, reconciliation, compensation, audit, and observability make failures explicit.

The frozen scientific thesis and metrics are in [the hypothesis](spec/HYPOTHESIS.md) and [metric specification](spec/METRICS.md).

## Architecture

```text
Natural-language mandate
        |
        v
[Untrusted intent provider]
        |
        v
[Contract + fidelity/abstention gate]
        |
        v
[Closed policy mapping] <--- [Registered authoritative evidence]
        |
        v
[Deterministic exposure decision]
        |
        v
[Progressive commitment + bound certificate]
        |
        v
[SIMULATED_LOCAL | RAZORPAY_TEST_MODE behind the same boundary]
```

See [Architecture](docs/ARCHITECTURE.md) for the component map and trust boundaries and [Threat Model](docs/THREAT_MODEL.md) for the adversary/control matrix.

## Quick start

Requirements: Git and Python 3.11 or newer.

```powershell
git clone https://github.com/sasipriya1221/sasipriya1221-ECOCOMMIT.git
Set-Location sasipriya1221-ECOCOMMIT
python -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .test-tmp-readme
```

POSIX shells can replace `.venv\Scripts\python.exe` with `.venv/bin/python`. No network credential is needed for the deterministic suite. Do not place a provider key on a command line or in a tracked file.

## Local safety-console demo

Start the loopback-only UI/API:

```powershell
.venv\Scripts\python.exe scripts\checkpoint_d_server.py --port 8765
```

Open `http://127.0.0.1:8765/`. The default server deliberately loads no authoritative checkpoint evidence, so every gate remains blocked and the provider endpoint denies. Three fixed synthetic scenarios are available:

- `HAPPY_PATH` — composes local A-to-B/B interfaces and records a simulated capture;
- `CHECKPOINT_A_BLOCKED` — releases no obligations or payment authority; and
- `CAPTURE_FAILURE` — injects a failure, voids the simulated hold, and ends closed.

A JSON-only fallback is available:

```powershell
.venv\Scripts\python.exe scripts\checkpoint_d_demo.py --scenario HAPPY_PATH
```

These synthetic paths demonstrate the safety boundary; they are not Razorpay evidence or a checkpoint pass.

The separately configured Razorpay Test path becomes ready only with SHA-256-pinned, cross-linked A/B/C evidence, a pinned human Checkout operation, persistent state/audit paths, current Test credentials, environment-only API/certificate/webhook secrets, and the required pre-order provenance reference. HTTP callers select only an opaque prepared operation ID; they cannot submit contracts, payment data, callback authority, credentials, or keys.

## Evidence and reports

- [Progress / evidence board](PROGRESS.md)
- [Checkpoint A runbook](CHECKPOINT_A_RUNBOOK.md)
- [Checkpoint B validation](CHECKPOINT_B_VALIDATION.md)
- [Checkpoint C validation](CHECKPOINT_C_VALIDATION.md)
- [Checkpoint D validation](CHECKPOINT_D_VALIDATION.md)
- [Checkpoint E validation](CHECKPOINT_E_VALIDATION.md)
- [Reproducibility runbook](docs/REPRODUCIBILITY.md)
- [Hosted deployment readiness](docs/DEPLOYMENT_READINESS.md)
- [License decision](docs/LICENSE_DECISION.md)
- [Engineering failure/fix log](docs/ENGINEERING_LOG.md)
- [Submission evidence framework](docs/SUBMISSION_EVIDENCE.md)
- [Five-minute pitch outline](docs/PITCH_OUTLINE.md)

Run the structural readiness checker with:

```powershell
.venv\Scripts\python.exe scripts\checkpoint_e_readiness.py
```

Strict final validation uses `scripts/checkpoint_e_readiness.py --mode final --independent-reproduction <receipt>` only after real final evidence is installed.

## Submission evidence status

The final evidence slots remain deliberately blocked until real, source-bound proof exists:

- complete Checkpoint A final metrics and typed receipt — **BLOCKED**;
- complete fresh post-fix Razorpay Test lifecycle — **BLOCKED**;
- final ECOCOMMIT-versus-baseline one-shot comparison — **BLOCKED**;
- integrated hosted TLS/product evidence — **BLOCKED**;
- independent clean-machine reproduction — **BLOCKED**;
- final screenshots — **BLOCKED**; and
- final five-minute demo video — **BLOCKED**.

Do not replace those slots with smoke results, fixtures, mocked output, preliminary benchmark numbers, or the non-promotable historical Razorpay authorization.

## Repository map

| Path | Purpose |
|---|---|
| `src/ecocommit/` | Intent, fidelity, policy/evidence/exposure, commitment/payment/webhook execution, benchmark, and product boundaries |
| `tests/` | Deterministic regressions and synthetic fixtures |
| `scripts/` | Live A/B tooling, evidence export, benchmark runner, demo/server, and readiness checks |
| `spec/` | Frozen scope, hypothesis, metrics, and evaluation protocol |
| `docs/` | Architecture, threat model, reproducibility, engineering log, demo, pitch, and evidence framework |
| `deploy/` | Provider-neutral single-host WSGI/TLS/reverse-proxy templates; not a deployed service |
| `.github/workflows/` | Offline CI plus manual-only credentialed workflows |

## Safety and limitations

- Checkpoint A has not passed; incomplete provider evidence is never promoted.
- B/C/D local validation does not clear their dependency/final-integration gates.
- `SIMULATED_LOCAL` moves no real money.
- Razorpay integration is **Test Mode only**. The old authorization remains non-promotable and no fresh post-fix lifecycle is claimed.
- SQLite WAL/FULL-sync state and cross-process audit locking are single-host durability features, not HA, KMS, malicious-storage integrity, or backup/restore claims.
- The checked-in C development material is not a final economic comparison.
- No formal security audit, accessibility certification, hosted SLO evidence, or independent clean-machine reproduction is claimed.

## License

ECOCOMMIT is released under the **Apache License, Version 2.0**. See [LICENSE](LICENSE) and the recorded [license decision](docs/LICENSE_DECISION.md). The license does not change any payment, security, or checkpoint acceptance claim; those remain governed by the evidence gates above.

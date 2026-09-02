# ECOCOMMIT

**Evidence-Calibrated Economic Commitment Protocol for Autonomous Commerce**

> AI may propose economic meaning. Deterministic policy and authoritative
> evidence decide whether irreversible exposure can advance.

ECOCOMMIT is a research-grade Buildathon project for autonomous enterprise
procurement. It turns natural-language mandates into provenance-preserving
economic contracts, abstains on unresolved material ambiguity, and places a
deterministic safety boundary between model output and payment commitment.

Payment behavior is explicit: **`SIMULATED_LOCAL`** remains the local/test
backend, and a separate **`RAZORPAY_TEST_MODE`** adapter sits behind the same
safety boundary. The earlier Razorpay Test order/Checkout authorization attempt
from workflow run `33645687964` is retained as failed evidence but is
**non-promotable** because the required source/run/transaction-bound
certificate/key reference did not exist before that order and authorization.
Public `main` at `36bd3b28cafcb915c41e07e792550e33fd0a54a1` fixes that defect by
creating the provenance reference before any provider order call and adds a
secret-safe, GET-only authorization verifier. Offline Regression run
`33663013490` passed that exact source with **471/471 tests**. No fresh Test
order, authorization, capture, refund, webhook, settlement, or real-money action
has been performed after the fix, so B8 and Checkpoint B remain blocked/not
passed.

Checkpoint A remains not passed. Candidate 1 is mathematically failed. A later
remote score-recovery experiment at run `33556907712` ended cancelled after
seven transient provider deferrals and is not an eligible frozen candidate; its
automatic maximum-score filling was rejected rather than promoted. Candidate 2
then ran as `33583323178`, but the retained attempts remained incomplete and
exposed a general provider/correction resumability defect. Candidate 3 is the
runner-only correction. Its public run `33590028177` ultimately concluded with
failure after repeated attempts; the last retained promotable aggregate remains
incomplete, with one passing row, one failed row, 78 provider deferrals, and no
complete receipt. A workflow failure status alone does not substitute for the
missing evidence. No complete score or Checkpoint A pass is claimed, and another
provider retry is not justified until provider recovery from the pervasive HTTP
429 condition is objectively demonstrated.

## Why ECOCOMMIT

LLMs are useful interpreters but unsafe sources of financial authority. A fluent
answer can still omit a limit, invert an exception, use stale approval, or replay
a transaction. ECOCOMMIT separates those concerns:

- probabilistic interpretation proposes a structured contract;
- fidelity validation checks grounding, material completeness, and ambiguity;
- a closed mapper turns validated clauses into known policy obligations;
- registered evidence and trusted policy calculate maximum exposure;
- progressive state and a transaction-bound certificate guard capture; and
- idempotency, reconciliation, compensation, audit, and observability make
  failures explicit.

The frozen scientific thesis and metrics are in [the hypothesis](spec/HYPOTHESIS.md)
and [metric specification](spec/METRICS.md).

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

The full component map, trust boundaries, runtime modes, and acceptance
dependencies are in [Architecture](docs/ARCHITECTURE.md). The adversary/control
matrix is in [Threat Model](docs/THREAT_MODEL.md).

## Checkpoint truth

| Checkpoint | Engineering state | Acceptance state |
|---|---|---|
| A — offline specification/contracts | **BUILT + PASSED (offline scope)** | Frozen invariants retained |
| A — live intent/fidelity gate | **Candidate 1 failed; Candidate 2 incomplete; Candidate 3 run `33590028177` terminal/incomplete after provider deferrals** | **NOT PASSED** |
| B — deterministic economic safety | **BUILT + LOCALLY VALIDATED; pre-authorization provenance defect fixed on public `main`** | **BLOCKED / NOT PASSED** |
| C — comparative benchmark harness | **BUILT + LOCALLY VALIDATED** | **BLOCKED / NOT PASSED** |
| D — API/UI/audit/operations | **BUILT + LOCALLY VALIDATED** | **BLOCKED / NOT PASSED** |
| E — repository/submission evidence | **BUILT + LOCALLY VALIDATED; Apache-2.0 selected** | **BLOCKED / NOT PASSED** |

See [PROGRESS.md](PROGRESS.md) for the evidence board. These terms are not
interchangeable:

- **BUILT**: implementation or documentation exists;
- **LOCALLY VALIDATED**: deterministic local checks passed;
- **BLOCKED**: a required upstream, external, or final-run input is unavailable;
- **PASSED**: the complete frozen acceptance gate passed with retained evidence.

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

POSIX shells can replace `.venv\Scripts\python.exe` with `.venv/bin/python`.
The resolved dependency manifest is checked in as
[requirements-dev.lock](requirements-dev.lock); its limits are documented in
[Reproducibility](docs/REPRODUCIBILITY.md).

No network credential is needed for the deterministic suite. Do not place a
provider key on the command line or in a tracked file.

## Local safety-console demo

Start the loopback-only UI/API:

```powershell
.venv\Scripts\python.exe scripts\checkpoint_d_server.py --port 8765
```

Open `http://127.0.0.1:8765/`. The server deliberately loads no authoritative
checkpoint evidence, so every gate remains blocked and the provider endpoint
always denies. The UI exposes three fixed synthetic scenarios:

- `HAPPY_PATH` — composes the local A-to-B/B interfaces and records a simulated
  capture;
- `CHECKPOINT_A_BLOCKED` — releases no obligations or payment authority; and
- `CAPTURE_FAILURE` — injects a failure, voids the simulated hold, and ends
  closed.

The exact flow and expected screen states are in
[Demo Runbook](docs/DEMO_RUNBOOK.md). A JSON-only fallback is available:

```powershell
.venv\Scripts\python.exe scripts\checkpoint_d_demo.py --scenario HAPPY_PATH
```

Neither path is Razorpay evidence or a checkpoint pass.

The same server also contains a separately configured Razorpay **Test Mode**
path, but it is unavailable by default. It becomes ready only when the operator
supplies a SHA-256-pinned, cross-linked A/B/C evidence bundle; a separately
pinned human Checkout operation; persistent audit/state paths; current Test
credentials that pass a read-only preflight; an environment-only API bearer
token, certificate signing secret, and webhook secret. HTTP callers can then
select only the opaque prepared operation ID. They cannot submit contracts,
payment data, callbacks, evidence claims, credentials, or keys. See
[Reproducibility](docs/REPRODUCIBILITY.md) for the exact future-run procedure.
Evidence and all local configuration are validated before provider preflight;
pending refunds remain retryable through exact refund-ID polling. The current
public implementation also creates the source/run/transaction-bound
certificate-key reference before any provider order call. This implementation
and its fake-transport regressions are not live evidence.

## Evidence and reports

- [Checkpoint A runbook](CHECKPOINT_A_RUNBOOK.md)
- [Checkpoint B validation](CHECKPOINT_B_VALIDATION.md)
- [Checkpoint C validation](CHECKPOINT_C_VALIDATION.md)
- [Checkpoint D validation](CHECKPOINT_D_VALIDATION.md)
- [Checkpoint E validation](CHECKPOINT_E_VALIDATION.md)
- [Reproducibility runbook](docs/REPRODUCIBILITY.md)
- [Hosted deployment readiness](docs/DEPLOYMENT_READINESS.md)
- [Owner license decision brief](docs/LICENSE_DECISION.md)
- [Engineering failure/fix log](docs/ENGINEERING_LOG.md)
- [Submission evidence framework](docs/SUBMISSION_EVIDENCE.md)
- [Five-minute pitch outline](docs/PITCH_OUTLINE.md)

Run the repository-readiness checker with:

```powershell
.venv\Scripts\python.exe scripts\checkpoint_e_readiness.py
```

It returns a local structural verdict separately from final submission readiness.
Known evidence blockers remain blockers rather than making the checker green by
omission.

After real evidence is installed, strict final validation uses
`scripts/checkpoint_e_readiness.py --mode final --independent-reproduction <receipt>`.

## Submission evidence status

The final evidence slots remain deliberately blocked until real, source-bound
proof exists:

- complete Checkpoint A final metrics — **BLOCKED**;
- complete Razorpay Test Mode payment lifecycle — **BLOCKED** (the prior
  authorization attempt is retained but non-promotable; the provenance fix is
  public, and a fresh source-bound Test lifecycle has not yet run);
- final ECOCOMMIT-versus-baseline comparison — **BLOCKED**;
- integrated hosted product evidence — **BLOCKED**;
- final screenshots — **BLOCKED**; and
- final demo video — **BLOCKED**.

See [Submission Evidence](docs/SUBMISSION_EVIDENCE.md) for the promotion rule.
Do not replace these slots with smoke results, synthetic fixtures, local browser
captures, mocked provider output, or preliminary benchmark numbers.

## Repository map

| Path | Purpose |
|---|---|
| `src/ecocommit/` | Intent, fidelity, policy/evidence/exposure, durable commitment/payment/webhook execution, benchmark, and D product boundaries |
| `tests/` | Deterministic regressions and synthetic fixtures |
| `scripts/` | Live A/B tooling, webhook/evidence export, C runner, D demo/prepared Test server, and E readiness checks |
| `spec/` | Frozen scope, hypothesis, metrics, and evaluation protocol |
| `docs/` | Architecture, threat model, reproducibility, engineering log, demo, pitch, and evidence framework |
| `deploy/` | Provider-neutral single-host WSGI, TLS proxy, and environment templates; not a deployed service |
| `.github/workflows/` | Offline CI plus manual-only credentialed provider workflows |

## Safety and limitations

- The actual Checkpoint A live gate has not passed.
- B/C/D local success does not clear their dependency or final integration gates.
- `SIMULATED_LOCAL` moves no real money. Durable SQLite-backed simulation/Test
  state is available only when explicitly configured.
- The Razorpay adapter is Test Mode only. The earlier Test authorization is
  retained as non-promotable evidence because it predates the required
  certificate/key-reference provenance. No fresh post-fix authorization,
  capture, refund, webhook, reconciliation, or settlement evidence is claimed.
- SQLite WAL/FULL-sync state, cross-process idempotency, and OS-locked audit
  append are locally validated for one host. They are not high availability,
  a malicious-storage integrity boundary, backup/restore evidence, or a managed
  production database/queue claim.
- Local HMAC keys are test boundaries, not KMS or production key management.
- The checked-in C plan/suite is synthetic and preliminary, not a final economic
  comparison.
- No formal security audit, accessibility certification, hosted SLO evidence, or
  independent clean-machine reproduction is claimed.

## License

ECOCOMMIT is released under the **Apache License, Version 2.0**. See
[LICENSE](LICENSE) and the recorded [license decision](docs/LICENSE_DECISION.md).
Open-source licensing does not change any payment, security, or checkpoint
acceptance claim; those remain governed by the evidence gates above.

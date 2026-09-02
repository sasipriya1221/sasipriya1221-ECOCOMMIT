# ECOCOMMIT

**Evidence-Calibrated Economic Commitment Protocol for Autonomous Commerce**

> AI may propose economic meaning. Deterministic policy and authoritative
> evidence decide whether irreversible exposure can advance.

ECOCOMMIT is a research-grade Buildathon project for autonomous enterprise
procurement. It turns natural-language mandates into provenance-preserving
economic contracts, abstains on unresolved material ambiguity, and places a
deterministic safety boundary between model output and payment commitment.

Payment behavior is explicit: **`SIMULATED_LOCAL`** remains the local/test
backend, and a separate **`RAZORPAY_TEST_MODE`** adapter now sits behind the same
safety boundary. Redacted Actions evidence validates Test authentication and one
bound Test order, but no payment authorization, capture, refund, webhook, or
settlement ran. B8 and Checkpoint B therefore remain blocked/not passed; there is
no live-money path. A digest-bound Test Checkout handoff and capture/refund
continuation are implemented locally but have not been exercised against the
provider.

Checkpoint A remains not passed. Candidate 1 is mathematically failed. A later
remote score-recovery experiment at run `33556907712` ended cancelled after
seven transient provider deferrals and is not an eligible frozen candidate; its
automatic maximum-score filling was rejected rather than promoted. Candidate 2
then ran as `33583323178`, but two attempts remained incomplete and exposed a
general provider/correction resumability defect. Candidate 3 is the runner-only
correction; it is locally focused-tested and has not been pushed or evaluated.

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
| A — live intent/fidelity gate | **Candidate 1 failed; Candidate 2 incomplete; Candidate 3 runner correction locally focused-tested, not evaluated** | **NOT PASSED** |
| B — deterministic economic safety | **BUILT + LOCALLY VALIDATED** | **BLOCKED / NOT PASSED** |
| C — comparative benchmark harness | **BUILT + LOCALLY VALIDATED** | **BLOCKED / NOT PASSED** |
| D — API/UI/audit/operations | **BUILT + LOCALLY VALIDATED** | **BLOCKED / NOT PASSED** |
| E — repository/submission evidence | **BUILT + LOCALLY VALIDATED** | **BLOCKED / NOT PASSED** |

See [PROGRESS.md](PROGRESS.md) for the live evidence board. These terms are not
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
pending refunds remain retryable through exact refund-ID polling. This
implementation and its fake-transport regressions are not live evidence.

## Evidence and reports

- [Checkpoint A runbook](CHECKPOINT_A_RUNBOOK.md)
- [Checkpoint B validation](CHECKPOINT_B_VALIDATION.md)
- [Checkpoint C validation](CHECKPOINT_C_VALIDATION.md)
- [Checkpoint D validation](CHECKPOINT_D_VALIDATION.md)
- [Checkpoint E validation](CHECKPOINT_E_VALIDATION.md)
- [Reproducibility runbook](docs/REPRODUCIBILITY.md)
- [Engineering failure/fix log](docs/ENGINEERING_LOG.md)
- [Submission evidence framework](docs/SUBMISSION_EVIDENCE.md)
- [Five-minute pitch outline](docs/PITCH_OUTLINE.md)

Run the repository-readiness checker with:

```powershell
.venv\Scripts\python.exe scripts\checkpoint_e_readiness.py
```

It returns a local structural verdict separately from final submission readiness.
Known evidence and legal blockers remain blockers rather than making the checker
green by omission.

After real evidence is installed, strict final validation uses
`scripts/checkpoint_e_readiness.py --mode final --independent-reproduction <receipt>`.

## Submission evidence status

The final evidence slots are deliberately empty and blocked:

- complete Checkpoint A final metrics — **BLOCKED**;
- complete Razorpay Test Mode payment lifecycle — **BLOCKED** (authentication
  and order-level evidence retained; authorization/capture/webhooks not run);
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
| `.github/workflows/` | Offline CI plus manual-only credentialed provider workflows |

## Safety and limitations

- The actual Checkpoint A gate has not passed.
- B/C/D local success does not clear their dependency or final integration gates.
- `SIMULATED_LOCAL` moves no real money. Durable SQLite-backed simulation/Test
  state is available only when explicitly configured.
- The Razorpay adapter is Test Mode only. Retained evidence covers authentication
  and order binding/idempotency, not payment authorization, capture, refund,
  webhook delivery, reconciliation, or settlement.
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

No open-source license has been selected. Public visibility does not itself grant
reuse rights. The repository owner must choose and add an appropriate license
before claiming open-source/submission license readiness; this remains an explicit
Checkpoint E blocker.

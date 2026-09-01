# ECOCOMMIT Reproducibility Runbook

This runbook separates deterministic local engineering evidence from live-model,
provider Test Mode, and final submission evidence. Completing the local steps does
not pass Checkpoint A, B, C, D, or E.

## Reproduction levels

| Level | Meaning | Current state |
|---|---|---|
| Same working environment | Rerun from the existing virtual environment | Locally exercised |
| Clean local environment | Create a new virtual environment from the resolved manifest | Locally exercised during E validation when reported |
| Independent clean machine | Another machine/operator follows this runbook and retains results | **BLOCKED / not retained** |
| Live/provider reproduction | Uses approved secrets and retained real external evidence | **BLOCKED** |
| Final submission reproduction | Recreates the integrated evidence bundle at its immutable revision | **BLOCKED** |

## Prerequisites

- Git.
- Python 3.11 or newer.
- Network access to install packages unless dependencies are already cached.
- No provider credential for deterministic local tests.

## Clone and identify the source

```powershell
git clone https://github.com/sasipriya1221/sasipriya1221-ECOCOMMIT.git
Set-Location sasipriya1221-ECOCOMMIT
git rev-parse HEAD
git status --short
```

For retained evidence, check out the exact full commit SHA named by the relevant
validation report. Never infer a source revision from a downloaded artifact.
The repository forces LF checkout for byte-digested Checkpoint C protocol text
files through `.gitattributes`; do not override that attribute when reproducing
their registered SHA-256 values.

## Create the deterministic environment

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.venv\Scripts\python.exe -m pip install --no-deps -e .
.venv\Scripts\python.exe -m pip check
```

POSIX shell:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m pip check
```

`requirements-dev.lock` records the exact Python distributions used by the local
validation environment. It does not contain artifact hashes and does not pin the
isolated build bootstrap declared in `pyproject.toml`; therefore it is a resolved
validation manifest, not a fully offline/hermetic supply-chain lock.

If validating the broad supported dependency ranges instead, use
`python -m pip install -e ".[dev]"` and retain the complete resolved distribution
manifest. Do not compare results across environments without recording that
difference.

## Deterministic tests and checks

Windows:

```powershell
.venv\Scripts\python.exe -m compileall -q src scripts tests
.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .test-tmp-reproduction
.venv\Scripts\python.exe -m pip check
node --check ui\app.js
.venv\Scripts\python.exe scripts\checkpoint_e_readiness.py
git diff --check
git status --short
```

`node --check` is a syntax check; Node.js is not needed by the Python product or
test suite. If Node.js is unavailable, record that check as not run rather than
silently omitting it.

## Focused checkpoint commands

### Checkpoint B local boundary

Use the exact focused command in `CHECKPOINT_B_VALIDATION.md`. It exercises
policy, evidence, exposure, certificate, state, idempotency, reconciliation, and
compensation with `SIMULATED_LOCAL` only.

### Checkpoint C preliminary synthetic harness

```powershell
.venv\Scripts\python.exe scripts\checkpoint_c_benchmark.py `
  --plan tests\fixtures\checkpoint_c\frozen_plan.json `
  --suite tests\fixtures\checkpoint_c\frozen_suite.json `
  --output artifacts\checkpoint-c-preliminary.json `
  --code-revision (git rev-parse HEAD) `
  --working-tree-state clean
```

The output must remain `PRELIMINARY_NOT_FINAL` and synthetic. The command must not
be used to populate the final comparison slot.

### Checkpoint D JSON scenarios

```powershell
.venv\Scripts\python.exe scripts\checkpoint_d_demo.py --scenario HAPPY_PATH
.venv\Scripts\python.exe scripts\checkpoint_d_demo.py --scenario CHECKPOINT_A_BLOCKED
.venv\Scripts\python.exe scripts\checkpoint_d_demo.py --scenario CAPTURE_FAILURE
```

Every result must say `SIMULATED_LOCAL`, `counts_as_checkpoint_evidence: false`,
`real_provider_called: false`, and `real_money_moved: false`.

### Checkpoint D loopback product flow

```powershell
.venv\Scripts\python.exe scripts\checkpoint_d_server.py --port 8765
```

Follow `DEMO_RUNBOOK.md`. This uses a loopback development server and deliberately
blocked gate reports. It is not hosted or provider evidence.

## Checkpoint A live evidence

Follow `CHECKPOINT_A_RUNBOOK.md`. Do not start a competing run while the guarded
provider-deferred retry is active. A full gate requires all 80 immutable cases and
all four frozen thresholds passing together. Provider deferrals, smoke runs,
fixtures, partial aggregates, and schema failures cannot become a pass.

Never print or pass a provider key in a shell command that will be retained. Use
the approved CI secret boundary.

## Razorpay Test Mode evidence

Razorpay integration is not implemented. When the dedicated adapter and approved
test credentials exist:

1. prove the account/context is Test Mode before sending a request;
2. use unique transaction and idempotency identifiers;
3. retain redacted request digests, provider IDs, timestamps, webhooks, and
   reconciliation results;
4. exercise authorize/reserve/capture/release/refund, duplicate delivery,
   signature failure, timeout/ambiguous outcome, and compensation;
5. retain application denials and provider/transport failures; and
6. checksum the complete evidence bundle.

No simulation or mocked HTTP response counts as this evidence.

## Clean-environment verification protocol

For a retained clean-environment result:

1. start from a clean clone at an immutable SHA;
2. create a new virtual environment;
3. install from `requirements-dev.lock` and the local project;
4. record OS, Python, pip, and every installed distribution/version;
5. run compile, full tests, D scenarios, E readiness, diff, and status checks;
6. save stdout/stderr and exit codes without secrets;
7. record whether the tree stayed clean; and
8. checksum the retained logs and readiness report.

An independent reproduction must be performed by another machine/operator and
retain the same provenance. This has not happened yet.

## Evidence-bundle checklist

Every promoted artifact must retain:

- full source revision and clean/dirty state;
- checkpoint/prerequisite states plus evidence references;
- exact commands and configuration with secrets removed;
- OS, Python, resolved dependencies, and manifest digest;
- mode (`SIMULATED_LOCAL` or verified provider Test Mode);
- raw rows/results, including failures and missing data;
- metric/policy/schema/registry versions and digests;
- timestamps and latency method;
- provider IDs/webhooks/reconciliation when applicable;
- artifact SHA-256 digests; and
- limitations and non-claims.

The judge-facing blocked/filled slots and promotion rule are in
`SUBMISSION_EVIDENCE.md`.

## Gate vocabulary

- **BUILT** — implementation/documentation exists.
- **LOCALLY VALIDATED** — deterministic local checks passed.
- **BLOCKED** — a required upstream, external, legal, or final-run input is absent.
- **PASSED** — the complete frozen acceptance gate passed with retained evidence.

Never infer a later label from an earlier one.

# ECOCOMMIT Reproducibility Runbook (Checkpoint E Scaffold)

This runbook separates local deterministic evidence from live-provider evidence.
Completing the local steps does not pass Checkpoint A or any later checkpoint.

## Local deterministic environment

Requirements:

- Python 3.11 or newer.
- A clean checkout at a recorded commit SHA.
- Development dependencies installed from the repository metadata.

From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
```

The full local suite includes Checkpoint A regressions, the locally validated
Checkpoint B B1–B7 boundary, and the independent C/D scaffold tests. No network
credential is required for these tests. Any local payment behavior is simulated
and must remain labeled `SIMULATED_LOCAL`.

The focused B commands, tested commit, environment versions, gate matrix, and
known blockers are retained in `CHECKPOINT_B_VALIDATION.md`.

## Preliminary Checkpoint C runs

The benchmark runner must use an explicit seed, named baseline, complete scenario
manifest, and output path. Its artifact must include:

- `preliminary: true` (or equivalent non-final status);
- repository commit SHA and dirty-worktree flag;
- Python version plus a sorted manifest of every installed Python distribution
  and version (resolved-environment evidence, not a dependency lock);
- scenario-set identifier/digest and every scheduled scenario result;
- runner configuration, deterministic seed, and baseline version;
- metric definitions and raw loss components;
- failed/error cases rather than silently omitted rows.

Preliminary artifacts may exercise the harness. They must not be copied into a
judge-facing final comparison table.

## Checkpoint A live evidence

Follow `CHECKPOINT_A_RUNBOOK.md`. A full gate requires one real-model run satisfying
all frozen thresholds in the same run. Smoke runs, fixtures, partial shards without
a valid aggregate, and provider failures cannot be relabeled as a pass.

## Razorpay Test Mode evidence

Razorpay integration remains pending until test credentials and an adapter are
available. When added:

1. Obtain credentials through the approved secret channel; never commit or print
   them.
2. Prove the account/provider context is Test Mode before sending a request.
3. Use unique test transaction and idempotency identifiers.
4. Record redacted request digests, provider IDs, timestamps, webhook/reconciliation
   results, and commit-certificate verification.
5. Exercise authorize/reserve/capture/refund-or-release, duplicate delivery,
   timeout/reconciliation, invalid signature, and compensation paths.
6. Retain failures and distinguish application denial, provider rejection,
   transport failure, ambiguous outcome, and successful Test Mode completion.

No simulation or mocked HTTP response counts as Razorpay end-to-end evidence.

## Evidence-bundle checklist

Before any later checkpoint is marked passed, retain a machine-readable bundle
containing:

- commit SHA and clean/dirty status;
- checkpoint and prerequisite statuses;
- exact commands/configuration with secrets redacted;
- dependency lock or resolved versions;
- test report and benchmark artifacts;
- policy, schema, evidence-registry, and metric-definition versions/digests;
- execution mode (`SIMULATED` or `RAZORPAY_TEST`);
- wall-clock timestamps and latency measurement method;
- all failed cases and known limitations;
- artifact checksums.

## Gate discipline

Use these distinct labels:

- **implemented**: code exists;
- **locally verified**: deterministic tests pass;
- **integrated**: prerequisite outputs and external boundaries were exercised;
- **passed**: every frozen acceptance requirement passed with retained evidence.

Never infer a later label from an earlier one.

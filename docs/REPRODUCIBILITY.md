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
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.venv\Scripts\python.exe -m pip check
```

POSIX shell:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m pip check
```

`requirements-dev.lock` records exact distributions and accepted published
SHA-256 artifact hashes for CPython 3.11 Linux x86_64 and CPython 3.11/3.14
Windows x86_64. Binary-only installation and `--require-hashes` reject an
unlisted wheel. The editable project install disables dependency resolution and
build isolation. The exact setuptools and wheel build-backend distributions are
included in the same hash lock, so a newly created standard virtual environment
does not depend on an unrecorded bootstrap package. Downloading the published
wheels is still required unless an independently verified local wheel cache is
available, so this is not a fully offline build attestation.

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

Follow `CHECKPOINT_A_RUNBOOK.md`. Candidate 1 is mathematically failed and must
not be resumed. Candidate 2 starts a fresh, manifest-bound 80-case run. A full
gate requires all 80 immutable cases and all four frozen thresholds passing
together. Provider deferrals, smoke runs, fixtures, partial aggregates, and
schema failures cannot become a pass.

Candidate 2 retains a redacted record for every provider attempt, including a
transient HTTP or transport retry that later succeeds. This preserves the actual
attempt chronology without retaining provider bodies or credentials.
Terminal candidate evidence also carries an explicit correction-attempt flag and
uses different codes for failure before versus after a correction request.
The model provider, GitHub verifier, Razorpay transport, and inline credential
preflights attach authorization as an unredirected header and reject a changed
final response URL. Preserve `REDIRECT_REJECTED` as terminal provider evidence;
do not retry it as an outage or accept a redirected response.

Never print or pass a provider key in a shell command that will be retained. Use
the approved CI secret boundary.

## Razorpay Test Mode evidence

The repository includes a dedicated `RAZORPAY_TEST_MODE` adapter and two
manual-only workflows. Keep the secret exclusively in the GitHub Actions secret
`RAZORPAY_KEY_SECRET`; never place it in an input, command, artifact, or report.
The Test key ID is intentionally public client configuration and appears only in
the generated Checkout handoff, not in redacted server evidence.
The credentialed order producer refuses to write redacted evidence containing a
credential value. Summary and upload steps run without either Razorpay credential.

1. Dispatch **Razorpay Test Credential Preflight**. It refuses a non-test key ID,
   performs only a read-only order-list request, discards the provider response,
   rejects redirects without forwarding Basic authorization, and publishes safe
   status fields. Record the successful run ID.
2. Inspect the preflight summary before continuing. It must say Test mode,
   authentication verified, and response discarded; it must contain no key value.
3. From the same pushed source revision, dispatch **Razorpay Test Order Boundary
   Validation** with confirmation `RUN_TEST_MODE_ORDER` and the successful
   preflight run ID. The workflow's read-only `GITHUB_TOKEN` calls the official
   [Get a workflow run API](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run)
   and refuses a run from another repository, workflow, event, conclusion, or
   source SHA. This creates
   one INR 1.00 Test Mode order, revalidates its transaction notes/amount/currency,
   replays the same ECOCOMMIT idempotency key, fetches the order's payments, and
   retains redacted order evidence plus a digest-bound Checkout handoff JSON and
   standalone Test Checkout HTML page.
4. Treat `ORDER_API_VALIDATED_PAYMENT_LIFECYCLE_BLOCKED` and
   `checkpoint_b8_passed=false` literally. A successful workflow conclusion only
   means the validator retained this truthful partial result.
5. Before testing payment authorization/capture, set the Razorpay account to
   manual capture. Download and open the retained Test Checkout page, complete
   one genuine Test Checkout, and keep the downloaded callback JSON private.
6. Before capture, combine the handoff/callback into a pinned webhook binding,
   configure the public HTTPS URL ending in `/v1/razorpay/webhook` in the
   Razorpay Test Dashboard, and start the loopback receiver behind that reviewed
   route. Set the separate `RAZORPAY_WEBHOOK_SECRET` only in the environment:

   ```powershell
   .venv\Scripts\python.exe scripts\checkpoint_d_prepare_operation.py `
     --handoff artifacts\checkpoint-b8-checkout-handoff.json `
     --callback ecocommit-razorpay-checkout-callback.json `
     --output artifacts\private\checkpoint-b8-prepared-operation.json

   .venv\Scripts\python.exe scripts\checkpoint_b8_webhook_server.py `
     --port 8766 `
     --prepared-operation artifacts\private\checkpoint-b8-prepared-operation.json `
     --prepared-operation-sha256 <printed-file-sha256> `
     --state-db artifacts\checkpoint-b8-state.sqlite3 `
     --audit-path artifacts\checkpoint-b8-webhook-audit.ndjson
   ```

   The bundled receiver is loopback development software; do not expose it
   directly. Public TLS/routing, Razorpay IP/network controls, and Dashboard Test
   Mode configuration are externally retained evidence.
7. With the matching Test credentials in the environment, continue through the
   signature/provider binding, capture, compensating refund, and reconciliation.
   Set `ECOCOMMIT_B8_SIGNING_SECRET` to an untracked environment-only value of at
   least 32 bytes; never put it in the command or an artifact:

   ```powershell
   .venv\Scripts\python.exe scripts\checkpoint_b8_razorpay_continue.py `
     --handoff artifacts\checkpoint-b8-checkout-handoff.json `
     --callback ecocommit-razorpay-checkout-callback.json `
     --output artifacts\checkpoint-b8-lifecycle.json `
     --state-db artifacts\checkpoint-b8-state.sqlite3
   ```

   A local/fake test of this command is not provider evidence.
8. After both events arrive, verify webhook delivery/reconciliation. The raw route is
   `/v1/razorpay/webhook`; it verifies `X-Razorpay-Signature`, deduplicates
   `X-Razorpay-Event-Id`, and accepts bound `payment.captured` and
   `refund.processed` in either order. The bundled server listens only on
   loopback, so externally reachable TLS/routing and Razorpay Dashboard Test
   Mode configuration remain operator/hosting work. Export a complete verified
   set only after both events arrive:

   ```powershell
   .venv\Scripts\python.exe scripts\checkpoint_b8_webhook_evidence.py `
     --state-db artifacts\checkpoint-b8-state.sqlite3 `
     --transaction-id <bound-transaction-id> `
     --output artifacts\checkpoint-b8-webhooks.json
   ```

   The exporter retains verified event metadata and digests, not raw bodies or
   the webhook secret. Its Test-key binding does not independently prove the
   Dashboard endpoint was configured in Test Mode; retain that external fact.
9. Retain application denials and provider/transport failures and checksum the
   complete redacted evidence bundle.

The server-side Payments API cannot collect a payment, so step 5 requires an
interactive Test Checkout. No simulation, mocked HTTP response, credential
presence, or order-only run counts as complete B8 evidence.

## Future Checkpoint D provider-Test run

This path is implemented but cannot be run until genuine pinned A/B/C evidence
exists. It requires a separately prepared Test Checkout operation for the D
integration run; request JSON cannot construct one.

1. Combine the second human Checkout handoff/callback into a sensitive prepared
   operation and retain the printed file SHA-256 out of band:

   ```powershell
   .venv\Scripts\python.exe scripts\checkpoint_d_prepare_operation.py `
     --handoff artifacts\checkpoint-d-checkout-handoff.json `
     --callback ecocommit-checkpoint-d-callback.json `
     --output artifacts\private\checkpoint-d-prepared-operation.json
   ```

2. Verify the A/B/C pin bundle without enabling a provider:

   ```powershell
   .venv\Scripts\python.exe scripts\checkpoint_d_evidence_status.py `
     --evidence-root evidence\final `
     --pins evidence\final\checkpoint-d-pins.json `
     --pins-sha256 <out-of-band-pin-file-sha256>
   ```

3. Supply only through the environment: `RAZORPAY_KEY_ID`,
   `RAZORPAY_KEY_SECRET`, the separate Test endpoint
   `RAZORPAY_WEBHOOK_SECRET`, `ECOCOMMIT_D_SIGNING_SECRET` (at least 32 bytes),
   and `ECOCOMMIT_D_API_TOKEN` (at least 32 non-space bytes). Start the
   loopback worker with persistent paths:

   ```powershell
   .venv\Scripts\python.exe scripts\checkpoint_d_server.py `
     --port 8765 `
     --audit-path artifacts\checkpoint-d-audit.ndjson `
     --evidence-root evidence\final `
     --pins evidence\final\checkpoint-d-pins.json `
     --pins-sha256 <out-of-band-pin-file-sha256> `
     --prepared-operation artifacts\private\checkpoint-d-prepared-operation.json `
     --prepared-operation-sha256 <out-of-band-operation-file-sha256> `
     --state-db artifacts\checkpoint-d-state.sqlite3
   ```

   Startup validates the expected repository and complete pinned A/B/C chain,
   prepared operation, signing/webhook/API secrets, and persistent local state
   configuration before the read-only provider preflight. It fails closed unless
   the current Test credentials then pass. The operator UI reveals the Test execution form only when
   A–C/runtime prerequisites and the adapter are ready. It sends the bearer token
   only in the Authorization header and clears the field after the request.

4. A public run additionally needs an independently reviewed HTTPS reverse proxy
   or host, authentication/network controls, the webhook route configured in the
   Razorpay Test Dashboard, retained rate-limit/backup/monitoring/security tests,
   and a digest-cross-linked D integration receipt. The local result always says
   it does not by itself pass D. Never expose the bundled WSGI development server
   directly to the internet.

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

For strict E final mode, also retain a JSON receipt with schema
`E.REPRODUCTION.1`, the exact source revision, `independent_machine=true`, clean
checkout/full-test/dependency/readiness pass flags, and the retained reproduction
artifact SHA-256. Pass that file through `--independent-reproduction`; the local
checker does not create or self-attest it.

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

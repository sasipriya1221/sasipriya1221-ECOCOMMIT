# Submission Evidence Framework

This file is the judge-facing evidence manifest. It prevents a demo, fixture,
partial run, historical artifact, or locally passing test suite from being
presented as final ECOCOMMIT evidence.

## Current verdict

**Framework locally validated; final evidence bundle BLOCKED; Checkpoint E NOT
PASSED.**

No final ECOCOMMIT-versus-baseline numbers are available. No final screenshot or
video is retained. Checkpoint A is still incomplete, the only retained Razorpay
Checkout authorization is permanently non-promotable because it predates the
required certificate/key-reference provenance, and the post-fix Razorpay Test
lifecycle has not run. Apache-2.0 licensing and independent clean-machine
reproduction are retained, but they do not substitute for A-D final evidence.

`PROGRESS.md` is the canonical current evidence board; detailed failures remain
preserved in repository history, `evidence/`, checkpoint reports, and retained
GitHub Actions artifacts.

## Evidence slots

### Checkpoint A final semantic gate

<!-- EVIDENCE:CHECKPOINT_A_FINAL_METRICS status=BLOCKED -->

- Status: **BLOCKED**
- Required: one complete frozen 80/80 real-model run satisfying all four frozen
  thresholds together: case pass rate >= 90%, selective semantic reliability >=
  95%, autonomous coverage >= 55%, and ambiguous clarification accuracy >= 80%.
- Candidate 1 is permanently failed. Its retained aggregate had 21 passes, 11
  terminal failures, and 48 provider-deferred cases, so its mathematical maximum
  was 69/80 = 86.25%.
- Candidate 2 is incomplete and non-promotable after exposing the corrected
  resumability-classification defect.
- Current Candidate 3 run: `33590028177`, candidate source
  `fd26a52a21dc8431133c50be76d7d1ecaf0d099b`, manifest SHA-256
  `773cb2efef42c0b94491cb599cb5e0d0a361722fec566ba90fac9e595ee51934`.
- Latest retained Candidate 3 aggregate: artifact `9857872102`
  (`checkpoint-a-candidate-3-results-attempt-10`), archive SHA-256
  `917e74372b46f7727b565b335f4a6f23427b9f718d7948d137dcea8b304d900d`,
  aggregate JSON SHA-256
  `a5b807d02d69283e5e14c209661f8f2e4e027e0abe55e276e3d46032dcf0f723`.
- Attempt-10 cumulative truth: 18 terminal rows, 12 passes, 6 failures, 62
  missing cases, `full_frozen_gate_run=false`, `checkpoint_a_gate.passed=false`,
  and no typed A receipt. Candidate 3 is not yet mathematically eliminated for
  the case-pass criterion alone: its maximum remains 74/80 = 92.5%, but only two
  additional failures can occur while still reaching 72/80.
- Retry boundary: another provider-consuming continuation requires a fresh,
  digest-bound healthy-provider observation no more than 30 minutes old. A
  terminal old aggregate is not proof of current provider health.
- Do not insert: smoke results, partial aggregates, provider-deferred rows,
  synthetic fixtures, or metrics calculated from an incomplete set.
- Final artifact reference: **BLOCKED — not available**
- Artifact SHA-256: **BLOCKED — not available**

### Checkpoint B Razorpay Test Mode integration

<!-- EVIDENCE:CHECKPOINT_B_RAZORPAY_TEST status=BLOCKED -->

- Status: **BLOCKED**
- Required: accepted A evidence, the real A-to-B path, verified Razorpay Test
  context, source/run/transaction-bound certificate/key-reference provenance
  created before order creation, genuine Test authorization, secret-safe
  verification, capture, webhook delivery, refund, reconciliation, idempotency,
  compensation evidence, and the final typed B receipt.
- Historical order evidence remains retained but is never retroactively upgraded.
  Fresh-source preflight `33592456896` and order-boundary run `33592499084` at
  `fd26a52a…` passed only their limited boundaries and explicitly retained
  `checkpoint_b8_passed=false`.
- Later run `33645687964` at source
  `151379d2d144c7d692b9e8e6f8faef5ab16b72b0` produced a real Razorpay **Test
  Mode** Checkout authorization callback. Verification bound the callback to the
  server-expected order, but provenance for the required certificate/key
  reference did not legitimately exist before the order/authorization. That
  authorization is therefore **permanently non-promotable and must never be
  captured as B8 evidence**.
- Provenance remediation is public on `main`: the new path creates the
  source/run/transaction-bound certificate/key reference **before** any Razorpay
  order call and fails closed if it cannot. The authorization verifier uses the
  server-side expected order ID for Checkout HMAC, performs GET-only provider
  reads, requires exact INR 1.00 binding, `authorized`, `captured=false`, and zero
  refund, rejects Live keys, and contains no capture/refund mutation path.
- Exact-source Offline Regression run `33663013490` passed the remediation source
  with **471/471 tests**.
- Required next evidence is a **fresh post-fix Razorpay Test lifecycle**. No fresh
  order, authorization, capture, refund, webhook, reconciliation, settlement,
  Live Mode call, or real-money action is claimed here.
- Do not insert: `SIMULATED_LOCAL`, mocked provider replies, credential presence,
  the historical non-promotable authorization, or a certificate-only unit test.
- Promotion state: **BLOCKED — no final B8 receipt exists**.

### Checkpoint C final economic comparison

<!-- EVIDENCE:CHECKPOINT_C_FINAL_COMPARISON status=BLOCKED -->

- Status: **BLOCKED**
- Required: passing typed A+B receipts, genuine frozen held-out scenario
  manifests, final TEL weights/cost sources/decision rule, authentic comparator
  outputs, and the separately gated one-shot held-out run.
- Framework state: the write-once raw-row final protocol binds the held-out suite,
  case identities, metric/TEL/cost-source hashes, passing A+B receipts,
  candidate/comparator protocols, comparator selection receipt, distinct system
  identities, one execution ID/nonce hash, quantitative margins/floors/ceilings,
  missing/error treatment, and statistical method before outcomes are observed.
- The final runner rejects fixtures and simulated inputs, enforces exact case
  coverage and A→B→C revision/hash chains, re-scores raw rows, and publishes only
  atomic write-once evidence.
- No legitimate final A/B receipts or genuine one-shot held-out execution exists,
  so the final comparison has **not** been run.
- Do not insert: checked-in synthetic fixtures, preliminary harness output, or a
  benchmark produced before A+B pass.
- Final comparison table: **BLOCKED — deliberately absent**
- Final benchmark artifact SHA-256: **BLOCKED — not available**

### Checkpoint D final integrated product run

<!-- EVIDENCE:CHECKPOINT_D_FINAL_INTEGRATION status=BLOCKED -->

- Status: **BLOCKED**
- Required: authoritative upstream A/B/C receipt loading, integrated real product
  flow, provider Test Mode execution, durable operational state, hosted TLS/API/UI
  evidence, and final security/operational review.
- Local implementation state: strict pinned receipt loading, SQLite/OS-lock
  single-host durability, startup-pinned Test execution, bearer authentication,
  local rate limiting, operator UI, bound webhook ingestion, and hardened
  deployment templates are regression-tested.
- Deployment files define the WSGI/TLS/reverse-proxy/security contract, but no
  final hosted listener/DNS/certificate/backup/monitoring proof or integrated
  A/B/C transaction is retained. A previously retained temporary tunnel later
  returned HTTP 502 and is not treated as hosted proof.
- Do not insert: the synthetic D happy path, localhost status, a static render, or
  the failed temporary tunnel.
- Hosted application/API reference: **BLOCKED — not available**
- Integrated trace/artifact SHA-256: **BLOCKED — not available**

### Independent clean-machine reproduction

- Status: **RETAINED, but not sufficient for Checkpoint E while A-D are blocked**.
- Exact-source retained run: Independent Clean-Machine Reproduction
  `33687184607` at source
  `b911dedba1259c52dbc05dac6212f9d644df2542`.
- Environment: Ubuntu 24.04 / Python 3.11 with hash-locked dependencies.
- Result: **471/471 tests** and **8/8 repository-readiness checks** passed; the
  workflow verified exact public-main binding.
- Artifact: `9868579299`,
  `checkpoint-e-independent-reproduction-33687184607`, GitHub artifact digest
  `sha256:46d81f7d99e1cbd56ec30e533fbe55e0fa10b8d4729474b97d2fb62ca7cfd409`.
- Typed self-digesting reproduction receipt SHA-256:
  `3dea8640cec4ade8443d34cf5dbbcb1a68d21d31f5980826a2b8073770d411eb`.
- This reproduction made no provider call and did not promote fixtures.

### Final screenshots

<!-- EVIDENCE:FINAL_SCREENSHOTS status=BLOCKED -->

- Status: **BLOCKED**
- Required: capture only after the integrated system and displayed data are
  frozen; include source revision and capture context.
- Required manifest per image: filename, SHA-256, UTC capture time, exact source
  revision, page/route, execution mode, visible checkpoint states, viewport,
  redaction review, and the upstream artifact IDs/digests supporting every shown
  metric or provider state.
- Required frames: checkpoint/evidence status, economic state transition, final
  comparison only if C passed, and provider lifecycle only if B/D passed. Keep
  browser chrome/account identifiers/API keys/callback signatures/webhook URLs
  and secrets out of frame.
- Current placeholder: **No screenshot**. Development visual checks are not
  promoted into this slot.

### Final demo video

<!-- EVIDENCE:FINAL_VIDEO status=BLOCKED -->

- Status: **BLOCKED**
- Required: record only after A/B/C/D integration, final evidence freeze, and a
  truthful run-through of the final demo.
- Required manifest: file/host URL, SHA-256 where downloadable, UTC recording
  time, exact source revision, duration, presenter/operator identity reference,
  script revision, referenced evidence bundle, edits/cuts disclosure, captions,
  and redaction review.
- Required content: show the gate-status screen before claims, distinguish
  simulation from Test Mode aloud/on screen, trace only retained results, show
  failure/blocker states, and end with limitations. Never recreate a missing
  provider event or benchmark result for the recording.
- Current placeholder: **No video URL and no video claim**.

## Evidence-bundle manifest

When the blockers are cleared, retain one machine-readable manifest with these
fields. Empty fields stay blocked; they are never filled with examples.

| Field | Required content | Current state |
|---|---|---|
| `source_revision` | Immutable full Git commit SHA | Await final integrated commit |
| `working_tree_clean` | `true`, measured before each retained run | Await final integrated run |
| `checkpoint_statuses` | A-E state plus evidence references | A-D not passed; E not passed |
| `execution_mode` | Exact mode; Test Mode distinguished from simulation | Historical partial Test evidence retained; fresh post-fix lifecycle blocked |
| `environment` | OS, Python, resolved dependencies, lock digest | Hash-locked environment retained |
| `independent_reproduction` | `E.REPRODUCTION.2` source/tree/lock/count/report/bundle bindings and exact Actions artifact | Retained for source `b911dedb…`; future final source must receive its own exact-source reproduction |
| `commands` | Exact invocations with secrets removed | Framework available |
| `raw_artifacts` | Complete outputs, including failures/error rows | Final A-D artifacts blocked |
| `artifact_sha256` | Digest for every retained file | Partial/historical digests retained; final bundle blocked |
| `provider_evidence` | Redacted provider IDs, events, reconciliation | Historical authorization is non-promotable; fresh B lifecycle blocked |
| `metric_definitions` | Frozen definitions/weights/decision rules | A thresholds frozen; C final outcome execution blocked |
| `license` | Canonical repository license | Apache-2.0 retained |
| `screenshots` | Final integrated UI captures and provenance | Blocked |
| `video` | Final demo URL and source revision | Blocked |
| `limitations` | Known residual risks and non-claims | Present and must remain present |

## Promotion rule

An evidence slot may change from `BLOCKED` only when its prerequisite gate has
actually completed and the referenced artifact is retained and checksummed. The
same promotion must update `PROGRESS.md`, the relevant checkpoint report, and
this manifest. A URL, screenshot, metric, provider ID, or historical event
without its source revision and complete evidence chain is not accepted.

Current acceptance remains sequential: **A NOT PASSED → B BLOCKED → C BLOCKED →
D BLOCKED → E BLOCKED**. Missing proof stays visible instead of being converted
into a claim.
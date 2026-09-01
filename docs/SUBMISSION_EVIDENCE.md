# Submission Evidence Framework

This file is the judge-facing evidence manifest template. It prevents a demo,
fixture, partial run, or locally passing test suite from being presented as final
ECOCOMMIT evidence.

## Current verdict

**Framework locally validated; final evidence bundle BLOCKED; Checkpoint E NOT
PASSED.**

No final ECOCOMMIT-versus-baseline numbers are available. No final screenshot is
retained. No final video is recorded. Razorpay Test Mode authentication and one
order-level validation ran, but no payment authorization, capture, refund,
webhook delivery, reconciliation, or settlement was executed.

## Evidence slots

### Checkpoint A final semantic gate

<!-- EVIDENCE:CHECKPOINT_A_FINAL_METRICS status=BLOCKED -->

- Status: **BLOCKED**
- Required: one complete frozen 80/80 real-model run satisfying all four frozen
  thresholds together.
- Retained failure: Candidate 1, run `33493409547` attempt 15, is mathematically
  failed at a maximum 69/80. Its tracked failure manifest and aggregate/archive
  digests are in `PROGRESS.md`; corrected Candidate 2 is not evaluated.
- Do not insert: smoke results, partial aggregates, provider-deferred rows,
  synthetic fixtures, or metrics calculated from an incomplete set.
- Final artifact reference: **BLOCKED — not available**
- Artifact SHA-256: **BLOCKED — not available**

### Checkpoint B Razorpay Test Mode integration

<!-- EVIDENCE:CHECKPOINT_B_RAZORPAY_TEST status=BLOCKED -->

- Status: **BLOCKED**
- Required: accepted A evidence, the real A-to-B path, a dedicated Razorpay Test
  Mode adapter, verified test context, retained provider identifiers, genuine
  authorization/capture plus webhook and reconciliation results, idempotency,
  and compensation evidence.
- Do not insert: `SIMULATED_LOCAL`, mocked provider replies, credential presence,
  or a certificate-only unit test.
- Partial provider evidence: Actions preflights `33534255136` and `33535533432`;
  order-boundary run `33535533557` at isolated snapshot `596001c`.
- Partial redacted artifact: `checkpoint-b8-razorpay-test-evidence-33535533557`,
  artifact ID `9811456771`, GitHub artifact SHA-256
  `6d8cdcabbc78093f2638c8fbefd2e7bcd4d566d1eb807cd6fa0abf709d700f4d`.
- Exact blocker: `RAZORPAY_CHECKOUT_AUTHORIZATION_REQUIRED`; the Payments API
  cannot collect a payment, and no genuine Test Checkout callback/signature was
  available. A digest-bound Checkout page and capture/refund continuation now
  exist locally, but have not run against Razorpay. Manual capture and webhook
  configuration also remain unverified.
- Promotion state: **BLOCKED — partial order evidence is not final B8 evidence**.

### Checkpoint C final economic comparison

<!-- EVIDENCE:CHECKPOINT_C_FINAL_COMPARISON status=BLOCKED -->

- Status: **BLOCKED**
- Required: frozen real scenario manifests, final TEL weights and decision rule,
  authentic comparator outputs, validated A+B candidate, and the separately
  gated one-shot held-out run.
- Framework state: a final preregistration/evidence contract now binds the
  required hashes, upstream receipts, candidate/comparator, and quantitative
  rule before outcomes; no real registration values or results exist.
- Do not insert: the checked-in synthetic one-case fixture or preliminary harness
  output.
- Final comparison table: **BLOCKED — deliberately absent**
- Final benchmark artifact SHA-256: **BLOCKED — not available**

### Checkpoint D final integrated product run

<!-- EVIDENCE:CHECKPOINT_D_FINAL_INTEGRATION status=BLOCKED -->

- Status: **BLOCKED**
- Required: authoritative upstream evidence loading, integrated real A/B/C
  product flow, provider Test Mode execution, durable operational state, hosted
  API/UI evidence, and final security/operational review.
- Do not insert: the synthetic D happy path, localhost status, or a static render.
- Hosted application/API reference: **BLOCKED — not available**
- Integrated trace/artifact SHA-256: **BLOCKED — not available**

### Final screenshots

<!-- EVIDENCE:FINAL_SCREENSHOTS status=BLOCKED -->

- Status: **BLOCKED**
- Required: capture only after the integrated system and displayed data are
  frozen; include source revision and capture context.
- Current placeholder: **No screenshot**. Development visual checks are not
  promoted into this slot.

### Final demo video

<!-- EVIDENCE:FINAL_VIDEO status=BLOCKED -->

- Status: **BLOCKED**
- Required: record only after A/B/C/D integration, final evidence freeze, and a
  truthful run-through of the final demo.
- Current placeholder: **No video URL and no video claim**.

## Evidence-bundle manifest

When the blockers are cleared, retain one machine-readable manifest with these
fields. Empty fields stay blocked; they are never filled with examples.

| Field | Required content | Current state |
|---|---|---|
| `source_revision` | Immutable full Git commit SHA | Await final integrated commit |
| `working_tree_clean` | `true`, measured before each retained run | Await final run |
| `checkpoint_statuses` | A–E state plus evidence references | A–E not all passed |
| `execution_mode` | Exact mode; Test Mode distinguished from simulation | `SIMULATED_LOCAL` development plus partial `RAZORPAY_TEST_MODE` order evidence; full lifecycle blocked |
| `environment` | OS, Python, resolved dependencies, lock digest | Local manifest exists; independent reproduction pending |
| `commands` | Exact invocations with secrets removed | Framework available |
| `raw_artifacts` | Complete outputs, including failures/error rows | Final artifacts blocked |
| `artifact_sha256` | Digest for every retained file | Final artifacts blocked |
| `provider_evidence` | Redacted provider IDs, events, reconciliation | Order-level artifact retained; authorization/capture/webhook/reconciliation blocked |
| `metric_definitions` | Frozen definitions/weights/decision rules | C final freeze blocked |
| `screenshots` | Final integrated UI captures and provenance | Blocked |
| `video` | Final demo URL and source revision | Blocked |
| `limitations` | Known residual risks and non-claims | Must remain present |

## Promotion rule

An evidence slot may change from `BLOCKED` only when its prerequisite gate has
actually completed and the referenced artifact is retained and checksummed. The
same change must update `PROGRESS.md`, the relevant checkpoint report, and this
manifest. A URL, screenshot, metric, or provider ID without its source revision
and evidence chain is not accepted.

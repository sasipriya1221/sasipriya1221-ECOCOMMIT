# ECOCOMMIT Progress

Implementation may proceed in parallel when it does not trust an unmet
prerequisite. Acceptance remains sequential and evidence-gated.

| Checkpoint | Status | Acceptance gate |
|---|---|---|
| A — M0/M1 specification and contract language | 🟢 PASSED (offline scope) | Frozen specifications and authority invariants retained |
| A — M2/M3 intent intelligence and abstention | 🟠 RESUMABLE LIVE EVALUATION 14/80 RETAINED; ATTEMPT 6 RUNNING — NOT PASSED | Complete all 80 frozen cases, then satisfy every frozen A threshold together |
| B — deterministic economic safety | 🟡 B1–B7 LOCALLY VALIDATED — BLOCKED / NOT PASSED | A pass, real A-to-B evidence, durability/security work, and Razorpay Test Mode evidence |
| C — comparative benchmark | 🟡 LOCALLY VALIDATED — BLOCKED / NOT PASSED | Frozen real suite/plan, TEL weights and quantitative decision rule, real comparator outputs, validated A+B candidate, and separately gated final held-out run |
| D — product/API/UI/operations | 🟡 LOCALLY VALIDATED — BLOCKED / NOT PASSED | Authoritative upstream evidence, real A/B/C integration, provider Test Mode boundary, durable operations, and final security/operational evidence |
| E — architecture/reproducibility | 🟡 DOCUMENTATION SCAFFOLD — NOT PASSED | Reproduced end-to-end demo and complete retained evidence bundle |

## Checkpoint A

**Status: 🟠 RESUMABLE FROZEN LIVE EVALUATION INCOMPLETE — NOT PASSED**

Frozen Checkpoint A gate (all required in the same real-model full run):

- case pass rate >= 90%
- selective semantic reliability >= 95%
- autonomous coverage >= 55%
- ambiguous clarification accuracy >= 80%

The thresholds are unchanged.

### Current per-case resumable run

GitHub Actions run `33493409547`, head
`6485d3b24f4967c178cce9b1a9b67cdf0230840c`, uses the frozen current Groq
configuration `qwen/qwen3.6-27b`, reasoning effort `none`, JSON object mode, and
the unchanged 80-case dataset, prompt semantics, and thresholds. Each frozen
case is one independently resumable job; only failed provider-deferred jobs are
eligible for a later attempt.

Attempt 5 completed with conclusion `failure` at 2026-09-01T13:06:59Z and
produced aggregate artifact `checkpoint-a-results`, artifact ID `9801782811`,
at 2026-09-01T13:06:55Z. Verified archive SHA-256:
`360afe759656329b88eb4cb6a7356adad4d7690e7899e86ea80d24815f1fe3d7`;
downloaded JSON SHA-256:
`89d2669ee971a948a6eb478cd4f1d23bf7977094a975710a7d499563b766ca4a`.

Its truthful partial state is:

- retained terminal case rows: 14 / 80;
- retained semantic passes: 9;
- retained terminal local contract-validation failures: 5;
- provider-deferred/missing cases: 66;
- full frozen run: false;
- Checkpoint A gate: false / not passed.

The aggregate's four gate metrics are not interpreted from this partial set.
Checkpoint A cannot pass until all 80 immutable cases have terminal rows and the
complete aggregate satisfies all four frozen thresholds together.

Attempt 6 was started through GitHub's failed-jobs-only rerun operation after
attempt 5. It targets only the 66 provider-deferred case jobs. Previously
successful or terminal case jobs were not rescheduled, and their artifacts remain
immutable inputs to later aggregation.

### Latest completed 80-case run

GitHub Actions run `33477953132`, head
`c37da4fe1b1741de6d8e6a4bab53da56e5413b7e`, completed on 2026-09-01 with
conclusion `failure`. Its authenticated aggregate artifact is structurally
complete (80/80 IDs, no missing cases), but every row is a non-transient Groq
HTTP 400 `json_validate_failed` response and none contains a valid candidate
contract. All four frozen metrics are therefore 0.00% and the gate failed.

Retained artifact `checkpoint-a-results`, artifact ID `9789328621`, has archive
SHA-256 `beae38159f081c597cf9d021470712709ff13a63fb0985f460f65d8d10136527`;
the downloaded JSON SHA-256 is
`8237240e520ed76b7e192c2e3bcff2490480027dce35be9bacf520c6f59ab64b`.
This is retained failed operational/schema evidence, not semantic performance
evidence and not a Checkpoint A pass.

The earlier run `33431828865`, which this file previously described as running,
was cancelled and did not produce a passing gate.

### Earlier retained evidence

An earlier full Groq run (GitHub Actions run `33412737638`, head
`37e78c93205e44c626b13e6bd694ca6c85d8c1ef`) completed against the real configured
model and failed the frozen gate. Its aggregate metrics were:

- passed cases: 11 / 80
- case pass rate: 13.75%
- autonomous coverage: 30.00%
- selective semantic reliability: 41.67%
- ambiguous clarification accuracy: 13.33%

The retained artifact from that failed run shows concrete failure classes:
contract validation/source-span errors, missing negation/exception/dependency
structure, uncovered numeric signals, and ambiguity handling that sometimes
validated or rejected when clarification was required. Those results remain
failed development evidence; they are not relabeled or discarded.

A later 10-clear + 10-ambiguous real-model smoke (GitHub Actions run
`33426475689`, head `45f4c0158d3917e3174741217f9a90bf5f496a6f`) also
remained failed intermediate evidence because 16/20 cases hit Groq HTTP 429
token-per-day exhaustion and produced no usable model result.

The Qwen development smoke (GitHub Actions run `33430987810`, head
`b398be64a22006d601d0686549aaf2183a78acfe`) completed successfully against
`qwen/qwen3.8-27b` after the M2/M3 repairs:

- passed cases: 20 / 20
- case pass rate: 100.00%
- selective semantic reliability: 100.00%
- ambiguous clarification accuracy: 100.00%
- autonomous coverage: 50.00%
- failed cases: 0

The 50% autonomous-coverage value is expected for that deliberately balanced
10-clear + 10-ambiguous smoke: even perfect behavior can validate at most the 10
clear cases. A smoke never passes the frozen full gate.

This parallel change set does not alter Checkpoint A's benchmark cases, schemas,
provider workflows, model configuration, or frozen thresholds.

## Parallel local implementation evidence

The full deterministic regression suite passes **192/192 tests** in an isolated
local environment. This is local engineering evidence only; it does not substitute
for any live or final checkpoint gate.

### Checkpoint B — 53 focused tests

Implemented and locally verified:

- fail-closed A-to-B admission that recomputes the current `FidelityReport`,
  releases no obligations while the actual A gate is failed, and rejects a
  substituted contract hash;
- closed deterministic policy-class mapping over all 11 current A clause types;
- registered authority/issuer/kind/scope, freshness, version, identity,
  observation-time, revocation, subject, and exact-claim checks for evidence;
- trusted-config-only exposure tiers with exact authoritative claim predicates
  (contract/evidence payloads cannot raise a monetary cap, and negative approval
  cannot satisfy a tier);
- transaction-, merchant-, amount-, currency-, contract-, evidence-, policy-,
  expiry-, and nonce-bound HMAC commit certificates;
- trusted-policy recomputation before signing, so a self-consistent forged cap is
  rejected;
- strict progressive commitment histories and payment-boundary enforcement of the
  exact `CAPTURE_ALLOWED` state, certificate, transaction, and reservation;
- certificate reverification plus a registry version lock across the simulated
  irreversible capture boundary, including repeated concurrency tests;
- thread-safe process-local idempotency with complete signed-request collision
  checks, retry-safe compensation, capture/refund crash-window recovery, and
  reconciliation;
- an explicitly labelled `SIMULATED_LOCAL` payment adapter.

The full local B1–B7 validation matrix is recorded in
`CHECKPOINT_B_VALIDATION.md` against implementation commit `6877a81`. A synthetic
passed-A fixture proves interface compatibility only; it is not Checkpoint A
evidence.

Checkpoint B is not passed. The actual latest A gate failed and the real A-to-B
path correctly remains locked. The registries/ledgers are process-local, the HMAC
key is a local-test boundary rather than a KMS claim, and no Razorpay adapter,
credentialed Test Mode run, webhook evidence, or provider result exists.

### Checkpoint C — 41 focused tests

Implemented and locally validated:

- versioned plan, suite, scenario, evidence, cost, result, metric, TEL-weight,
  provenance, and artifact schemas with frozen instruction and suite digests;
- synthetic-fixture replay adapters for the naive-agent and prompt-guardrail
  comparator roles, plus static deterministic, fail-closed dynamic
  policy/risk/evidence workflow, and conservative-abstain controls;
- seeded deterministic ordering and a checked-in synthetic one-case plan/suite
  pinned to literal suite, plan, prompt, guardrail, and dynamic-config digests;
- preregistered integer Total Economic Loss weights and round-half-up accounting
  for unsafe execution, false abort, abstention review, and compensation cost;
- incorrect irreversible amount, selective reliability, coverage, legitimate
  completion, false-abort count/rate, compensation-event/outcome/cost,
  total/p95 latency, and missing-latency accounting;
- exact baseline×case coverage, retained error rows, mixed-latency provenance,
  repository/dependency provenance, and semantic recomputation of every result
  and summary so internally consistent tampering is rejected;
- compulsory `PRELIMINARY_NOT_FINAL`/not-passed labeling;
- explicit A and B final-pass prerequisites, plus rejection of live Checkpoint A
  outputs and all `FINAL_HELD_OUT` cases by the preliminary runner.

The checked-in suite, costs, TEL weights, agent outputs, evidence, and latency are
explicitly synthetic fixtures for harness validation only. No final comparison
numbers were generated or published. Checkpoint C is **blocked / not passed**:
the real suite and final TEL weights are not frozen; real naive-agent and
prompt-guardrail outputs are not retained; the strongest dynamic comparator has
not been selected by a preregistered study; no quantitative/statistical C
acceptance rule is frozen; A and B are not both validated; and the integrated
candidate and separately gated final held-out evaluation remain unrun.

### Checkpoint D — 44 focused tests

Implemented and locally validated:

- prerequisite-aware A–E gate status reporting that requires evidence references
  for any pass;
- health/readiness separation (health proves liveness only);
- append-only local JSONL audit records with a verified SHA-256 chain, strict
  record-shape validation, and shared in-process locking across log instances;
- structured finite metrics/logging, audited parser-boundary denials, and
  validated correlation IDs;
- a dependency-light JSON/WSGI facade whose commit endpoint always denies because
  no execution adapter is installed;
- explicit rejection/ignoring of caller-supplied authority claims such as
  `authorized`, `ai_validated`, or `checkpoint_a_passed`;
- deterministic synthetic A-to-B/exposure/certificate/commitment/payment workflow
  scenarios for simulated capture, Checkpoint-A blocking, and injected capture
  failure with reversible-hold cleanup;
- a loopback-only local server with fixed static assets and browser security
  headers; and
- a responsive safety console with fail-closed stale-status behavior, economic
  exposure/state visualization, and correlated failure feedback.

The committed implementation at `b583299` passes 44/44 focused D tests and
192/192 full regression tests. Python compilation, dependency consistency,
JavaScript syntax, all three deterministic CLI scenarios, loopback browser flow,
and 390 px responsive behavior were also checked. The full local matrix and the
defects found during validation are in `CHECKPOINT_D_VALIDATION.md`.

Checkpoint D is **blocked / not passed**. The local positive scenario uses a
synthetic A-pass fixture and `SIMULATED_LOCAL`; it is interface-compatibility
evidence only. The actual A, B, and C gates are not all passed, the real commit
route has no execution adapter, and no authoritative gate-evidence loader,
Razorpay Test Mode path, durable multi-process audit store, hosted deployment,
or final security/operational review exists.

### Checkpoint E scaffold

Added architecture/trust-boundary documentation, threat model, and reproducibility
runbook. They explicitly separate `implemented`, `locally verified`, `integrated`,
and `passed`, and require retained live/Test Mode evidence before later claims.

Checkpoint E is not passed.

## Payment truth

- Current payment behavior is only `SIMULATED_LOCAL`.
- No Razorpay credentials were present or used.
- No Razorpay API request was made.
- No Test Mode or live-money outcome is claimed.

Real Razorpay Test Mode work begins only when a dedicated adapter, verified test
credentials, secret handling, webhook/reconciliation paths, and retained end-to-end
evidence are available. Live money remains out of scope.

## Gate discipline

Parallel coding does not relax dependencies:

1. B cannot pass before A passes and A-to-B integration succeeds.
2. C cannot publish final comparisons before its evaluation protocol, suite, and
   integrated candidate are frozen and the separately gated held-out run executes.
3. D cannot pass from process health or scaffold tests.
4. E cannot pass from documentation alone.
5. No frozen threshold is lowered and no simulation is presented as real evidence.

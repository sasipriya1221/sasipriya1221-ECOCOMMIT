# ECOCOMMIT Progress

Implementation may proceed in parallel when it does not trust an unmet
prerequisite. Acceptance remains sequential and evidence-gated.

| Checkpoint | Status | Acceptance gate |
|---|---|---|
| A — M0/M1 specification and contract language | 🟢 PASSED (offline scope) | Frozen specifications and authority invariants retained |
| A — M2/M3 intent intelligence and abstention | 🔴 LATEST FULL LIVE GATE FAILED — NOT PASSED | One real full run must satisfy every frozen A threshold together |
| B — deterministic economic safety | 🟡 LOCALLY VERIFIED SCAFFOLD — NOT PASSED | A pass, A-to-B integration, durability/security work, and applicable Razorpay Test Mode evidence |
| C — comparative benchmark | 🟡 LOCALLY VERIFIED HARNESS — NOT PASSED | Frozen real suite/plan, valid integrated candidate, and separately gated final held-out run |
| D — product/API/UI/operations | 🟡 LOCALLY VERIFIED SCAFFOLD — NOT PASSED | Upstream gates, integrated product/security/operational evidence, and no default-deny bypass |
| E — architecture/reproducibility | 🟡 DOCUMENTATION SCAFFOLD — NOT PASSED | Reproduced end-to-end demo and complete retained evidence bundle |

## Checkpoint A

**Status: 🔴 LATEST FULL FROZEN LIVE GATE FAILED — NOT PASSED**

Frozen Checkpoint A gate (all required in the same real-model full run):

- case pass rate >= 90%
- selective semantic reliability >= 95%
- autonomous coverage >= 55%
- ambiguous clarification accuracy >= 80%

The thresholds are unchanged.

### Latest full run

GitHub Actions run `33477953132`, head
`c37da4fe1b1741de6d8e6a4bab53da56e5413b7e`, completed on 2026-09-01 with
conclusion `failure`.

Verified public job evidence:

- the offline regression job succeeded;
- all 16 live benchmark shards covering cases 0–79 succeeded;
- aggregation, compact diagnostics, and final artifact upload succeeded;
- the `Enforce frozen gate` step failed with exit code 2;
- retained artifact: `checkpoint-a-results`, artifact ID `9789328621`.

This establishes a genuine failed full gate rather than a provider/setup abort.
The aggregate artifact requires authenticated download and was not available in
this local checkout, so no new aggregate metric values are copied or inferred
here. The run remains failed evidence and Checkpoint A remains unpassed.

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

The full deterministic regression suite passes **126/126 tests** in an isolated
local environment. This is local engineering evidence only; it does not substitute
for any live or final checkpoint gate.

### Checkpoint B — 32 focused tests

Implemented and locally verified:

- closed deterministic policy-class mapping;
- registered authority/issuer/kind/scope, freshness, version, revocation, and
  subject checks for evidence;
- trusted-config-only exposure tiers (contract/evidence payloads cannot raise a
  monetary cap);
- transaction-, merchant-, amount-, currency-, contract-, evidence-, policy-,
  expiry-, and nonce-bound HMAC commit certificates;
- trusted-policy recomputation before signing, so a self-consistent forged cap is
  rejected;
- strict progressive commitment state transitions;
- certificate reverification at capture authorization and at the simulated
  irreversible capture boundary;
- thread-safe process-local idempotency, collision rejection, compensation, and
  reconciliation;
- an explicitly labelled `SIMULATED_LOCAL` payment adapter.

Checkpoint B is not passed. The registries/ledgers are process-local scaffolding,
the HMAC key is a local-test boundary rather than a KMS claim, A-to-B integration
has not run, and no Razorpay adapter or credentialed Test Mode evidence exists.

### Checkpoint C — 21 focused tests

Implemented and locally verified:

- pre-registered-style plan, suite, scenario, evidence, cost, result, metric, and
  artifact schemas;
- static-rule, dynamic policy/risk/evidence-aware, and conservative-abstain
  deterministic baselines;
- seeded deterministic ordering;
- Total Economic Loss, incorrect irreversible amount, selective reliability,
  coverage, legitimate completion, and nearest-rank p95 latency accounting;
- artifact integrity checks for plan/suite hashes and exact baseline×case result
  coverage;
- compulsory `PRELIMINARY_NOT_FINAL`/not-passed labeling;
- rejection of live Checkpoint A outputs and all `FINAL_HELD_OUT` cases by the
  preliminary runner.

No final comparison numbers were generated or published. Checkpoint C is not
passed; the real suite/plan and final candidate evaluation remain unfrozen and
unrun.

### Checkpoint D — 19 focused tests

Implemented and locally verified:

- prerequisite-aware A–E gate status reporting that requires evidence references
  for any pass;
- health/readiness separation (health proves liveness only);
- append-only local JSONL audit records with a verified SHA-256 chain;
- structured metrics/logging and validated correlation IDs;
- a dependency-light JSON/WSGI facade whose commit endpoint always denies because
  no execution adapter is installed;
- explicit rejection/ignoring of caller-supplied authority claims such as
  `authorized`, `ai_validated`, or `checkpoint_a_passed`;
- an unmistakably simulated endpoint and responsive safety-console UI.

Checkpoint D is not passed. Durable audit storage, authoritative gate-evidence
loading, B integration, hosted UI/API execution, and operational/security review
remain pending.

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

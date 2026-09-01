# ECOCOMMIT Progress

Implementation may proceed in parallel when it does not trust an unmet
prerequisite. Acceptance remains sequential and evidence-gated.

| Checkpoint | Current state | What is still required |
|---|---|---|
| A — frozen semantic gate | **Candidate 1 FAILED; Candidate 2 BUILT + LOCALLY VALIDATED, NOT EVALUATED** | Commit/push authorization, fresh 80-case provider run, and all four unchanged thresholds passing together |
| B — deterministic economic safety | **B1–B7 LOCALLY VALIDATED; B8 order subgates live-validated; NOT PASSED** | Passing A receipt, genuine Test Checkout/capture/refund/webhook evidence, durable state, and production-grade key boundary |
| C — comparative benchmark | **Framework + final preregistration contract LOCALLY VALIDATED; NOT PASSED** | Real frozen suite/costs/outputs, pre-outcome rule choices, passing A+B receipts, and one-shot held-out run |
| D — product/API/UI/operations | **LOCAL SIMULATION LOCALLY VALIDATED; NOT PASSED** | Authoritative A/B/C loading, durable provider execution, hosted operations, and final integrated evidence |
| E — repository/submission readiness | **LOCAL CHECKER LOCALLY VALIDATED; NOT PASSED** | A–D evidence, owner-selected license, push, independent reproduction, final screenshots, and video |

Status vocabulary is strict: **BUILT** means an implementation exists;
**LOCALLY VALIDATED** means deterministic local checks passed; **BLOCKED** means a
required upstream, external, legal, or final-run input is absent; **PASSED** means
the complete acceptance gate passed with retained evidence.

## Checkpoint A

### Frozen acceptance rule

All four thresholds must pass in the same complete real-model 80-case run:

- case pass rate >= 90%;
- selective semantic reliability >= 95%;
- autonomous coverage >= 55%; and
- ambiguous clarification accuracy >= 80%.

The 80 cases, thresholds, and evaluator were not weakened or rewritten.

### Candidate 1 — mathematically failed

GitHub Actions run `33493409547`, attempt 15, evaluated frozen source
`6485d3b24f4967c178cce9b1a9b67cdf0230840c`. The retained aggregate had:

- 32 terminal rows;
- 21 semantic passes;
- 11 terminal candidate-contract failures; and
- 48 provider-deferred cases.

Even if every deferred case later passed, Candidate 1 could reach only 69/80 or
86.25%, below the frozen 90% case-pass threshold. Candidate 1 is therefore
**FAILED**, not resumable toward a pass.

The 11 terminal cases are `C002`, `C005`, `C011`, `C012`, `C014`, `C015`,
`C016`, `C017`, `C023`, `C024`, and `A026`. The first ten contained an
incomplete trailing `auth_01` clause missing required `materiality` and
`confidence`; `A026` omitted the top-level `clauses` field. None reached semantic
scoring. Every one of the other 48 latest failed job logs was separately
verified as `transient_provider_error` and is not relabelled as a semantic
failure.

Retained evidence:

- run: `https://github.com/sasipriya1221/sasipriya1221-ECOCOMMIT/actions/runs/33493409547`;
- aggregate artifact ID: `9813043400`;
- archive SHA-256: `6f0052ddf1152f7e25ba13d0a3f9dbea52d6c0a994b0d526d1c2de3ee72b183a`;
- result JSON SHA-256: `1cb8eb4ae722ea77b02a2a2b10891b86f3b2b5c40b3df753b93e8bb0f8c1f4a7`; and
- tracked failure manifest: `evidence/checkpoint-a-candidate-1-failure.json`.

### Candidate 2 — corrected but not launched

The corrected candidate is explicitly versioned `A-CANDIDATE-2` and starts a
fresh 80-case run. It does not reuse Candidate 1 rows. The local implementation:

- requires every model-emitted clause field explicitly before Pydantic defaults;
- never invents missing confidence, materiality, provenance, or graph edges;
- performs at most one general schema-correction request;
- retains bounded candidate hashes, finish reason, request ID, usage, validation
  paths, and correction/provider chronology without retaining raw provider text;
- treats a provider failure after an invalid candidate as a terminal interrupted
  correction, not a resumable pure provider deferral;
- restricts provider URLs to HTTPS allowlisted hosts and bounds response bodies;
- accepts credentials only through the environment;
- binds each row to the frozen dataset, case, prompt/schema, evaluator, runner,
  criteria, provider configuration, source revision, and manifest digests;
- recomputes every successful semantic row during aggregation; and
- permits identical attempt duplicates but rejects conflicts or mixed manifests.

The Candidate 2 workflow uses fresh, immutable, per-attempt artifact names and
emits a typed passing receipt only after a complete aggregate passes. It is
commit-pinned and scopes the provider secret only to the validation steps.

Candidate 2 has not been pushed, dispatched, or represented as live evidence.
Remote launch requires an intentional push/dispatch boundary and the configured
provider secret.

## Checkpoint B

B1–B7 remain locally validated: policy mapping, authoritative evidence,
exposure, progressive commitment, TOCTOU protection, certificates,
idempotency/reconciliation, and compensation all fail closed under adversarial
tests.

The A→B boundary no longer accepts a caller-created “A passed” string. It requires
a typed receipt bound to Candidate 2, the frozen dataset and thresholds, the
aggregate/manifest/source digests, and the exact evidence reference. Explicit
test-fixture receipts are refused by the production bridge.

Live Razorpay evidence already retained:

- credential preflight runs `33534255136` and `33535533432` authenticated in Test
  Mode without retaining provider bodies or credentials;
- order-boundary run `33535533557` created/fetched one INR 1.00 order and proved
  exact transaction binding plus identical idempotent replay;
- artifact ID `9811456771`, archive SHA-256
  `6d8cdcabbc78093f2638c8fbefd2e7bcd4d566d1eb807cd6fa0abf709d700f4d`.

Locally, the order workflow now emits a digest-bound Test Checkout handoff and
standalone page. A continuation validates the returned Checkout HMAC and exact
provider order/payment, captures only behind ECOCOMMIT's certificate and TOCTOU
gate, performs an idempotent compensating refund, and reconciles the state.

This new lifecycle has only fake-transport regression evidence. No genuine
Checkout, capture, refund, webhook, or reconciliation outcome is claimed. The
remaining human/external actions are manual-capture account confirmation, one
Test Checkout interaction, and webhook endpoint/secret configuration and event
delivery. Process-local ledgers/registries and the local HMAC signer are not
production durability/KMS claims.

## Checkpoint C

The V2 preliminary framework remains explicitly synthetic and ineligible for
final claims. It validates comparator registration, deterministic ordering,
TEL accounting, latency/error treatment, provenance, full pair coverage, and
semantic artifact recomputation.

A separate final protocol now requires, before outcomes are observed:

- hashes for the real held-out suite, case identities, metric specification, TEL
  weights, and cost-source manifest;
- passing A and B receipt hashes plus the integrated candidate revision;
- the selected comparator;
- a quantitative TEL-reduction margin, legitimate-completion and selective-
  reliability floors, latency/error/missing-data/irreversible-loss ceilings,
  tie handling, rationale, and statistical method; and
- authentic case-result hashes with fixtures, simulated costs, and simulated
  latency structurally forbidden.

No real plan values or results were invented. C remains blocked on the real
inputs, preregistration decisions, A+B, and one-shot held-out execution.

## Checkpoint D

The loopback API/UI, audit/observability, parser limits, status truth, and three
synthetic workflows remain locally validated. `HAPPY_PATH` is still labelled
`SIMULATED_LOCAL`; `/v1/commit` still denies because no authoritative execution
adapter is installed.

D does not pass from component health, synthetic A evidence, or the existence of
the Razorpay adapter. It still requires authoritative A/B/C receipt loading,
durable multi-process state/audit/idempotency, a provider-backed product flow,
hosted evidence, and final security/operational review.

## Checkpoint E and release security

The readiness checker can now genuinely transition to final-ready: it reads each
evidence slot's `BLOCKED`/`FAILED`/`PASSED` state, validates a revision-bound
independent-reproduction receipt, and provides a strict `--mode final`. Today's
real slots remain blocked, so final readiness remains false.

All repository workflows now:

- pin third-party actions to full commit SHAs;
- disable persisted checkout credentials;
- scope provider/payment secrets to individual steps;
- avoid printing provider bodies; and
- use the hash-locked validation dependency file.

Offline CI watches source, scripts, tests, docs, UI, workflows, protocol files,
and the lock, then runs tests, compilation, JavaScript syntax, dependency
consistency, readiness structure, and diff checks. The lock authorizes exact
published artifact hashes for the supported Linux CI and Windows validation
wheels, including the exact setuptools/wheel build backend required by a fresh
virtual environment; editable project installation uses
`--no-deps --no-build-isolation`.

Final E blockers are unchanged in substance: A–D final evidence, license choice,
intentional push/public CI, independent reproduction, final screenshots, and the
five-minute video.

## Non-claims

- Candidate 1 did not pass and will not be retried into a pass.
- Candidate 2 has not run remotely.
- Provider deferrals are not semantic failures; contract failures are not
  provider deferrals.
- The Razorpay order subgate is not a payment-lifecycle pass.
- Synthetic B/C/D fixtures are not provider or final comparison evidence.
- No final comparator/TEL numbers, hosted integration, independent reproduction,
  screenshot, or video is claimed.
- No remote push was performed without explicit authorization.

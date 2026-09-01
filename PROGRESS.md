# ECOCOMMIT Progress

Implementation may proceed in parallel when it does not trust an unmet
prerequisite. Acceptance remains sequential and evidence-gated.

| Checkpoint | Current state | What is still required |
|---|---|---|
| A — frozen semantic gate | **Candidate 1 FAILED; remote score-recovery experiment CANCELLED; Candidate 2 BUILT + LOCALLY VALIDATED, NOT EVALUATED** | Commit/push authorization, fresh 80-case Candidate 2 provider run, and all four unchanged thresholds passing together |
| B — deterministic economic safety | **B1–B7 + durable single-host runtime LOCALLY VALIDATED; B8 order subgates live-validated; NOT PASSED** | Passing A receipt, genuine Test Checkout/capture/refund/webhook evidence, and an independently verified signing-key boundary |
| C — comparative benchmark | **Framework + final preregistration contract LOCALLY VALIDATED; NOT PASSED** | Real frozen suite/costs/outputs, pre-outcome rule choices, passing A+B receipts, and one-shot held-out run |
| D — product/API/UI/operations | **AUTHORITATIVE LOADER + DURABLE TEST EXECUTION PATH LOCALLY VALIDATED; NOT PASSED** | Real pinned A/B/C receipts, current credentials/human callback/webhooks, hosted security/operations, and final integrated evidence |
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

Operational warning observed at `2026-09-01T21:25:25Z`: the obsolete Candidate
1 run `33493409547` was still `queued` as attempt 27 at frozen source
`6485d3b24f4967c178cce9b1a9b67cdf0230840c`. Candidate 1 is already
mathematically failed, so this attempt cannot alter its acceptance state and
must not be allowed to consume provider capacity or produce replacement rows.
The account operator must cancel it in GitHub Actions and stop rerunning Candidate
1. The timestamped observation is retained in
`evidence/checkpoint-a-candidate-1-obsolete-queued.json`; no queue actor or future
state is inferred.

### Remote score-recovery experiment — cancelled and not promotable

After Candidate 2 had been built locally, `origin/main` independently advanced to
`1cc9fd199781de3974adbcb6099b77d89aec2206` and launched run `33556907712`.
That source was not Candidate 2. It used the earlier runner and added a contract
pre-validator that filled omitted `materiality` and `confidence` with `1.0` when
a clause self-labelled as grounded and explicit.

The public run metadata proves a partial operational result only:

- offline regression succeeded;
- one case job completed successfully, but its row is not claimed as a semantic
  pass because the artifact content could not be downloaded without an
  authenticated GitHub session;
- cases 0, 2, 3, 4, 5, 6, and 7 exited with code 75, which that exact runner emits
  only for `transient_provider_error` deferrals;
- the other 72 case jobs were cancelled; and
- aggregation failed and the run conclusion was `cancelled`.

No newer same-workflow run was visible, while the public API does not expose the
cancellation actor or reason. The 11 published artifacts and their GitHub-published
archive digests are recorded without claiming that their contents were locally
re-hashed or inspected in
`evidence/checkpoint-a-run-33556907712-cancelled.json`.

The score-filling change was rejected during reconciliation. Exact text grounding
does not prove maximum materiality or extraction confidence, and those values
affect downstream validation. The reconciled contract therefore still requires
both fields, the provider still requests one bounded model correction for an
incomplete candidate, and regressions now explicitly cover both omitted scores.
The remote history and cancelled evidence remain preserved; they do not pass A
and do not evaluate Candidate 2.

### Candidate 2 — corrected but not launched

The corrected candidate is explicitly versioned `A-CANDIDATE-2` and starts a
fresh 80-case run. It does not reuse Candidate 1 rows. The local implementation:

- requires every model-emitted clause field explicitly before Pydantic defaults;
- never invents missing confidence, materiality, provenance, or graph edges;
- performs at most one general schema-correction request;
- retains bounded candidate hashes, finish reason, request ID, usage, validation
  paths, and complete correction/provider chronology—including transient retries
  that later recover—without retaining raw provider text;
- treats a provider failure after an invalid candidate as a terminal interrupted
  correction, not a resumable pure provider deferral;
- records whether a terminal schema failure occurred before or after a correction
  request instead of inferring correction from a generic error label;
- restricts provider URLs to HTTPS allowlisted hosts and bounds response bodies;
- strictly decodes provider envelopes and candidates, rejecting duplicate keys,
  non-finite numbers, invalid Unicode scalar values, and excessive structure;
- accepts credentials only through the environment;
- binds each row to the frozen dataset, case, prompt/schema, evaluator, runner,
  criteria, provider configuration, source revision, and manifest digests;
- directly hashes the interpreter, strict decoder, protocol, shard, aggregate,
  and typed receipt implementation into the runner manifest;
- recomputes every successful semantic row during aggregation; and
- permits identical attempt duplicates but rejects conflicts or mixed manifests;
  resume/aggregate files must be bounded nonsymlinked strict UTF-8 JSON objects.

The Candidate 2 workflow uses fresh, immutable, per-attempt artifact names and
emits a typed passing receipt only after a complete aggregate passes. It is
commit-pinned and scopes the provider secret only to the validation steps.

Candidate 2 has not been pushed, dispatched, or represented as live evidence.
Run `33556907712` is explicitly excluded because it used a different, earlier
protocol and ended cancelled.
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

That historical order run remains evidence for its original adapter snapshot; it
is not retroactively upgraded. The current manual order-boundary workflow now
uses GitHub's Actions API to require a successful `workflow_dispatch` preflight
from the expected workflow, repository, and exact lifecycle source revision. A
bounded strict-JSON receipt is digest-bound, retained, and consumed before
Razorpay credentials are loaded.
The order validator initializes no credential values and does not invoke the
credential factory until that receipt has passed. Its tampered-receipt regression
installs credentials plus a factory trap and proves neither credential loading nor
provider construction occurs on the rejected path.
All tracked credentialed `urllib` clients now attach `Authorization` as an
unredirected header and reject any response whose final URL differs from the
fixed request URL. This covers Candidate 2/model calls, GitHub run verification,
Razorpay API calls, and both inline credential preflights. The new regressions do
not create provider evidence or retroactively upgrade the retained historical run.
Every workflow that references a repository secret is now `workflow_dispatch`
only. Pushing the accumulated source can start offline regression but cannot by
itself start a model-provider or Razorpay request; the retained legacy sentinel
files are inert historical records.

Locally, the order workflow now emits a digest-bound Test Checkout handoff and
standalone page. A continuation validates the returned Checkout HMAC and exact
provider order/payment, captures only behind ECOCOMMIT's certificate and TOCTOU
gate, performs an idempotent compensating refund, and reconciles the state.

This new lifecycle has only fake-transport regression evidence. No genuine
Checkout, capture, refund, webhook, or reconciliation outcome is claimed. The
remaining human/external actions are manual-capture account confirmation, one
Test Checkout interaction, and webhook endpoint/secret configuration and event
delivery. The local runtime now provides SQLite WAL/FULL-sync payment,
commitment, idempotency, and webhook state plus cross-process audit locking and
restart replay. Pending refunds remain retryable, poll only their exact provider
refund ID, and can reach processed compensation after restart or handoff expiry;
expiry never grants fresh capture authority to a merely reserved payment. That
is a **single-host durability implementation**, not a
high-availability, malicious-database-tamper, backup/restore, or KMS claim.

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
Standalone plan/suite loading now uses the same bounded nonsymlinked strict-JSON
boundary, so duplicate-key or non-standard JSON cannot silently change a frozen
benchmark input.

## Checkpoint D

The loopback API/UI, audit/observability, parser limits, status truth, and three
synthetic workflows remain locally validated. The default server still loads no
authority and `/v1/commit` denies. A separate startup-only path now:

- reloads strict SHA-256-pinned A/B/C[/D] receipts on every status request and
  verifies the expected repository plus every revision and upstream cross-link;
- performs a read-only current-credential preflight before enabling any Test
  provider call;
- accepts only an opaque, digest-pinned operation ID at the HTTP boundary;
- requires an environment-only bearer token, applies a single-process rate
  limit to failed and successful authentication attempts, and never accepts
  transaction/evidence/callback/key authority from a request;
- executes capture/compensation with SQLite-backed cross-process idempotency,
  payment, commitment, and result replay; and
- verifies raw Razorpay webhook HMACs, deduplicates the official event-ID
  header, handles capture/refund arrival order, and retains only bound redacted
  event records.

The UI exposes this operator Test path only when the server reports it ready;
the bearer token is cleared after the request and is never stored or placed in
JSON. A locally produced execution/webhook result explicitly does **not** pass D.
D still requires real pinned A/B/C receipts, the human/provider events, a public
TLS deployment/reverse proxy, independently verified authentication/rate-limit/
webhook endpoint configuration, operations evidence, and a cross-linked D
receipt. The bundled WSGI server remains loopback development software.

## Checkpoint E and release security

The readiness checker can now genuinely transition to final-ready: it reads each
evidence slot's `BLOCKED`/`FAILED`/`PASSED` state, validates a revision-bound
independent-reproduction receipt as a bounded nonsymlinked strict JSON object
with exactly the typed fields, and provides a strict `--mode final`. Today's
real slots remain blocked, so final readiness remains false.

All repository workflows now:

- pin third-party actions to full commit SHAs;
- disable persisted checkout credentials;
- scope provider/payment secrets only to steps that perform provider work;
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
- Candidate 1 run `33493409547` was observed queued at attempt 27 and must be
  cancelled by an authorized GitHub operator; it is not resumable evidence.
- Cancelled run `33556907712` is neither an A pass nor a Candidate 2 run; its
  provider deferrals and cancelled jobs are not relabelled as semantic outcomes.
- Candidate 2 has not run remotely.
- Provider deferrals are not semantic failures; contract failures are not
  provider deferrals.
- The Razorpay order subgate is not a payment-lifecycle pass.
- Synthetic B/C/D fixtures are not provider or final comparison evidence.
- No final comparator/TEL numbers, hosted integration, independent reproduction,
  screenshot, or video is claimed.
- No remote push was performed without explicit authorization.

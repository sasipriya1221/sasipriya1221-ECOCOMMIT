# ECOCOMMIT Progress

Implementation may proceed in parallel when it does not trust an unmet
prerequisite. Acceptance remains sequential and evidence-gated.

| Checkpoint | Current state | What is still required |
|---|---|---|
| A — frozen semantic gate | **Candidate 1 FAILED; Candidate 2 REMOTE RUN INCOMPLETE; Candidate 3 RUNNER FIX BUILT + FOCUSED-VALIDATED, NOT PUSHED/EVALUATED** | Fresh 80-case Candidate 3 provider run and all four unchanged thresholds passing together |
| B — deterministic economic safety | **B1–B7 + durable single-host runtime LOCALLY VALIDATED; B8 order subgates live-validated; NOT PASSED** | Passing A receipt, genuine Test Checkout/capture/refund/webhook evidence, and an independently verified signing-key boundary |
| C — comparative benchmark | **Framework + final preregistration contract LOCALLY VALIDATED; NOT PASSED** | Real frozen suite/costs/outputs, pre-outcome rule choices, passing A+B receipts, and one-shot held-out run |
| D — product/API/UI/operations | **AUTHORITATIVE LOADER + DURABLE TEST EXECUTION PATH LOCALLY VALIDATED; NOT PASSED** | Real pinned A/B/C receipts, current credentials/human callback/webhooks, hosted security/operations, and final integrated evidence |
| E — repository/submission readiness | **PUBLIC MAIN + OFFLINE CI + LOCAL CHECKER VALIDATED; NOT PASSED** | A–D evidence, owner-selected license, independent reproduction, final screenshots, and video |

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

Pre-dispatch public metadata checked at `2026-09-02T02:23:34Z` now reports the
same run completed with conclusion `failure` at attempt 27. It is no longer
active and needs no cancellation. This later operational state cannot replace
or improve the immutable attempt-15 mathematical failure. The current
observation is retained separately in
`evidence/checkpoint-a-pre-dispatch-run-status.json`.

### Remote score-recovery experiment — failed after reruns and not promotable

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

That file remains the immutable observation of attempt 1. Pre-dispatch public
metadata checked at `2026-09-02T02:23:34Z` reports the same run completed with
conclusion `failure` at attempt 6. The head SHA remains
`1cc9fd199781de3974adbcb6099b77d89aec2206`. The later reruns still use the
rejected earlier protocol and are not Candidate 2 or Candidate 3; no row or
artifact from any attempt is eligible for a frozen-candidate resume.

The score-filling change was rejected during reconciliation. Exact text grounding
does not prove maximum materiality or extraction confidence, and those values
affect downstream validation. The reconciled contract therefore still requires
both fields, the provider still requests one bounded model correction for an
incomplete candidate, and regressions now explicitly cover both omitted scores.
The remote history and cancelled evidence remain preserved; they do not pass A
and do not evaluate Candidate 2.

### Candidate 2 — launched, incomplete, and not promotable

The validated source was fast-forward pushed to public `main` at
`c52884eb455c1858608d430aa2d14b1d31a9fa12`. Offline Regression run
`33583217298` passed. The manually authorized frozen Candidate 2 workflow is run
`33583323178`, workflow number 11, at that exact source.

Attempt 1 completed with:

- successful offline regression and secret checks;
- 80 immutable case artifacts;
- 78 case jobs exiting code 75 as `transient_provider_error` deferrals;
- two case jobs completing the live path, but **zero semantic passes**;
- only two aggregate rows, 78 missing rows, and a failed partial aggregate; and
- no passing receipt.

The terminal diagnostics were `C002: provider HTTP_429 after 2 attempt(s)` and
`C042: candidate contract invalid before correction could be attempted`. These
are not treated as clean semantic failures. The frozen runner converted a
transient provider interruption during correction into terminal evidence, and
could also retain a schema-invalid row after provider retry consumed the bounded
request budget before the promised correction ran. The immutable public-metadata,
job-log, artifact-digest, and non-claim record is
`evidence/checkpoint-a-candidate-2-attempt-1.json`.

A failed-jobs-only rerun legitimately completed attempt 2 without changing the
dataset, prompt, evaluator, model configuration, schemas, or thresholds. It
preserved successful jobs and retried only the 78 provider-deferred jobs plus the
dependent aggregate. Two retry jobs became terminal: `A004` logged `passed=true`,
while `C004` failed before correction could be attempted. The cumulative
aggregate has four rows, one pass, three infrastructure/runner-contaminated error
rows (`C002`, `C004`, `C042`), 76 missing rows, and no receipt. Attempt 2 is
retained in `evidence/checkpoint-a-candidate-2-attempt-2.json`. Further Candidate
2 retries are not justified because failed-jobs-only reruns cannot repair the
three contaminated rows already retained by successful jobs.

### Candidate 3 — runner-only correction, not launched

The evidence-driven correction is explicitly versioned `A-CANDIDATE-3`. It
keeps the same frozen 80 cases, Qwen model/provider configuration, prompt,
contract schema, semantic evaluator, and four acceptance thresholds. Only the
execution classification and fresh artifact namespace change:

- a transient provider failure interrupting schema correction remains a
  resumable infrastructure deferral;
- a schema-invalid candidate that did not receive its correction opportunity
  because the trace contains a transient provider retry remains resumable;
- completed bounded correction failures and non-transient provider errors remain
  terminal;
- every case and aggregate artifact uses a fresh Candidate 3 name so no Candidate
  1 or Candidate 2 row can enter the run; and
- the typed receipt is bound to Candidate 3 while retaining the frozen dataset
  digest and thresholds.

The focused Candidate 3/provider/evidence scope passes **67/67** with an isolated
local pytest temp area. Implementation commit `bb4c15b7…` passes **392/392** in
both the working repository and a separate no-hardlink clean copy. Candidate 3
has not been pushed, dispatched, or evaluated. A fresh remote run requires an
explicit push/dispatch boundary; no current result marks Checkpoint A passed.

## Checkpoint B

B1–B7 remain locally validated: policy mapping, authoritative evidence,
exposure, progressive commitment, TOCTOU protection, certificates,
idempotency/reconciliation, and compensation all fail closed under adversarial
tests.

The A→B boundary no longer accepts a caller-created “A passed” string. It requires
a typed receipt bound to Candidate 3, the frozen dataset and thresholds, the
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
fixed request URL. This covers Checkpoint A model calls, GitHub run verification,
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

Remote readiness is now identity-bound rather than presence-based. Only the
expected public GitHub repository is accepted; local filesystem clones,
mismatched/alternate hosts, insecure transports, credential-bearing URLs, and
malformed remotes remain final blockers. The report emits only the canonical
expected URL and never echoes a raw invalid origin that could contain a token.

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

Public `main` and offline CI are now real at `c52884e…`; the local Candidate 3
runner correction is intentionally not pushed. Final E blockers remain A–D final
evidence, license choice, an authorized Candidate 3 push/CI if that candidate is
adopted, independent reproduction, final screenshots, and the five-minute video.

## Non-claims

- Candidate 1 did not pass and will not be retried into a pass.
- Candidate 1 run `33493409547` is completed with failure at attempt 27; it is
  neither resumable evidence nor a replacement for the retained attempt-15 failure.
- Excluded run `33556907712` is completed with failure at attempt 6 and is neither
  an A pass nor a frozen Candidate 2/3 run; none of its attempts or artifacts may be resumed.
- Candidate 2 ran remotely; attempts 1 and 2 remained incomplete and contaminated
  by a runner classification defect. It did not pass and will not be retried.
- Candidate 3 has not been pushed or evaluated.
- Provider deferrals are not semantic failures; contract failures are not
  provider deferrals.
- The Razorpay order subgate is not a payment-lifecycle pass.
- Synthetic B/C/D fixtures are not provider or final comparison evidence.
- No final comparator/TEL numbers, hosted integration, independent reproduction,
  screenshot, or video is claimed.
- No remote push was performed without explicit authorization.

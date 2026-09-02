# ECOCOMMIT Progress

Implementation may proceed in parallel when it does not trust an unmet
prerequisite. Acceptance remains sequential and evidence-gated.

| Checkpoint | Current state | What is still required |
|---|---|---|
| A — frozen semantic gate | **Candidate 1 FAILED; Candidate 2 INCOMPLETE; Candidate 3 ATTEMPT 2 INCOMPLETE / PROVIDER-BLOCKED; NOT PASSED** | After confirmed provider-capacity recovery, resume only the 78 deferred Candidate 3 jobs and pass all four unchanged thresholds together |
| B — deterministic economic safety | **B1–B7 + DURABLE RUNTIME + B8 FINALIZER LOCALLY VALIDATED; ORDER SUBGATES LIVE-VALIDATED; NOT PASSED** | Passing A receipt, Test manual-capture/webhook attestations, and genuine Checkout/capture/refund/webhook evidence |
| C — comparative benchmark | **RAW-ROW FINAL RUNNER + PREREGISTRATION CHAIN LOCALLY VALIDATED; NOT PASSED** | Real frozen suite/costs/outputs, published pre-outcome choices, passing A+B receipts, and one-shot held-out run |
| D — product/API/UI/operations | **V2 AUTHORITATIVE LOADER + DURABLE TEST PATH + DEPLOYMENT CONTRACT LOCALLY VALIDATED; NOT PASSED** | Real pinned A/B/C receipts, hosted TLS/security/operations, provider lifecycle, and final integrated evidence |
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

Public metadata checked before Candidate 3 dispatch showed Candidate 2 run
`33583323178` completed with conclusion `failure` at attempt 3. The tracked
Candidate 2 evidence remains the separately verified attempt-1 and attempt-2
observations above; no attempt-3 artifact or semantic result is claimed here.

### Candidate 3 — runner-only correction, pushed; attempt 2 incomplete

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
both the working repository and a separate no-hardlink clean copy. The authorized
fast-forward then pushed exactly `bb4c15b7…` and the documentation-only
`fd26a52a…` to public `main`; no force push or history rewrite occurred. Offline
Regression run `33589998688` passed at `fd26a52a…`.

The fresh manual Candidate 3 workflow is run `33590028177` at that exact source:
`https://github.com/sasipriya1221/sasipriya1221-ECOCOMMIT/actions/runs/33590028177`.
Attempt 1 passed its independent regression/static job and every Groq
secret-presence check. Seventy-nine case jobs then exited code 75 as typed
provider deferrals; the representative `C001` artifact proves a transient
`candidate_contract_correction_interrupted` / `CORRECTION_PROVIDER_ERROR` after
provider HTTP 429, not a semantic failure. Its artifact ID is `9831406347`; the
downloaded archive SHA-256 exactly matched GitHub's published digest
`481068fb0824dfbc466902c3cef3eeb10e1cc7ad44a83de94ee021d13da21aff`.

One case, `A002`, retained a terminal row. It did not pass: the validator and
expected status were both `CLARIFICATION_REQUIRED`, but the required dependency
condition failed. The aggregate therefore contained one failed terminal row,
79 missing rows, `full_frozen_gate_run=false`, `gate_passed=false`, and no
receipt. Its artifact ID is `9831908998`; the downloaded archive SHA-256 matched
`bc8ae6175e1d1cce424ac0a4ad1a757d5719b88338ec1e9412ea8ab707b650c5`.
The zero values in that partial aggregate are not final metrics and are not a
Candidate 3 semantic score.

The verified manifest still binds Candidate 3, source `fd26a52a…`, run
`33590028177`, frozen dataset SHA-256
`968be3ed3a438a3a28a3402fa65c90a45cb564ed1adad2e6e51d852e24c5bb8b`,
and the unchanged Qwen/JSON-object/1,024-token configuration. Its verified
manifest SHA-256 is
`773cb2efef42c0b94491cb599cb5e0d0a361722fec566ba90fac9e595ee51934`;
that digest is an identity pin, not an A receipt. A
failed-jobs-only attempt 2 began at `2026-09-02T04:40:34Z`. GitHub preserved
the successful `A002` job at its original attempt-1 timestamps and scheduled
only the 79 deferred cases plus the dependent aggregate.

Attempt 2 completed with conclusion `failure` at `2026-09-02T05:05:19Z` because
coverage remained incomplete. It added one genuine passing terminal row,
`C002`: validator and expected status were both `VALIDATED`, every dependency
condition passed, and the retained trace records an HTTP 429 followed by an
accepted response. Its row SHA-256 is
`bec8aafd4467d6a382f40857ebed3c3ce4c78a61cffb910acb922d16bcc07f12`.
The earlier `A002` row was byte-for-byte unchanged with row SHA-256
`5dbfc71fcb1cdebe5ef7c4210b38f8dbbe7e19fb7079686170f302902be78c29`.
The cumulative aggregate therefore has two terminal rows, one pass, one
semantic failure, 78 missing provider-deferred rows,
`full_frozen_gate_run=false`, `gate_passed=false`, and no receipt. Partial
metrics are not a final Candidate 3 score.

Attempt-2 aggregate artifact `9832489831` has verified archive SHA-256
`fcbe84be1211d6a195ff778b6bb0f104dd3b35ae16bd65a4259b857ad935296a`
and JSON SHA-256
`b01a7d5f83beb9018fa25e7cbec7f9ed57e238d9f1e708d5ab2995512e916c76`.
An immediate attempt 3 is not justified: attempt 2 converted only one of 79
deferred cases while pervasive HTTP 429s continued. After confirmed Groq
quota/capacity recovery, continuation may resume only this run's 78 failed jobs.
Checkpoint A remains **BLOCKED / NOT PASSED**.

The local non-mutating Candidate 3 diagnostic strictly recomputes retained rows
and exposes self-consistency separately as `computed_gate_passed`. It can report
authoritative `gate_passed`/`PASSED` or receipt possibility only for an exactly
completed run with all manifest, source, and run-ID pins supplied out of band.
Retry readiness additionally requires a digest-bound healthy-provider
observation no more than 30 minutes old; it never dispatches a retry.

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
is not retroactively upgraded. A fresh exact-source preflight run `33592456896`
then passed at public `fd26a52a…`. Exact-source order-boundary run `33592499084`
created and fetched one INR 1.00 Test order, proved one provider create across
identical replay, found zero attached payments, generated the Checkout handoff,
and truthfully retained `checkpoint_b8_passed=false`, capture not executed, and
blocker `RAZORPAY_CHECKOUT_AUTHORIZATION_REQUIRED`. Its artifact ID is
`9832232980`; the downloaded archive SHA-256 matched GitHub's published
`56ca57750589d41cbf4b9ea717d0b48d7dfb16344702a5f0b6d7d5d1a350000d`.
The generated handoff expires at `2026-09-03T04:53:12.35686Z`; its Checkout HTML
SHA-256 is `ad7c60fd53490693a6fc878a140a21e11be9bccbde997016e385e58c53d97fe5`.

The current manual order-boundary workflow
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

A new local-only B8 finalizer now cross-loads the A receipt, exact-source
preflight/order/handoff, lifecycle, verified webhook set, audit chain,
deterministic safety counts, durability scenarios, and non-secret key-boundary
reference. It derives the B receipt and refuses caller pass booleans, missing or
duplicate strict JSON, cross-artifact ID/amount/digest mismatches, and output
overwrite. Final provider-manifest and receipt publication is atomic, byte-exact
on replay, and recoverable if the process stops after publishing only the first
file. The retained evidence reference must name an exact artifact under the same
GitHub repository. The Checkout callback filename is explicitly ignored and the
runbook moves it immediately under `artifacts/private/`.

The finalizer also requires two owner-produced, non-secret Dashboard
attestations: Test-mode manual capture with an exact three-day timeout and
`NORMAL_REFUND` timeout action, and an enabled HTTPS webhook configuration with
exactly `payment.captured` and `refund.processed`. It binds source revision,
provider-account hash, observation time, screenshot hash, and verifier reference
without retaining the endpoint URL or credentials. Webhook secrets must contain
32–256 visible ASCII bytes and must differ from the API secret. The focused B
finalizer suite passes **25/25** locally.
These controls prepare evidence assembly; no genuine Checkout/capture/refund or
webhook event exists, so B remains **NOT PASSED**.

## Checkpoint C

The V2 preliminary framework remains explicitly synthetic and ineligible for
final claims. It validates comparator registration, deterministic ordering,
TEL accounting, latency/error treatment, provenance, full pair coverage, and
semantic artifact recomputation.

A separate final protocol now requires, before outcomes are observed:

- hashes for the real held-out suite, case identities, metric specification, TEL
  weights, and cost-source manifest;
- passing A and B receipt hashes plus the integrated candidate revision;
- the candidate and comparator execution-protocol hashes plus a separately
  retained comparator-selection receipt hash;
- one exact final execution ID and execution nonce hash, with distinct candidate
  and comparator identities;
- a quantitative TEL-reduction margin, legitimate-completion and selective-
  reliability floors, an autonomous-coverage floor, latency/error/missing-data/
  irreversible-loss ceilings, tie handling, rationale, and statistical method;
- authentic case-result hashes with fixtures, simulated costs, and simulated
  latency structurally forbidden.

No real plan values or results were invented. C remains blocked on the real
inputs, preregistration decisions, A+B, and one-shot held-out execution.
Standalone plan/suite loading now uses the same bounded nonsymlinked strict-JSON
boundary, so duplicate-key or non-standard JSON cannot silently change a frozen
benchmark input.

The local final path is no longer limited to a caller-created metric snapshot. A
write-once `C.FINAL.HELD_OUT.EVIDENCE.1` CLI accepts an out-of-band pinned frozen
registration, exact held-out suite and metric/TEL/cost-source hashes, passing A/B
receipt files, complete candidate/comparator raw decision rows, and paired
write-once execution receipts. The registration freezes one execution ID and
nonce hash before outcomes; both manifests and both attempt-1 receipts must match
them while binding the frozen protocols and comparator selection, complete row
manifests, and exact GitHub Actions artifact references. The runner rejects fixtures/
simulated inputs, enforces exact unique case coverage and the A→B→C revision/hash
chain, re-scores every case, and derives both aggregate snapshots and the
preregistered decision internally. Output publication is atomic and identical
replay returns the same bytes; conflicts fail closed. The C-only test-module
selection passes **56/56**. No real suite, rows, receipts, or one-shot execution
were supplied, so C remains **NOT RUN / BLOCKED**.

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

Local deployment readiness now includes an importable production WSGI entrypoint,
strict environment/forwarded-host policy, provider-neutral nginx/TLS and proxy
templates, request-size and external-rate-limit expectations, and explicit
persistent-volume, backup, monitoring, and secret-injection requirements. These
files also reject transfer-encoded/ambiguous body framing, noncanonical numeric
settings, unbounded/non-ASCII API tokens, and hard-link aliasing between the
mutable state database and append-only audit log. They are configuration
scaffolding only: no listener, DNS, host, certificate, provider route, or paid
service was created.

The authoritative D loader now requires `D.EVIDENCE.PINS.2` and the new raw-row
`C.FINAL.HELD_OUT.EVIDENCE.1`; legacy caller-metric C evidence, old pins,
cross-link mismatches, and re-pinned aggregate tampering fail closed. The focused
D suite passes **111/111**, and the complete local suite passes **468/468**.
Hosted TLS scans,
reverse-proxy rendering on the chosen host, edge controls, backup/restore,
monitoring, real A/B/C receipts, and a hosted integrated run remain **NOT RUN**.

## Checkpoint E and release security

The readiness checker can structurally transition to final-ready: it reads each
evidence slot's `BLOCKED`/`FAILED`/`PASSED` marker, validates a revision-bound
independent-reproduction receipt as a bounded nonsymlinked strict JSON object
with exact source tree/dependency-lock/test-count/readiness-count/report/bundle
digests, distinct verifier and machine bindings, UTC chronology, and an exact
same-repository GitHub Actions artifact reference. It derives completeness from
the counts and self-digest rather than trusting pass booleans, and provides a
strict `--mode final`. It does not
yet substantively reload and verify every underlying final artifact, so marker
promotion alone is not authoritative evidence. Today's real slots remain blocked,
and final readiness remains false.

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

Offline CI now runs for every `main` push and every pull request, removing path-
filter gaps, then runs tests, compilation, JavaScript syntax, dependency
consistency, readiness structure, and diff checks. The readiness manifest makes
the A diagnostic, B/C finalizers, D deployment boundary, deployment templates,
and license-decision plumbing required public files. The lock authorizes exact
published artifact hashes for the supported Linux CI and Windows validation
wheels, including the exact setuptools/wheel build backend required by a fresh
virtual environment; editable project installation uses
`--no-deps --no-build-isolation`.

Public `main` is now exactly `fd26a52a…`, and Offline Regression run
`33589998688` passed that pushed state. Candidate 3 run `33590028177` completed
attempt 2 incomplete with 78 provider deferrals and no A receipt. Final E blockers remain A–D final evidence,
license choice, independent reproduction, final screenshots, and the five-minute
video.

The owner license decision remains **BLOCKED**, not inferred. The prepared option
brief in `docs/LICENSE_DECISION.md` recommends Apache-2.0 for permissive
enterprise/research reuse with express patent terms, while preserving MIT,
AGPL-3.0, and no-license as explicit alternatives. No `LICENSE` file will be
created until the owner chooses.

The existing final evidence slots and five-minute pitch outline remain prepared
but deliberately blocked. They will not be populated with screenshots, metrics,
or video claims until A–D have authoritative retained evidence.

## Non-claims

- Candidate 1 did not pass and will not be retried into a pass.
- Candidate 1 run `33493409547` is completed with failure at attempt 27; it is
  neither resumable evidence nor a replacement for the retained attempt-15 failure.
- Excluded run `33556907712` is completed with failure at attempt 6 and is neither
  an A pass nor a frozen Candidate 2/3 run; none of its attempts or artifacts may be resumed.
- Candidate 2 ran remotely; attempts 1 and 2 remained incomplete and contaminated
  by a runner classification defect. It did not pass and will not be retried.
- Candidate 3 was pushed and run `33590028177` completed attempt 2 incomplete;
  its two terminal rows and 78 provider deferrals are not a complete score or pass.
- Provider deferrals are not semantic failures; contract failures are not
  provider deferrals.
- The Razorpay order subgate is not a payment-lifecycle pass.
- Synthetic B/C/D fixtures are not provider or final comparison evidence.
- No final comparator/TEL numbers, hosted integration, independent reproduction,
  screenshot, or video is claimed.
- The only new remote push was the explicitly authorized fast-forward of
  `bb4c15b7…` and `fd26a52a…`; no later local readiness work is remotely published.
- The new A diagnostic, B finalizer, C raw-row/receipt runner, D V2 loader and
  deployment templates, E receipt verifier, license brief, and truth updates are
  local review work, not public evidence; they have not been pushed.

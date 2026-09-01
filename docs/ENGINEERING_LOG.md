# Engineering Log: What Broke and How It Was Fixed

This log is reconstructed from retained Git history, validation reports, and
failed-run evidence. It records development facts, not a success narrative.
Failed and partial runs remain part of the project record.

## 2026-08-31 — Initial intent boundary

### What broke

The first implementation could represent economic clauses and abstain, but it had
not yet been tested against a real provider or compositional failure modes.

### What changed

- Froze the MVP scope, metric definitions, and Checkpoint A evaluation protocol.
- Added the contract schema, fidelity/ambiguity validator, live-provider
  interface, and a 30-case material-ambiguity suite.
- Kept model output explicitly untrusted; validation, not the model, determines
  whether a candidate can advance.

### Retained evidence and limitation

Commits `eb96f49` through `1888205` establish the first offline boundary. This was
implementation evidence only, not a live Checkpoint A pass.

## 2026-08-31 — Provider transport and first full live failure

### What broke

Initial provider attempts hit HTTP and account/provider constraints. After the
Groq path ran, the first complete semantic run passed only 11/80 cases. Retained
failure classes included invalid source spans, missing material structure,
misclassified ambiguity, incomplete negation/exception/dependency relations, and
uncovered numeric signals.

### How it was fixed

- Added explicit provider diagnostics, preflight checks, a provider-specific user
  agent, bounded retry behavior, and retained failures.
- Grounded source spans against the original instruction and derived explicit
  provenance only from verified spans.
- Made semantic scoring representation-aware instead of requiring one fragile
  surface form.
- Added regressions for every repaired live failure class rather than deleting or
  weakening hard cases.

### Retained evidence and limitation

The failed run and its metrics remain in `PROGRESS.md`. Commits `7696a1b`,
`e7f7d22`, `67f6eee`, and `7e39620` contain the first repair set. A failed live
run was never relabeled as passing.

## 2026-09-01 — Ambiguity, negation, and dependency repairs

### What broke

Open-textured supplier terms could be accepted as if precise; explicit exception
links and dependency conditions were not always preserved; vague comparison and
true prohibition could be conflated.

### How it was fixed

- Classified vague supplier-selection and quality terms as material ambiguity.
- Normalized confidence risk and required explicit dependency structure.
- Preserved exception gates as dependency edges.
- Split vague comparison from genuine negation/prohibition handling.
- Added targeted tests for each repair.

### Retained evidence and limitation

Commits `e4f1fca` through `3f48133` contain these repairs. They improved the local
validator; they did not themselves satisfy the frozen live gate.

## 2026-09-01 — Provider rate windows and schema mode

### What broke

Short backoff logic did not respect long rolling token windows. Strict provider
schema attempts also exposed compatibility and JSON-validation failures. A later
complete 80-row artifact contained HTTP 400 `json_validate_failed` results rather
than valid candidate contracts.

### How it was fixed

- Bounded and serialized requests under provider limits.
- Honored long rate-window hints and classified transient transport failures.
- Added a compact schema, bounded completion budget, Qwen transport probes, and a
  supported JSON-object fallback mode.
- Kept operational/schema failures separate from semantic performance evidence.

### Retained evidence and limitation

The structurally complete failed artifact is retained and described in
`PROGRESS.md`. It is not used as semantic success evidence.

## 2026-09-01 — Resumable frozen evaluation

### What broke

Monolithic/sharded runs lost useful progress when quota or runner timeouts affected
unrelated cases. Re-running completed cases also wasted provider capacity.

### How it was fixed

- Made every frozen case an independently resumable job.
- Retained immutable terminal rows and classified provider-deferred cases
  separately from terminal validation failures.
- Added aggregate integrity checks and failed-jobs-only retry behavior.

### Retained evidence and limitation

Commits `ca4b05c` through `6485d3b` implement this path. The latest recorded state
is partial and Checkpoint A remains not passed; the guarded retry owns further A
progress.

## 2026-09-01 — Checkpoint B safety-boundary validation

### What broke

The initial B kernel exposed several integration risks: a bare A status handoff,
negative approval evidence that could satisfy a tier, mutable evidence identity,
a freshness check/use race, capture without the exact progressive state and hold,
incomplete idempotency identity, and crash windows around capture/refund journals.

### How it was fixed

- Recomputed A fidelity at the A-to-B bridge and required actual accepted A
  evidence before releasing obligations.
- Added exact evidence claim predicates and immutable authority/subject/version
  checks.
- Held the evidence version lock through simulated capture.
- Bound capture to the exact transaction, certificate, `CAPTURE_ALLOWED` state,
  and reservation.
- Included the complete signed request in idempotency identity.
- Added explicit capture/refund recovery and compensation reconciliation.

### Retained evidence and limitation

Commit `6877a81` and `CHECKPOINT_B_VALIDATION.md` retain the validation matrix.
B8/Razorpay, persistence, KMS-grade signing, and real passing A evidence remain
blocked.

## 2026-09-01 — Checkpoint C benchmark-integrity validation

### What broke

The initial comparator harness lacked complete comparator roles, unambiguous
latency provenance, explicit TEL weights/components, full runtime provenance, and
semantic recomputation strong enough to catch internally consistent tampering.

### How it was fixed

- Added all required comparator roles and digest-pinned selection/configuration.
- Separated authorization truth from legitimate-completion truth.
- Added integer TEL weights, deterministic rounding, complete cost components,
  error-row retention, and missing-latency accounting.
- Recomputed decisions, results, summaries, coverage, and provenance during
  artifact validation.
- Added a literal-digest synthetic fixture and prohibited preliminary/final label
  confusion.

### Retained evidence and limitation

Commit `ac2ae83` and `CHECKPOINT_C_VALIDATION.md` retain 41 focused local tests.
The real suite, final TEL rule/weights, authentic outputs, integrated candidate,
and held-out run remain blocked.

## 2026-09-01 — Checkpoint D product validation

### What broke

The D simulation was label-only, metrics accepted non-finite values, audit locks
were instance-local, HTTP parser denials were outside the audit trail, WSGI body
failures were under-specified, and the UI could retain stale gate cards or expose
raw parser errors without correlation status.

### How it was fixed

- Added fixed synthetic success, blocked-A, and capture-failure workflows through
  the real local A-to-B/B state components and `SIMULATED_LOCAL` adapter.
- Rejected non-finite/overflowing metrics and malformed audit rows.
- Shared in-process audit locks by resolved path and covered concurrent appends.
- Audited parser-boundary denials and bounded WSGI failure responses.
- Added a loopback UI/API server, economic-state trace, stale-status reset,
  correlated failure UX, and desktop/mobile browser validation.

### Retained evidence and limitation

Commits `bb70f71` and `b583299` plus `CHECKPOINT_D_VALIDATION.md` retain the local
result. The real commit endpoint still always denies; authoritative gate loading,
provider Test Mode, durability, hosted operations, and final integration remain
blocked.

## 2026-09-01 — Checkpoint B8 Razorpay Test Mode boundary

### What broke or remained unknown

The repository had only `SIMULATED_LOCAL`: no credential preflight, no provider
adapter, no order/payment binding, and no retained Razorpay evidence. Credential
presence alone could not prove valid Test Mode authentication. Razorpay's
server-side Payments API also cannot collect a payment, so an order-only script
could not truthfully manufacture authorization or capture evidence. Razorpay's
default auto-capture behavior conflicts with ECOCOMMIT's delayed capture gate.

### How it was fixed

- Added a read-only, redacted Actions credential preflight that refuses non-test
  key IDs and never prints or retains secret values or provider responses.
- Added an environment-injected Test Mode adapter with a fixed provider origin,
  safe error metadata, exact transaction/order/payment/refund binding, Checkout
  and webhook HMAC verification, ECOCOMMIT-boundary idempotency, ambiguous-order
  recovery, capture-gate preservation, and explicit unsupported-void behavior.
- Kept `SIMULATED_LOCAL` as a separate explicit backend.
- Added manual-only order validation requiring a successful preflight run ID and
  retaining only redacted identifiers, bindings, call paths, and non-claims.
- Added 27 focused adapter/workflow tests covering authentication-header safety,
  binding mutations, signature failures, idempotency collisions/replay, provider
  failures, ambiguous capture, refund states, webhook HMAC, and secret redaction.

### Retained evidence and limitation

Actions preflights `33534255136` and `33535533432` authenticated successfully.
Run `33535533557` created and fetched one INR 1.00 Test order with exact binding
and one create call after identical replay; its redacted artifact is retained as
ID `9811456771` with GitHub SHA-256
`6d8cdcabbc78093f2638c8fbefd2e7bcd4d566d1eb807cd6fa0abf709d700f4d`.
The validator retained `checkpoint_b8_passed=false`. Exact blocker:
`RAZORPAY_CHECKOUT_AUTHORIZATION_REQUIRED`. No payment authorization, capture,
refund, webhook delivery, reconciliation, or settlement ran; manual capture and
webhook configuration remain external prerequisites. Checkpoint A also remains
incomplete, so Checkpoint B is not passed. A fresh same-host clone at
`68d6798ecf1577529a07ef8585bea7d9999bd863` passed all 224 tests, compilation,
dependency consistency, JavaScript syntax, structural readiness checks, and clean
status; this is not independent-machine reproduction.

## Validation-environment incident

One Checkpoint B full-suite attempt failed while pytest created a Windows
temporary directory. It was rerun with a workspace-local isolated `--basetemp`
and passed. The setup incident was recorded as an environment failure, not a
product failure and not passing evidence. Later validation commands keep
`--basetemp` explicit for reproducibility.

## 2026-09-01 — Checkpoint E repository/evidence hardening

### What broke

The public repository had a short status README, no resolved install manifest, no
machine-readable submission-readiness check, no explicit final evidence slots,
and no consolidated failure/fix or demo/pitch material. Architecture text also
overstated audit coverage by implying that every internal B boundary already
emitted D audit events. No license had been selected, and the validated local
commits were not yet present on the public remote.

The first E focused run also exposed a brittle documentation assertion: it looked
for one exact sentence without normalizing Markdown line wrapping, so truthful
wrapped prose failed the test.

The first clean-clone run found a deeper portability defect: on a Windows checkout
with `core.autocrlf=true`, Git converted the three byte-digested Checkpoint C
prompt/guardrail fixtures to CRLF. Their registered SHA-256 values describe LF
bytes, so the clean clone failed one digest-integrity test while the original
working tree passed.

### How it was fixed

- Added a resolved validation dependency manifest and verified a new virtual
  environment can install it and pass the full suite.
- Rebuilt the README around the problem, trust boundary, strict checkpoint truth,
  quick start, demo, evidence, limitations, and explicit missing-license state.
- Added a machine-readable readiness checker for required tracked files, local
  links, portable paths, transient outputs, secret markers, status vocabulary,
  upstream state, and blocked final evidence.
- Added the submission manifest, demo runbook, five-minute pitch, and this
  evidence-backed engineering log.
- Corrected architecture/audit claims and expanded the threat/supply-chain
  boundary.
- Made the documentation regression normalize whitespace so formatting changes do
  not alter the semantic non-claim it protects.
- Added a repository `.gitattributes` rule that forces LF checkout for every
  byte-digested Checkpoint C protocol text file, independent of platform Git
  defaults.

### Retained evidence and limitation

Local repository checks can pass while final submission readiness remains false.
The owner must choose a license; local commits must be pushed intentionally; all
final A/B/C/D metrics/provider/media slots remain blocked; and no independent
machine reproduction has been retained.

## 2026-09-01 — Candidate 1 terminal forensics and Candidate 2 protocol

### What broke

Attempt 15 of run `33493409547` retained 21 semantic passes and 11 terminal
candidate-contract failures. Ten candidates appended a seventh `auth_01` clause
without `materiality` or `confidence`; one omitted `clauses`. The other 48 cases
were genuine provider deferrals. Candidate 1's best possible result was therefore
69/80, below the frozen 72/80 minimum. The earlier resume/aggregate protocol also
identified rows only by case ID, allowed mutable artifact names, trusted stored
semantic detail, and did not bind candidate configuration/source components.

### How it was fixed

- Retained a tracked failure manifest with the run/source/artifact hashes, exact
  case classes, all 48 provider-deferral IDs, and the mathematical upper bound.
- Added a general all-fields prompt rule and provider-ingress presence checking
  before Pydantic defaults; no missing economic value or graph edge is invented.
- Added one bounded model correction, safe candidate/finish/request/usage traces,
  and terminal mixed classification when correction is interrupted by a provider
  error.
- Restricted provider URLs to HTTPS allowlisted hosts, bounded response/error
  reads, redacted failures, and removed command-line API keys.
- Versioned a fresh `A-CANDIDATE-2` manifest binding the frozen dataset, case,
  prompt, schema, evaluator, runner, thresholds, provider configuration, and
  source revision. Resume/aggregate recompute rows, reject conflicts/mixing, use
  immutable attempt artifacts, and emit a typed receipt only after a full pass.
- Added regressions for every observed omission, default-masking risk, correction
  boundary, URL/body safety boundary, manifest/row tampering, duplicate conflict,
  exact threshold, secret scope, and workflow immutability.

### Retained evidence and limitation

Candidate 1 remains failed and is not resume-eligible. Candidate 2 is locally
validated only; it has not been pushed or evaluated remotely and has no
performance result.

## 2026-09-01 — Typed A→B evidence and human Checkout continuation

### What broke

The B bridge accepted any non-empty evidence string in a caller-created passed A
gate. The live B8 workflow could create an order but produced no executable
handoff for the genuinely human-only Checkout step, leaving capture/refund
continuation as a documentation claim rather than a tested software path.

### How it was fixed

- Added a typed A receipt bound to Candidate 2, frozen dataset/thresholds,
  aggregate/manifest/source digests, metrics, and exact evidence reference.
  Production rejects absent/mismatched receipts and explicit test fixtures.
- Added a digest-bound Razorpay Test Checkout handoff containing only public
  client configuration and exact transaction/order binding.
- Added a standalone page that downloads the typed Checkout callback and a
  continuation that verifies its HMAC and provider entities, captures only after
  ECOCOMMIT certificate/TOCTOU checks, compensates with an idempotent refund, and
  reconciles the final state.
- Added processed-refund, tampering, expiry, wrong-order, secret-absence, and
  provider call-sequence regressions.

### Retained evidence and limitation

The existing live evidence still stops at authentication/order creation. The new
Checkout/capture/refund path has fake-transport tests only. A human must confirm
manual capture and perform Test Checkout; webhook configuration/delivery remains
external. No new provider lifecycle outcome is claimed.

## 2026-09-01 — Final C/E contracts and release supply-chain hardening

### What broke

C had no final preregistration/evidence type, so the preliminary-only model could
not represent a legitimate held-out decision without code changes. E's checker
could never become final-ready because it unconditionally inserted blocked
markers and the independent-reproduction blocker. Workflows used mutable action
tags, broad secret environments, incomplete CI path coverage, and provider-body
printing; dependencies were version-pinned but not artifact-hash enforced.

### How it was fixed

- Added a digest-bound, pre-outcome C registration for suite/case/metrics/weights/
  cost hashes, A/B receipt hashes, candidate revision, comparator, TEL margin,
  completion/reliability floors, latency/error/missing/irreversible-loss ceilings,
  tie handling, rationale, and exact-census method. Final evidence recomputes the
  decision and structurally rejects fixture/simulated inputs.
- Changed E evidence slots into parsed states, added a revision-bound independent
  reproduction receipt, and added strict final mode while preserving current
  blocked truth.
- Pinned every workflow action to a full SHA, disabled checkout credential
  persistence, scoped secrets per step, stopped printing provider bodies,
  expanded offline triggers/static checks, and added workflow-policy regressions.
- Replaced the version-only dependency snapshot with binary-only published
  artifact SHA-256 authorization for the supported Linux/Windows validation
  environments and enforced `--require-hashes` in CI.

### Retained evidence and limitation

No final C plan values or results were invented. E remains blocked on real A–D
evidence, license, push, independent reproduction, screenshots, and video. The
hash lock is not a fully offline build bootstrap or provenance attestation.

## 2026-09-02 — Fresh-environment build bootstrap failure

### What broke

The first Candidate 2 clean-clone validation created a standard new virtual
environment and installed every entry in `requirements-dev.lock`, but the lock
omitted the setuptools/wheel build backend named by `pyproject.toml`. Without an
installed `ecocommit` distribution, 260 tests passed and ten failed: Checkpoint C
correctly rejected an incomplete dependency manifest and the D CLI subprocess
correctly failed its package import. Treating the earlier working-environment
pass as sufficient would have hidden a real reproducibility gap.

### How it was fixed

- Downloaded the published pure-Python setuptools 84.0.0 and wheel 0.48.0 wheels,
  verified their SHA-256 digests, and authorized exactly those artifacts in the
  binary-only hash lock.
- Added a workflow-security regression requiring one exact, hashed lock entry for
  each build-backend distribution.
- Updated the reproduction boundary to distinguish a complete fresh virtual
  environment from independent-machine or fully offline attestation.

### Retained evidence and limitation

After installing from the corrected lock, the same no-hardlink clone built the
editable local package without dependency resolution and passed all 270 tests
that existed at that revision. The final tree adds the build-lock guard as test
271. This remains same-host/operator evidence; published-wheel availability and
independent reproduction are still external.

## 2026-09-02 — Authoritative runtime evidence and single-host durability

### What broke or remained unsafe

The D status object still depended on code-supplied gate reports: no runtime
loader could distinguish a pinned real receipt from a fixture or caller-created
model. Payment, commitment, and idempotency state disappeared with the process;
the audit lock coordinated only objects in one interpreter. A crash after a
provider mutation but before the local idempotency result could cause a retry,
and pending compensation could be mistaken for a completed overall operation.

The checkpoint status contract also required E before provider execution. E is
the submission bundle created after D, so this made the integrated D run
architecturally impossible. After separating E, a second cycle remained: D
cannot be evidence required before the provider-Test run that produces D.

Finally, the Razorpay webhook verifier was a detached HMAC helper. There was no
raw-body route, durable provider event-ID deduplication, exact operation binding,
out-of-order capture/refund handling, or redacted webhook evidence export. The D
UI could display simulation only even if an operator safely installed a real
Test operation.

The post-implementation audit then found four recovery/security defects that the
first green suite did not expose. A pending provider refund was intentionally not
called complete, but its adapter result was journaled and the compensation layer
never polled it, so it could not later reach `processed`. Webhook redelivery at a
later local time changed the locally computed record digest and was misclassified
as an event-ID collision. Failed bearer authentication did not consume the rate
limit, and runtime construction could reach the read-only credential preflight
before all evidence and webhook configuration had been validated. Audit rows also
accepted semantically equivalent noncanonical encodings, and an expired handoff
with only a reservation needed a more precise authority boundary.

### How it was fixed

- Added strict Checkpoint B and D receipt schemas and an authoritative loader
  whose pin file requires an out-of-band SHA-256. Every evidence file is hashed
  before parsing; duplicate/nonfinite/unknown/symlinked inputs are rejected; and
  A→B→C→D source/upstream links are recomputed. Status reloads the bundle on
  every request so later file modification fails closed.
- Added SQLite WAL with `synchronous=FULL` for canonical JSON state, optimistic
  CAS, payment and commitment snapshots, typed allowlisted idempotency results,
  stale-lease recovery, and integrity checks. Cross-process regressions prove one
  side effect/result for concurrent callers on the claimed single host.
- Bound Razorpay reserve/capture/refund to that durable state and provider-side
  idempotency. Exact state can reconstruct a result when the mutation commits
  immediately before the result journal. Completed lifecycles resume after
  restart without another provider call; pending compensation is deliberately
  not cached as a terminal D result.
- Added OS-level companion locking around the audit read/verify/append critical
  section and a three-process append regression.
- Separated prerequisites: A–C plus current verified Test runtime may authorize
  the compensated integration run; A–D plus final integration evidence govern
  final D readiness; E remains downstream packaging. The real-money field stays
  permanently false.
- Added a startup-pinned execution adapter. The HTTP route requires an
  environment-only bearer token, a local rate limit, and exactly one opaque
  operation ID. Transaction, callback, receipts, provider configuration,
  credentials, and signing keys cannot come from request JSON. Current Test
  credentials receive a read-only preflight before enablement.
- Added strict provider JSON parsing and a raw webhook endpoint following the
  documented Razorpay HMAC and event-ID headers. `payment.captured` and
  `refund.processed` are bound to the prepared order/payment/amount/currency,
  stored durably, duplicate/collision checked, accepted in either order, and
  exported as a digest-bound set without raw bodies or secrets.
- Added a hidden-by-default operator Test control to the UI. It appears only when
  the server reports the prepared path ready, sends the token only as an
  Authorization header, clears it immediately, and labels the result as
  insufficient by itself for D.
- Made pending refund results non-terminal at both idempotency layers. Retry uses
  Razorpay's exact refund-ID lookup, validates the same payment/amount/currency,
  and advances the durable state only when the provider says `processed`. One
  provider-payment-scoped ledger key prevents different local keys from racing
  two full refunds.
- Restricted post-expiry continuation to exact durable lifecycle state. A
  reservation alone is insufficient unless its matching commitment had already
  persisted `CAPTURE_ALLOWED`; captured/refund states remain recoverable for
  compensation.
- Made webhook deduplication compare stable signed-event fields and return the
  first retained timestamp/digest on redelivery. Changed content under the same
  provider event ID still fails as a collision.
- Moved evidence, repository, and local secret validation before provider
  preflight; rate-limited failed authentication; required canonical strict audit
  JSON; and made sensitive prepared/lifecycle outputs refuse overwrite.

### Regression evidence and limitation

At implementation commit `6f72d9bf2b7dcdc0abfc8aff282cdbbc989bf43e`,
the tree passed 95 Checkpoint B-focused tests, 76 Checkpoint D-focused tests, and
325 total deterministic tests, plus compilation, dependency, and JavaScript
syntax checks. Tests cover evidence tampering, restart/cross-process
state, payment journal crash windows, completed and pending lifecycle replay,
adapter request authority, authentication/rate limiting, strict/canonical JSON,
pending-to-processed refund polling, expiry authority, raw webhook signatures,
late redelivery/collisions/order, and redacted export.

The committed implementation at
`6f72d9bf2b7dcdc0abfc8aff282cdbbc989bf43e` was then cloned without hardlinks,
installed into a new virtual environment from the exact hash lock, and passed
the same 325 tests plus compilation, `pip check`, JavaScript syntax, readiness,
diff, and clean-status checks. That is same-host clean-environment validation,
not independent reproduction.

These new execution paths have local fake-transport and same-host evidence. The
separately retained real Razorpay evidence reaches only Test authentication and
order create/fetch/idempotent replay. No genuine Candidate 2 A receipt, complete
B receipt, final C evidence, provider Checkout/capture/refund, webhook delivery,
public TLS host, managed key, backup/restore, HA, hosted security review, or D
receipt was created. SQLite digests are not protection against an attacker who
can rewrite both a row and its unkeyed digest. The bundled WSGI server remains
loopback development software.

## 2026-09-02 — Checkpoint E evidence-report status drift

### What broke

The Checkpoint E report correctly gained a current-tree addendum as later work
expanded the suite from 197 to 271 and then 325 tests, but its readiness matrix
still called the 197-test clone current. More seriously, an older explicit
non-claim said no Razorpay credential, request, Test transaction, or provider
result had been used. That became false after the retained Test authentication
and order-boundary runs, even though the report elsewhere described the newer
evidence. The contradictory text could understate real evidence and make the
submission record internally unreliable.

### How it was fixed

- Labeled the 197- and 271-test results as historical snapshots rather than
  current evidence.
- Bound the current clean-clone row to the validated 325-test parent revision.
- Replaced the obsolete all-provider non-claim with the exact proven boundary:
  Test authentication plus one INR 1.00 order create/fetch/idempotent replay.
- Kept Checkout authorization, capture, refund, webhook, reconciliation, and
  hosted evidence explicitly unproven.
- Added a regression that requires both the retained order-boundary statement
  and the lifecycle non-claim while forbidding the obsolete contradictory text.

### Regression evidence and limitation

The focused Checkpoint E suite passes with the new truth-consistency assertion.
The working repository and a separate no-hardlink clone at
`fc63416d7e53455285d89837b17680ea2b9e65e7` both pass the resulting 326-test
suite; the clone also passes compilation, dependency consistency, JavaScript
syntax, readiness, diff, and clean-status checks.

The first clone invocation was accidentally started from the shared parent
directory without an explicit test path. Pytest collected identically named
modules from sibling historical clones and correctly stopped with 32 import-file
mismatch collection errors. No repository assertion ran or failed. Rerunning
from the clone root with `tests` explicitly bounded collected exactly 326 tests
and passed all of them. The failed invocation is retained here rather than
silently represented as a product failure or discarded pass.

This corrects repository wording and validation discipline only; it does not
create any new provider, checkpoint, independent-reproduction, or submission
evidence.

## 2026-09-02 — Strict JSON at candidate and final-gate boundaries

### What broke or remained unsafe

Candidate 2 parsed both the provider envelope and the model's nested candidate
with Python's permissive JSON defaults. Duplicate keys could therefore overwrite
earlier values silently, while NaN/Infinity and invalid Unicode scalar values
could take parser-specific paths before schema validation. A resume or aggregate
artifact used the same permissive decoding and had no file-size or symlink
boundary. The source revision bound the implementation, but the runner digest
did not directly enumerate the interpreter, strict decoder, protocol, or typed
A-receipt code.

The standalone C plan/suite loader and E independent-reproduction receipt also
used permissive decoding. In E, duplicate boolean fields could be normalized to
the last value before the final-readiness decision. This did not create a false
pass in retained evidence—every current slot remains blocked—but it was an
unacceptable future parser-differential surface.

### How it was fixed

- Added a shared strict decoder that rejects duplicate object names,
  NaN/Infinity, invalid Unicode surrogates, excessive depth/node counts, and
  malformed JSON without retaining input values.
- Applied it to provider envelopes and nested Candidate 2 content. Candidate
  JSON defects receive the existing single bounded correction opportunity and
  remain distinct from malformed provider envelopes.
- Made A resume/aggregate inputs bounded, nonsymlinked, strict UTF-8 JSON objects
  and made canonical A hashing forbid non-finite values.
- Expanded the A runner digest to include the interpreter, strict decoder,
  protocol, shard, aggregate, constants, and typed receipt implementation.
- Applied bounded nonsymlinked strict-object loading to standalone C plan/suite
  files and the E reproduction receipt; E additionally requires exactly the
  typed receipt fields.
- Added adversarial tests for duplicate candidates and envelopes, non-finite and
  invalid-Unicode candidates, strict A artifacts and resume behavior, manifest
  runtime coverage, duplicate C inputs, and malformed E receipts.

### Regression evidence and limitation

The focused Candidate 2/provider suite passes **44/44**, the focused C suite
passes **47/47**, the focused E suite passes **13/13**, and the full suite passes
**342/342** in both the working repository and a no-hardlink clone at
`3ea35a8a64e5f7eaa65f05c7c720b43d5658958b`. The clone also passes compilation,
dependency consistency, JavaScript syntax, readiness, diff, and clean-status
checks.

The first combined focused run stopped during collection because the newly
parametrized E test used `pytest` without importing it. No product assertion ran
or failed. Adding the missing test import made the identical 70-test combined
scope pass; the failed harness invocation is retained here rather than hidden.

Strict parsing protects interpretation of evidence; it does not authenticate an
independent reproducer, supply real C inputs, make Candidate 2 run remotely, or
turn any blocked checkpoint into a pass.

## 2026-09-02 — Recovered provider retries missing from Candidate 2 chronology

### What broke or remained unsafe

Candidate 2 retried transient HTTP 429/5xx and transport failures, but provider
errors were appended to `provider_trace` only on terminal failure branches. A
retryable attempt was therefore omitted before each retry. Whether a later
attempt succeeded or failed terminally, that earlier failure disappeared from
retained metadata. A mixed schema-correction/provider-retry sequence could
therefore show an incomplete chronology even though its final semantic result
was correct.

This was an evidence-completeness defect, not a benchmark failure or a change to
the frozen evaluator. Candidate 2 has not run remotely, and Candidate 1's retained
terminal evidence was not modified.

### How it was fixed

- Record each retryable HTTP or transport failure before sleeping and retrying.
- Retain only the attempt number, redacted outcome/error class, and transient
  flag; provider bodies, prompts, and credentials remain absent.
- Preserve the subsequent accepted or terminal attempt in order, including a
  schema-invalid candidate followed by a transient failure and successful
  correction.
- Added regressions for recovered HTTP 429, recovered transport failure, and the
  mixed schema-invalid → HTTP 503 → accepted chronology.

### Regression evidence and limitation

The focused Candidate 2/provider suite passes **45/45**. The full suite passes
**343/343** in both the working repository and a no-hardlink clone at
`13fcdbf0e1b12595a146d5518cc0683899e12cbe`. The clone also passes compilation,
dependency consistency, JavaScript syntax, readiness, diff, and clean-status
checks.

This is same-host deterministic evidence. It does not prove external provider
behavior, run Candidate 2, fill any final evidence slot, or change any checkpoint
to passed.

## 2026-09-02 — Terminal schema failure falsely labeled as corrected

### What broke or remained unsafe

The provider request limit is shared by transport retries and the single bounded
schema-correction opportunity. If a transient provider failure consumed an early
attempt and the final allowed response was the first schema-invalid candidate,
no correction request ran. `CandidateContractError` nevertheless always said the
candidate failed after correction, and the live evaluator always emitted
`SCHEMA_INVALID_AFTER_CORRECTION`.

The provider trace still exposed the actual order, so this could be reconstructed
manually, but the terminal classification itself was false. This did not affect
Candidate 1 evidence and Candidate 2 has not run remotely.

### How it was fixed

- `CandidateContractError` now carries immutable `correction_attempted` state.
- The interpreter sets it from the actual correction state-machine branch.
- The live row retains that boolean and emits
  `SCHEMA_INVALID_BEFORE_CORRECTION` or `SCHEMA_INVALID_AFTER_CORRECTION`
  accordingly.
- Regressions cover both terminal phases and the concrete transient transport →
  first schema-invalid exhaustion sequence.

### Regression evidence and limitation

The first red test run produced the expected two failures because the old error
object had no correction-attempt state. After the fix, the focused Candidate 2/
provider suite passes **48/48** and the full suite passes **346/346** in both the
working repository and a no-hardlink clone at
`e616ce47a86f91af9810f089bd4ed5ee0ebd7849`. The clone also passes compilation,
dependency consistency, JavaScript syntax, readiness, diff, and clean-status
checks.

The fix makes evidence truthful; it does not increase the configured provider
request budget, promise that correction is always available during an outage,
run Candidate 2, or change any checkpoint to passed.

## 2026-09-02 — Razorpay credentials exposed to a non-provider summary step

### What broke or remained unsafe

The manual Razorpay order-boundary workflow correctly scoped secrets at step
level, but it injected both the Test key ID and secret into two steps. The second
step only rendered the redacted summary and repeated a credential-string check
already enforced by `checkpoint_b8_razorpay_live.py` before evidence is written.
That duplicate check unnecessarily enlarged the credential exposure surface.

### How it was fixed

- Removed both Razorpay credentials from the summary step.
- Kept the credential-value rejection inside the one provider-execution step,
  before the redacted evidence file is written.
- Added a workflow regression requiring exactly one lifecycle reference to each
  Razorpay secret. The subsequent artifact-upload action also receives neither
  credential.

### Regression evidence and limitation

The red workflow test failed because each secret appeared twice. After the fix,
the same test passes, the focused B suite passes **95/95**, and the full suite
passes **346/346** in both the working repository and a no-hardlink clone at
`813bc82c5ea1a726fc95bebe076a003f5a42a5c8`. The clone also passes compilation,
dependency consistency, JavaScript syntax, readiness, diff, and clean-status
checks.

This narrows future workflow exposure. It does not revoke or inspect repository
secrets, rerun the historical order boundary, execute Checkout, or prove the
capture/refund/webhook lifecycle.

## Log discipline

- New failures are appended; old failures are not erased.
- A fix must name its regression coverage and residual limitation.
- Provider deferral, application failure, semantic failure, and acceptance
  failure are distinct categories.
- A local pass never becomes an integrated or checkpoint pass through wording.

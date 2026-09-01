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

## Log discipline

- New failures are appended; old failures are not erased.
- A fix must name its regression coverage and residual limitation.
- Provider deferral, application failure, semantic failure, and acceptance
  failure are distinct categories.
- A local pass never becomes an integrated or checkpoint pass through wording.

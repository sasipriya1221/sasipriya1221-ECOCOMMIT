# Checkpoint A Live Evaluation Runbook

Checkpoint A is intentionally blocked unless a real configured model is called.
Mocked provider fixtures do not count. Candidate 1 is permanently failed and
Candidate 2 exposed a provider/correction resumability defect; this runbook now
describes the fresh runner-only correction `A-CANDIDATE-3`.

## Secure credential setup

The current GitHub Actions configuration uses Groq's OpenAI-compatible endpoint. Create a GitHub Actions repository secret named:

`ECOCOMMIT_GROQ_API_KEY`

Do **not** commit the key to the repository, issue, README, workflow, or benchmark artifact.
The provider client stores the bearer value as an unredirected request header and
rejects a changed final response URL as terminal `REDIRECT_REJECTED`; a redirect
must never be treated as a provider result or retried as a transient failure.

Current committed live configuration:

- base URL: `https://api.groq.com/openai/v1`
- model: `qwen/qwen3.6-27b`
- reasoning effort: `none`
- structured output: JSON object mode; strict JSON Schema mode disabled
- maximum completion budget: 1,024 tokens per request
- live-request scheduling: one immutable case per job, with at most two case
  jobs running in parallel
- per-case provider retry bound: two attempts, with a 15-second delay ceiling

The model, endpoint, reasoning effort, structured-output mode, completion budget,
prompt, schema, evaluator, runner, criteria, dataset, and source revision are
bound into the Candidate 3 evidence manifest. Changing any of them creates a
different candidate and conflicting artifacts are rejected.

Candidate 3 is a fresh 80-case evaluation. Never place a Candidate 1 or Candidate
2 artifact in its resume directory. Candidate 1's attempt-15 failure is retained in
`evidence/checkpoint-a-candidate-1-failure.json`.

Candidate 2 genuinely ran as workflow run `33583323178` from source
`c52884eb455c1858608d430aa2d14b1d31a9fa12`. Attempt 1 retained 78 code-75
provider deferrals and only two terminal rows; neither terminal row passed. One
was a provider HTTP 429 that the runner incorrectly terminalized after a
correction interruption, while the other was schema-invalid before its promised
correction could run. The immutable observation is
`evidence/checkpoint-a-candidate-2-attempt-1.json`. A failed-jobs-only attempt 2
added one proven pass and one more pre-correction error but left 76 provider
deferrals; its terminal observation is
`evidence/checkpoint-a-candidate-2-attempt-2.json`. Candidate 3 changes only the
runner classification and fresh artifact namespace; it does not change the
dataset, prompt, evaluator, model configuration, schemas, or thresholds.

Before dispatching Candidate 3, confirm obsolete run `33493409547` is no longer
active. It was observed queued as Candidate 1 attempt 27 after Candidate 1 had
already become mathematically incapable of passing. Public metadata checked at
`2026-09-02T02:23:34Z` reports it completed with conclusion `failure` at attempt
27, so no cancellation is currently required. Do not rerun it and do not use
any later artifact from it to replace the retained attempt-15 failure.

Remote run `33556907712` is also not a Candidate 2 or Candidate 3 attempt. It used an earlier
runner plus a rejected score-filling experiment, produced only partial provider
deferrals before its retained attempt-1 cancellation, and failed aggregation.
Later reruns do not change its identity; public metadata checked at
`2026-09-02T02:23:34Z` reports conclusion `failure` at attempt 6. Its observations
are retained separately in `evidence/checkpoint-a-run-33556907712-cancelled.json`
and `evidence/checkpoint-a-pre-dispatch-run-status.json`; none of its rows or
artifacts may enter a Candidate 3 resume directory.

## Preflight

The repository's current **Groq Provider Preflight** workflow still targets the
earlier `openai/gpt-oss-120b`, `low`, 2,048-token configuration. It is not an
exact preflight for the frozen Qwen evaluation above and must not be cited as
proof of that configuration's provider/schema plumbing. Any preflight pass is
operational evidence only and does not count toward Checkpoint A metrics.

## Run

After the workflow exists on the pushed default branch, use GitHub → Actions →
**Checkpoint A - Live Intent Evaluation** → Run workflow. All secret-bearing
workflows are manual-only; pushing source or editing a legacy sentinel must not
start a provider request.

The full workflow performs, in order:

1. clean checkout;
2. dependency install;
3. full offline pytest regression suite;
4. Groq secret-presence check;
5. live model run across 80 procurement cases (50 clear + 30 materially ambiguous);
6. manifest and row verification plus full semantic recomputation;
7. compact failure diagnostics; and
8. immutable result upload, with a typed A receipt emitted only if the full gate passes.

A separate **Checkpoint A - Development Smoke** workflow runs a 10-clear + 10-ambiguous subset for development diagnostics. A smoke result can guide fixes but can never mark Checkpoint A passed.

## Frozen Checkpoint A gate

All four must pass in the same full real-model run:

- case pass rate >= 90%
- selective semantic reliability >= 95%
- autonomous coverage >= 55%
- ambiguous clarification accuracy >= 80%

These thresholds are frozen. They must not be lowered after seeing results.

## Important scope note

This is the Checkpoint A development gate, not the final M8 held-out benchmark. The final benchmark is created and frozen later under the M8 protocol and must not be tuned against.

## Result handling

If the workflow fails the gate, Checkpoint A remains failed. Retain the artifact,
use its diagnostics to isolate a general implementation defect, add regression
tests, and create a separately versioned candidate only when the evidence
justifies a general correction. Do not delete difficult cases, change expected
outcomes to fit the model, hard-code benchmark answers, or lower thresholds.

Every provider candidate must explicitly contain the complete top-level contract
and every required clause field. The local runtime may recompute exact source
offsets for model-supplied text, but it does not manufacture missing economic
fields or graph edges. One schema-invalid candidate receives at most one bounded
model correction request. A second invalid candidate is terminal. If the
correction request itself ends in a transient provider error, both facts are
retained but the case remains a provider deferral rather than becoming terminal
semantic evidence. A non-transient provider rejection remains terminal.
If earlier provider retries exhaust the request budget before the first invalid
candidate can be corrected, the row explicitly records that correction was not
attempted; when its trace proves a transient provider interruption, the case is
resumable so it can receive the promised correction opportunity. A completed
bounded correction that remains schema-invalid is terminal.

Provider envelopes and candidate content are decoded as bounded strict JSON.
Duplicate keys, NaN/Infinity, invalid Unicode scalar values, and excessive
structure are rejected rather than normalized by the parser; a candidate-level
failure follows the same one-correction limit. Resume and aggregate artifacts
must also be bounded nonsymlinked strict UTF-8 JSON objects. The manifest directly
hashes the candidate interpreter, strict decoder, protocol, shard, aggregate,
and typed A-receipt code in addition to binding the source revision.

Provider failures are evidence too. Groq's HTTP 429/5xx responses are retried
with bounded backoff using the provider `Retry-After` window; transient transport
failures are also retried. Every attempted provider turn, including a transient
failure that later recovers, remains in the redacted per-attempt chronology; no
provider body or credential is retained. If one remains unavailable, that case
records an infrastructure error without a semantic row and exits nonzero.
Redirect rejection is non-transient and retains only the redacted failure code.

Resume Candidate 3 by re-running only failed jobs in the same workflow run.
Every attempt uses a unique artifact name. The runner accepts only rows with the
same manifest and case digests, skips transient provider deferrals even when they
interrupt correction or consume the pre-correction request budget, permits
identical duplicate rows, and rejects conflicts. Completed terminal rows are
immutable. Non-transient provider responses, completed correction failures, and
local contract-validation failures are terminal evidence. Provider failures are
never replaced with fixtures.

Aggregation must read every shard through the strict verifier. It recomputes
contracts, validator reports, semantic decisions, metrics, missing IDs, and the
exact frozen gate. A passing receipt binds the result artifact SHA-256, manifest,
source revision, Candidate 3 identity, frozen dataset, and metrics; a partial or
failed aggregate cannot emit that receipt.

Free-tier token-per-day exhaustion can make a smoke artifact mostly operational rather than semantic evidence. Such an artifact must still be retained and reported, but it must not be presented as an estimate of model accuracy when most cases never received a model result.

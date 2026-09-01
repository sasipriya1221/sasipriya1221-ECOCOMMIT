# Checkpoint A Live Evaluation Runbook

Checkpoint A is intentionally blocked unless a real configured model is called.
Mocked provider fixtures do not count. Candidate 1 is permanently failed; this
runbook now describes the fresh `A-CANDIDATE-2` evaluation.

## Secure credential setup

The current GitHub Actions configuration uses Groq's OpenAI-compatible endpoint. Create a GitHub Actions repository secret named:

`ECOCOMMIT_GROQ_API_KEY`

Do **not** commit the key to the repository, issue, README, workflow, or benchmark artifact.

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
bound into the Candidate 2 evidence manifest. Changing any of them creates a
different candidate and conflicting artifacts are rejected.

Candidate 2 is a fresh 80-case evaluation. Never place a Candidate 1 artifact in
its resume directory. Candidate 1's attempt-15 failure is retained in
`evidence/checkpoint-a-candidate-1-failure.json`.

## Preflight

The repository's current **Groq Provider Preflight** workflow still targets the
earlier `openai/gpt-oss-120b`, `low`, 2,048-token configuration. It is not an
exact preflight for the frozen Qwen evaluation above and must not be cited as
proof of that configuration's provider/schema plumbing. Any preflight pass is
operational evidence only and does not count toward Checkpoint A metrics.

## Run

GitHub → Actions → **Checkpoint A - Live Intent Evaluation** → Run workflow, or update the committed trigger file when an audited rerun is required.

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
correction request itself ends in a provider error, both facts are retained and
the row is terminal rather than misclassified as a pure provider deferral.

Provider failures are evidence too. Groq's HTTP 429/5xx responses are retried
with bounded backoff using the provider `Retry-After` window; transient transport
failures are also retried. If one remains unavailable, that case records an
infrastructure error without a semantic row and exits nonzero.

Resume Candidate 2 by re-running only failed jobs in the same workflow run.
Every attempt uses a unique artifact name. The runner accepts only rows with the
same manifest and case digests, skips pure transient provider deferrals, permits
identical duplicate rows, and rejects conflicts. Completed terminal rows are
immutable. Non-transient provider responses, interrupted corrections, and local
contract-validation failures are terminal evidence. Provider failures are never
replaced with fixtures.

Aggregation must read every shard through the strict verifier. It recomputes
contracts, validator reports, semantic decisions, metrics, missing IDs, and the
exact frozen gate. A passing receipt binds the result artifact SHA-256, manifest,
source revision, Candidate 2 identity, frozen dataset, and metrics; a partial or
failed aggregate cannot emit that receipt.

Free-tier token-per-day exhaustion can make a smoke artifact mostly operational rather than semantic evidence. Such an artifact must still be retained and reported, but it must not be presented as an estimate of model accuracy when most cases never received a model result.

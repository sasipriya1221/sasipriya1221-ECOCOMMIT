# Checkpoint A Live Evaluation Runbook

Checkpoint A is intentionally blocked unless a real configured model is called. Mocked provider fixtures do not count.

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

The model, endpoint, reasoning effort, structured-output mode, and completion
budget are frozen for the current 80-case evaluation. Changing any of them
creates different provider evidence and is not a resume of the same evaluation.

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
6. compact failure diagnostics;
7. machine-readable artifact upload.

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

If the workflow fails the gate, Checkpoint A remains red. Retain the failed artifact, use its diagnostics to isolate implementation defects, add regression tests, and rerun. Do not delete difficult cases, change expected outcomes to fit the model, or lower thresholds to manufacture a pass.

Provider failures are evidence too. Groq's HTTP 429/5xx responses are retried
with bounded backoff using the provider `Retry-After` window, including longer
rolling token windows; transient transport failures are also retried. If one of
those transient classes remains unavailable after bounded attempts, that
single-case job records the infrastructure error without a semantic case row and
exits nonzero. Resume by re-running only failed jobs in the same workflow run.
Completed case artifacts are immutable inputs to later aggregation and must not
be replayed. Do not start a new full workflow run to retry provider-deferred
cases. Non-transient provider responses and local contract-validation failures
are terminal failed case evidence and are not eligible for a provider-deferred
retry. Provider failures are never replaced with fixtures.

Free-tier token-per-day exhaustion can make a smoke artifact mostly operational rather than semantic evidence. Such an artifact must still be retained and reported, but it must not be presented as an estimate of model accuracy when most cases never received a model result.

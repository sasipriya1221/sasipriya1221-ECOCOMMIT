# Checkpoint A Live Evaluation Runbook

Checkpoint A is intentionally blocked unless a real configured model is called. Mocked provider fixtures do not count.

## Secure credential setup

The current GitHub Actions configuration uses Groq's OpenAI-compatible endpoint. Create a GitHub Actions repository secret named:

`ECOCOMMIT_GROQ_API_KEY`

Do **not** commit the key to the repository, issue, README, workflow, or benchmark artifact.

Current committed live configuration:

- base URL: `https://api.groq.com/openai/v1`
- model: `openai/gpt-oss-120b`
- reasoning effort: `low` for the extraction workload
- structured output: strict JSON Schema mode
- maximum completion budget: 2,048 tokens per request
- live-request concurrency: serialized (`workers=1`)

The model and endpoint are explicit workflow configuration; changing them creates different provider evidence and must be recorded with the resulting benchmark artifact.

## Preflight

Before spending a smoke/full benchmark budget, the **Groq Provider Preflight** workflow exercises the actual `OpenAICompatibleIntentProvider` with one procurement instruction. It runs the full offline regression suite first, verifies the secret is present, sends the same structured-output configuration used by the live workflows, validates the returned `EconomicIntentContract`, and runs the deterministic fidelity validator.

A preflight pass proves provider/schema plumbing only. It does not count toward Checkpoint A metrics.

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

Provider failures are evidence too. Groq's HTTP 429/5xx responses are retried with bounded backoff using the provider `Retry-After` window, including longer rolling token windows; transient transport failures are also retried. If the provider remains unavailable after bounded attempts, affected cases fail rather than being replaced with fixtures.

Free-tier token-per-day exhaustion can make a smoke artifact mostly operational rather than semantic evidence. Such an artifact must still be retained and reported, but it must not be presented as an estimate of model accuracy when most cases never received a model result.

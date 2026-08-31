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

The model and endpoint are explicit workflow configuration; changing them creates different provider evidence and must be recorded with the resulting benchmark artifact.

## Run

GitHub → Actions → **Checkpoint A - Live Intent Evaluation** → Run workflow, or update the committed trigger file when an audited rerun is required.

The workflow performs, in order:

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

Provider failures are evidence too. Groq's rate-limit responses are retried with bounded backoff using the provider `Retry-After` window; transport failures are also retried. If the provider remains unavailable after the bounded attempts, affected cases fail rather than being replaced with fixtures.

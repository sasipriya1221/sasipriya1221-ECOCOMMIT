# Checkpoint A Live Evaluation Runbook

Checkpoint A is intentionally blocked unless a real OpenAI-compatible model is called. Mocked provider fixtures do not count.

## Secure credential setup

Create a GitHub Actions repository secret named:

`ECOCOMMIT_LLM_API_KEY`

Do **not** commit the key to the repository, issue, README, workflow, or benchmark artifact.

The workflow also accepts two manual inputs:

- `base_url` — OpenAI-compatible API base URL, e.g. `https://api.openai.com/v1`
- `model` — the exact model name exposed by that endpoint

## Run

GitHub → Actions → **Checkpoint A - Live Intent Evaluation** → Run workflow.

The workflow performs, in order:

1. clean checkout;
2. dependency install;
3. full offline pytest regression suite;
4. secret-presence check;
5. live model run across 80 post-prompt-freeze procurement cases (50 clear + 30 materially ambiguous);
6. machine-readable artifact upload.

## Frozen Checkpoint A gate

All four must pass in the same run:

- case pass rate >= 90%
- selective semantic reliability >= 95%
- autonomous coverage >= 55%
- ambiguous clarification accuracy >= 80%

These thresholds are frozen before the live run. They must not be lowered after seeing results.

## Important scope note

This is the Checkpoint A development gate, not the final M8 held-out benchmark. The final benchmark is created and frozen later under the M8 protocol and must not be tuned against.

## Result handling

If the workflow fails the gate, Checkpoint A remains red. Record the failure categories, fix root causes, add regression tests, and rerun. Do not delete difficult cases or lower thresholds to manufacture a pass.

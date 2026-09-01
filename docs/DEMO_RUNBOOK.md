# Demo Runbook

This runbook covers the current local safety-console demo. It does not substitute
for the final integrated demo or video, both of which remain blocked in
`SUBMISSION_EVIDENCE.md`.

## Preflight

1. Use a clean checkout at the intended demo commit.
2. Install the resolved validation dependencies using `REPRODUCIBILITY.md`.
3. Run the full deterministic suite.
4. Run the Checkpoint E readiness checker and read its blockers.
5. Confirm that no real provider credential is loaded for the local demo.

```powershell
git status --short
.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .test-tmp-demo
.venv\Scripts\python.exe scripts\checkpoint_e_readiness.py
```

## Start the local console

```powershell
.venv\Scripts\python.exe scripts\checkpoint_d_server.py --port 8765
```

Open `http://127.0.0.1:8765/`. The expected banner is:

`SIMULATION MODE — NO PROVIDER CALLS · NO MONEY MOVEMENT`

Every A–E card must remain blocked because the local server deliberately loads no
authoritative gate evidence. The real-money card must remain disabled.

## Demonstration sequence

### 1. Happy-path composition

Select `HAPPY_PATH` and run the simulation.

Expected visible signals:

- outcome `SIMULATED_CAPTURED`;
- requested `INR 40.00`, policy cap `INR 50.00`, simulated capture `INR 40.00`;
- stages `PROPOSED -> AUTHORIZED -> RESERVED -> CAPTURE_ALLOWED -> CAPTURED`;
- every label still says simulation/local; and
- the global commit status remains blocked.

Narration: this proves local component composition only. The A gate is a fixed
synthetic fixture, the signer uses a local test key, and the payment is an
in-memory simulator.

### 2. Upstream gate denial

Select `CHECKPOINT_A_BLOCKED`.

Expected visible signals:

- outcome `SIMULATED_BLOCKED`;
- A-to-B blocker `CHECKPOINT_A_BLOCKED`;
- authorized and captured amounts both zero;
- final commitment state `PROPOSED`; and
- no payment activity.

Narration: a valid-looking contract alone cannot release economic authority.

### 3. Failure and cleanup

Select `CAPTURE_FAILURE`.

Expected visible signals:

- outcome `SIMULATED_FAILED_CLOSED`;
- captured amount zero;
- final state `FAILED`;
- cleanup `SIMULATED_HOLD_VOIDED`; and
- a visible correlation ID.

Narration: the reversible simulated hold is cleaned up; there is no hidden
fallback capture.

## CLI fallback

If the browser cannot be used, run the same deterministic scenarios as JSON:

```powershell
.venv\Scripts\python.exe scripts\checkpoint_d_demo.py --scenario HAPPY_PATH
.venv\Scripts\python.exe scripts\checkpoint_d_demo.py --scenario CHECKPOINT_A_BLOCKED
.venv\Scripts\python.exe scripts\checkpoint_d_demo.py --scenario CAPTURE_FAILURE
```

The fallback is acceptable for local engineering review. It is not a replacement
for final hosted product evidence.

## Stop conditions

Stop the demo and state the blocker if any of these occurs:

- a gate card appears passed without an authoritative evidence reference;
- the real commit path becomes ready;
- a response omits the simulation label;
- a captured amount appears in a blocked or injected-failure scenario;
- a secret, provider credential, or live/test provider call is requested; or
- the source revision/working-tree state is unknown.

## Final demo/video gate

The final submission recording must be made only after A/B/C/D are integrated and
their required evidence is retained. At that point, replace this local sequence
with the final run, record the exact source revision and evidence digests, and
update the blocked media slots in `SUBMISSION_EVIDENCE.md`. Until then, do not add
a video URL or present local screenshots as final evidence.

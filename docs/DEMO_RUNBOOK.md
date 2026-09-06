# Demo Runbook

This runbook records a five-minute reviewer demonstration of the runnable local
safety console. It proves product composition and fail-closed behavior. It does
not substitute local simulation for authoritative checkpoint receipts.

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

## Five-minute recording timeline

| Time | Show | Say |
|---:|---|---|
| 0:00–0:35 | Repository root, README and test command | “ECOCOMMIT separates probabilistic interpretation from deterministic economic authority.” |
| 0:35–1:05 | Start the server and open the console | “This is an intentionally labelled local simulation: no provider calls and no money movement.” |
| 1:05–2:05 | `HAPPY_PATH` | Point out the cap, certificate-controlled state sequence, simulated capture and audit correlation ID. |
| 2:05–2:55 | `CHECKPOINT_A_BLOCKED` | Show that a plausible contract cannot execute without an authoritative upstream receipt; authorized and captured amounts remain zero. |
| 2:55–3:45 | `CAPTURE_FAILURE` | Show the failed state, zero capture and simulated hold cleanup. |
| 3:45–4:25 | Architecture and trust boundary | Explain that the model proposes semantics while validation, evidence, state transitions, idempotency and payment authority are deterministic. |
| 4:25–5:00 | Failure-recovery document and current status | Summarize OTPM diagnosis, Candidate-7 semantic failure, Candidate-8 development, and the decision not to fabricate checkpoint PASS states. |

Keep the browser zoom high enough that the simulation banner, outcome, amounts,
state sequence and correlation ID remain readable. Do not show secrets, local
environment files, provider dashboards, payment credentials or real financial
information.

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

## Evidence wording for the recording

Call this a **runnable local product demonstration**. Do not call it a completed
Razorpay lifecycle or an A/B/C/D/E PASS. If a later authoritative receipt exists,
show its exact source revision and digest separately; otherwise keep the relevant
checkpoint visibly BLOCKED or NOT RUN.

# ECOCOMMIT Submission Evidence

This is the judge-facing evidence index. A green workflow, local demo,
screenshot or narrative cannot promote a checkpoint. Typed receipts and
source-bound retained artifacts are authoritative.

## Current verdict

**Runnable product LOCALLY VALIDATED. Candidate 8 and Checkpoints A–E NOT
PASSED.**

The local console is a safe deterministic simulation. Candidate 8 is still in
visible development. No final Razorpay lifecycle, held-out comparator experiment
or hosted integrated proof is claimed.

No final ECOCOMMIT-versus-baseline numbers are available. No final screenshot is
retained. No final video is recorded. For the fresh final lifecycle, no payment
authorization, capture, refund, webhook delivery, reconciliation, or settlement
was executed.

## Current evidence matrix

| Evidence boundary | State | Authoritative reference |
|---|---|---|
| Local product | **LOCALLY VALIDATED** | `HAPPY_PATH`, `CHECKPOINT_A_BLOCKED` and `CAPTURE_FAILURE` in `scripts/checkpoint_d_demo.py` and the local console |
| Candidate 7 | **FAILED** | Run `33957313516`; artifact `9966909942`; D003 0/5, D009 5/5; zero provider/schema failures |
| Candidate 8 iteration 1 | **DEVELOPMENT FAIL** | Run `33959690847`; source `1600a9d7d8f469d2b948f8b4ec0b548e4cae1c48`; 6/24 (25%) |
| Candidate 8 iteration 2 | **DEVELOPMENT FAIL** | Run `33965955682`; artifact `9970125633`; source `eabf660b...`; 18/24 (75%) |
| Candidate 8 iteration 3 | **DEVELOPMENT NOT READY** | Run [`33970539713`](https://github.com/sasipriya1221/sasipriya1221-ECOCOMMIT/actions/runs/33970539713); source `b540de4998769cc0dd6e3a220fa00abeb8a3ce72`; artifact `9971456984`; digest `sha256:11a9b21340b549d4b9bc7b6f4328c80c86784123c1d930b8e7483a6215b403f1` |
| Candidate 8 regression/preflight/qualification | **NOT RUN** | Locked behind a complete visible-development PASS |
| Checkpoint A | **BLOCKED / NOT PASSED** | No qualified candidate and no typed A PASS receipt |
| Checkpoint B | **FINAL EXECUTION BLOCKED** | Deterministic implementation exists; no eligible A receipt or fresh final Razorpay Test lifecycle |
| Checkpoint C | **FINAL EXPERIMENT BLOCKED** | Comparator/TEL infrastructure exists; no passing A+B receipt chain |
| Checkpoint D | **LOCAL DEMO ONLY / FINAL PROOF BLOCKED** | Runnable simulation exists; no authoritative A/B/C integration or hosted proof |
| Checkpoint E | **PACKAGE READY / FINAL EVIDENCE BLOCKED** | Repository, license, lock, architecture, threat model and runbook exist; gated receipts remain absent |

## Candidate-8 iteration-3 metrics

The retained `summary.json` reports:

| Metric | Observed | Development requirement | Result |
|---|---:|---:|---|
| Case pass | 23/24 = 95.83% | >= 95% | Met |
| Selective semantic reliability | 100% | >= 97% | Met |
| Autonomous coverage | 79.17% | >= 60% | Met |
| Ambiguous clarification accuracy | 100% | >= 90% | Met |
| Provider deferrals | 0 | 0 | Met |
| Schema/validation failures | 0 | 0 | Met |
| Conservation failures | 0 | 0 | Met |
| Fail-open outcomes | 0 | 0 | Met |
| Dropped guards | 1 | 0 | **Failed** |

C8D020 was rejected with `C8_UNRESOLVED_ENTITY_DISPOSITION`. It authorized no
economic action, but its material guard was unresolved. The artifact correctly
records `passed: false`.

## Runnable demo evidence

The local console must visibly retain:

- `SIMULATION MODE — NO PROVIDER CALLS · NO MONEY MOVEMENT`;
- all A–E cards blocked without authoritative receipts; and
- the three fixed scenario outcomes.

| Scenario | Required visible result |
|---|---|
| `HAPPY_PATH` | `SIMULATED_CAPTURED`; INR 40 requested/captured under INR 50 cap; legal state sequence |
| `CHECKPOINT_A_BLOCKED` | `SIMULATED_BLOCKED`; zero authorized/captured; no payment |
| `CAPTURE_FAILURE` | `SIMULATED_FAILED_CLOSED`; zero captured; failed state; simulated hold voided |

This demonstrates component composition, decision transparency and failure
recovery. It is not provider or payment-network evidence.

## Build and reproducibility evidence

- Apache License 2.0: `LICENSE`.
- Python 3.11+ package: `pyproject.toml`.
- Hash-locked dependencies: `requirements-dev.lock`.
- Deterministic reproduction: `docs/REPRODUCIBILITY.md`.
- Independent clean-machine reproduction is retained historically, but final
  exact-source release evidence must be regenerated after submission changes.
- The stale workflow-security assertion was corrected to the preregistered
  900-token Candidate-7 amendment source. Local regression at this submission
  boundary is **524/524 passing**; exact-source GitHub CI remains required after
  publication.

## What must remain blocked

### Checkpoint A

<!-- EVIDENCE:CHECKPOINT_A_FINAL_METRICS status=BLOCKED -->

Requires a frozen candidate qualification PASS followed by one official
80-case run satisfying all four thresholds together:

- case pass >= 90%;
- selective semantic reliability >= 95%;
- autonomous coverage >= 55%; and
- ambiguous clarification accuracy >= 80%.

No typed A PASS receipt exists.

### Checkpoint B

<!-- EVIDENCE:CHECKPOINT_B_RAZORPAY_TEST status=BLOCKED -->

Requires A PASS followed by provenance-before-order, Razorpay **Test Mode**
authorization, verification, capture, `payment.captured` verification, refund,
`refund.processed` verification, reconciliation and a typed B receipt. No Live
Mode or real financial data is permitted. Historical pre-provenance transaction
evidence is non-promotable.

### Checkpoint C

<!-- EVIDENCE:CHECKPOINT_C_FINAL_COMPARISON status=BLOCKED -->

Requires passing A+B receipts and the frozen one-shot comparator/TEL experiment.
No final comparison outcome is claimed.

### Checkpoint D

<!-- EVIDENCE:CHECKPOINT_D_FINAL_INTEGRATION status=BLOCKED -->

Requires legitimate A/B/C receipts, an integrated trace and hosted
security/operations evidence. Localhost simulation is not hosted proof.

### Checkpoint E

Requires the final exact-source CI/reproduction and legitimate A–D evidence.
Repository readiness does not substitute for those gates.

## Video and screenshot boundary

<!-- EVIDENCE:FINAL_SCREENSHOTS status=BLOCKED -->
<!-- EVIDENCE:FINAL_VIDEO status=BLOCKED -->

The five-minute recording may show the runnable local simulation, architecture,
tests and retained failure history. It must say aloud that:

1. the console is simulation-only;
2. Candidate 8 is 23/24 in visible development, not qualified; and
3. A–E have not passed.

Do not expose API keys, provider dashboards, signatures, webhook URLs or real
financial information.

## Promotion rule

A status changes only when its complete protocol finishes and its artifact,
source revision and digest are retained. Missing evidence stays `BLOCKED` or
`NOT RUN`; it is never inferred from implementation, file presence or a green
workflow.

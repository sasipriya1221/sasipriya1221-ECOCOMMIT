# ECOCOMMIT Progress

Status vocabulary: `PASS`, `FAILED`, `BLOCKED`, `LOCALLY VALIDATED`, or `NOT RUN`. Workflow color alone is never a semantic PASS.

| Gate | Status | Current boundary |
|---|---|---|
| Candidate-8 visible development | **PASS** | Run `34322382314`, artifact `10093914827`, 24/24 |
| Candidate-8 visible regression | **PASS** | Run `34436075032`, artifact `10136732309`, 12/12 |
| Candidate-8 sealed preflight | **PASS** | Run `34440794156`, aggregate artifact `10138944664`, 24/24 |
| Candidate-8 formal qualification | **PASS** | Run `34458656631`, aggregate artifact `10146318320`, typed receipt PASS, 24/24 |
| Candidate-8 official Checkpoint A | **FAILED** | Run `34676224911`, artifact `10292342612`; early stop after 3/80; no A PASS receipt |
| Checkpoints B–E | **BLOCKED** | Locked because Checkpoint A did not pass |
| Candidate-9 | **NOT RUN** | Authorized; preregistration and isolated development branch are next |

## Candidate-8 terminal boundary

Candidate-8 remains frozen at `850a7b5f1f21d7951cd4a9a840c0bebbb635d594`. Its terminal artifact archive digest is `sha256:eb1b0c48b7c956c56868f176dd76b9eee3e7fd956a2dcf1f94551b9b7bb7feaa`; aggregate status is `FAILED`, and no A PASS receipt exists.

Earlier run `34465756009` stopped after one provider-scored row because of a missing aggregation import. Run `34675788962` stopped before provider construction because of a supervisor-boundary check. They remain infrastructure evidence and do not replace the terminal authorized evaluation.

## Candidate-9 boundary

Candidate-9 is new. Permitted development evidence is limited to public implementation, candidate history, visible development/regression corpora, general language principles, deterministic/property tests, provider documentation, and non-secret infrastructure evidence. Official-A cases/outputs/gold, sealed gold, and formal-qualification gold are forbidden.

Before provider-backed development, Candidate-9 requires a source-bound preregistration defining evidence boundaries, architecture hypothesis, provider/model/prompts/schemas, attempt policy, 900-token ceiling, thresholds, zero-tolerance gates, namespace, iteration limit, and stopping rules.

See [Submission Evidence](docs/SUBMISSION_EVIDENCE.md), [Reproducibility](docs/REPRODUCIBILITY.md), and [Failure Recovery](docs/FAILURE_RECOVERY.md).

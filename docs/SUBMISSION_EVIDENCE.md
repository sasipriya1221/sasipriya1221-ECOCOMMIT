# Submission Evidence

This index records the authoritative current boundary. GitHub Actions artifact bytes, aggregate summaries, and typed receipts override this narrative.

<!-- EVIDENCE:CHECKPOINT_A_FINAL_METRICS status=FAILED -->
<!-- EVIDENCE:CHECKPOINT_B_RAZORPAY_TEST status=BLOCKED -->
<!-- EVIDENCE:CHECKPOINT_C_FINAL_COMPARISON status=BLOCKED -->
<!-- EVIDENCE:CHECKPOINT_D_FINAL_INTEGRATION status=BLOCKED -->
<!-- EVIDENCE:FINAL_SCREENSHOTS status=BLOCKED -->
<!-- EVIDENCE:FINAL_VIDEO status=BLOCKED -->

## Candidate-8 evidence chain

| Gate | Status | Authoritative evidence |
|---|---|---|
| Visible development | **PASS** | Source `850a7b5f1f21d7951cd4a9a840c0bebbb635d594`; run `34322382314`, attempt 1; artifact `10093914827`; archive SHA-256 `b2ce264c2df986adbe9e41e97b3484200b71d4fa519dafac479b50815e2249b4`; summary SHA-256 `24fc8854a05fff78bef9f24719c919f464c1501bf4965857608d8d1486c6a028`; 24/24 |
| Visible regression | **PASS** | Run `34436075032`, attempt 1; artifact `10136732309`; archive SHA-256 `b89c17f068257f0cd3b323064e778153efb49ecb285489ca691c96db6079a2c8`; summary SHA-256 `d8253f25979442365553ee81453de65e1f9a52c61c5e72734ac815f5f995cd0f`; 12/12 |
| Sealed preflight | **PASS** | Run `34440794156`, attempt 1; aggregate artifact `10138944664`; archive SHA-256 `35677602df358909a0769349a19243e1be79423adffe54934b230d4ae1186a31`; summary SHA-256 `c4be609bbcfe14d829c7282519648c60829589c98d017ec89f5faed380925ea0`; 24/24 |
| Formal qualification | **PASS** | Run `34458656631`, attempt 1; aggregate artifact `10146318320`; archive SHA-256 `d829225be0ee23792cc7674cee15ed89dfdde43765128bcd3ed4ee08549c8817`; summary SHA-256 `2e0208ed0445c90dc241ba9aff71d60c52b2c138a82904dfe6fbe9e35b342f03`; typed receipt SHA-256 field `8afa0a96900ced5b1c50429811b05c9d88dfc8603f358aa708eba14d6aca1d74`; 24/24 |
| Official Checkpoint A | **FAILED** | Run `34676224911`, attempt 1; artifact `10292342612`; archive SHA-256 `eb1b0c48b7c956c56868f176dd76b9eee3e7fd956a2dcf1f94551b9b7bb7feaa`; decision file SHA-256 `a2af9ade91cd56c722397b1cc586b2f9358daef9b1939fd3c8e86e67be1816dc`; aggregate file SHA-256 `a7b3d1c0e4072a253952e9209edcda1f3e62877641cb5e8e8ce5c9d462ec0b4c`; early stop after 3/80; no PASS receipt |

Visible regression metrics were 100% case pass, 100% selective reliability, 91.67% autonomous coverage, 100% clarification accuracy, and zero safety failures/provider deferrals. Sealed preflight and formal qualification each scored 24/24, 100% selective reliability, 83.33% autonomous coverage, 100% ambiguity accuracy, and zero safety/provider failures.

The official aggregate records status `FAILED`, processed `3`, provider-attempt rows `3`, zero score-recovery retries, and mathematical elimination after the third processed case. The official case-level artifact is not development evidence and must not be used for Candidate-9.

Restricted artifacts `10138944316` (sealed preflight) and `10146317641` (formal qualification) were not opened.

## Infrastructure chronology

- Official run `34465756009` stopped during aggregation after one provider-scored row because `OfficialCounts` was absent from the runner runtime.
- Official run `34675788962` stopped before provider construction because a checked-out supervisor SHA was incorrectly compared with the dispatch commit SHA.
- Both failures are preserved as infrastructure evidence; neither is the terminal semantic decision.
- Exact-source CI run `34676095634` passed the corrected runner before the terminal evaluation.

## Checkpoint matrix

| Checkpoint | Status | Reason |
|---|---|---|
| A | **FAILED** | Candidate-8 did not meet the frozen official gate and emitted no A PASS receipt |
| B | **BLOCKED** | Requires A PASS |
| C | **BLOCKED** | Requires A and B PASS receipts |
| D | **BLOCKED** | Requires legitimate A/B/C evidence |
| E | **BLOCKED** | Requires the complete upstream evidence chain |

## Candidate-9

Candidate-9 is authorized but **NOT RUN**. It must preregister before provider-backed development and must not consume official-A case material, sealed gold, or formal-qualification gold.

## Product and repository evidence

- Local deterministic safety console: **LOCALLY VALIDATED**
- Hash-locked dependencies and pytest suite: retained in `requirements-dev.lock`, `tests/`, and Offline Regression runs
- Architecture and threat model: `docs/ARCHITECTURE.md`, `docs/THREAT_MODEL.md`
- Reproduction: `docs/REPRODUCIBILITY.md`
- Payment boundary: Razorpay **TEST MODE only**; no Live Mode or real-money claim
- License: Apache-2.0 (`LICENSE`, `docs/LICENSE_DECISION.md`)

No final ECOCOMMIT-versus-baseline numbers are available because C is blocked.
No final screenshot is retained. No final video is recorded as Checkpoint-E
evidence; the linked YouTube demonstration is a local product demo. For the
authoritative B gate, no payment authorization, capture, refund, webhook delivery,
reconciliation, or settlement was executed.

# ECOCOMMIT Progress

This file is the **current evidence board**. Detailed historical failure records remain preserved in `evidence/`, the checkpoint validation documents, GitHub Actions artifacts, and repository history. Nothing below upgrades an incomplete or failed run into a pass.

Status vocabulary is strict:

- **BUILT** — implementation exists.
- **LOCALLY VALIDATED** — deterministic local/regression checks passed.
- **BLOCKED** — required upstream, provider, deployment, or final evidence is absent.
- **PASSED** — the complete frozen acceptance gate passed with retained source-bound evidence.

## Current checkpoint matrix

| Checkpoint | Current state | What is still required |
|---|---|---|
| A — frozen semantic gate | **Candidate 1 FAILED; Candidate 2 INCOMPLETE; Candidate 3 INCOMPLETE; NOT PASSED** | A complete frozen 80-case Candidate 3 aggregate satisfying all four unchanged thresholds plus a typed A receipt |
| B — deterministic economic safety | **B1–B7 + B8 implementation locally validated; pre-order provenance defect fixed; NOT PASSED** | Passing A receipt plus a fresh post-fix Razorpay Test authorization/capture/webhook/refund lifecycle and final B receipt |
| C — comparative benchmark | **RAW-ROW FINAL RUNNER + PREREGISTRATION CHAIN LOCALLY VALIDATED; NOT PASSED** | Passing A+B receipts, genuine frozen held-out inputs/costs/rows, and the one-shot preregistered final run |
| D — product/API/UI/operations | **AUTHORITATIVE LOADER + DURABLE TEST PATH + DEPLOYMENT CONTRACT LOCALLY VALIDATED; NOT PASSED** | Real A/B/C receipts, hosted TLS/security/operations evidence, and final integrated D receipt |
| E — repository/submission readiness | **PUBLIC MAIN + OFFLINE CI + APACHE-2.0 + INDEPENDENT REPRODUCTION RETAINED; NOT PASSED** | A–D final evidence, final source-bound screenshots, and final five-minute video |

Acceptance remains sequential and evidence-gated even when engineering proceeds in parallel.

---

## Checkpoint A

### Frozen acceptance rule

All four thresholds must pass together in one complete real-model 80-case run:

- case pass rate >= **90%**;
- selective semantic reliability >= **95%**;
- autonomous coverage >= **55%**; and
- ambiguous clarification accuracy >= **80%**.

The frozen 80 cases, prompt, model/provider configuration, schemas, evaluator, and thresholds have not been weakened or rewritten.

### Candidate 1 — mathematically failed

Retained source/run: `6485d3b24f4967c178cce9b1a9b67cdf0230840c` / GitHub Actions run `33493409547`, evidence-bearing attempt 15.

The retained aggregate contained 32 terminal rows: 21 passes, 11 terminal failures, and 48 provider-deferred cases. Even if all 48 deferred cases had later passed, Candidate 1 could reach only **69/80 = 86.25%**, below the frozen 90% case-pass threshold. Candidate 1 is therefore permanently **FAILED**.

Retained proof includes:

- artifact `9813043400`;
- archive SHA-256 `6f0052ddf1152f7e25ba13d0a3f9dbea52d6c0a994b0d526d1c2de3ee72b183a`;
- result JSON SHA-256 `1cb8eb4ae722ea77b02a2a2b10891b86f3b2b5c40b3df753b93e8bb0f8c1f4a7`; and
- `evidence/checkpoint-a-candidate-1-failure.json`.

Later reruns cannot replace that mathematical failure.

### Excluded score-recovery experiment

Run `33556907712` used an earlier protocol that automatically filled omitted `materiality` and `confidence` values. That behavior was rejected because exact text grounding does not prove maximum materiality or extraction confidence. The run and its failure history remain preserved but are **not** Candidate 2/3 evidence and are not promotable.

### Candidate 2 — incomplete and not promotable

Candidate 2 ran as `33583323178`. Attempts 1 and 2 remained incomplete and exposed a provider/correction resumability defect; a later public attempt did not convert the run into eligible evidence. Candidate 2 has no passing receipt and will not be resumed into a pass.

### Candidate 3 — latest retained truth

Candidate 3 (`A-CANDIDATE-3`) changes only execution classification/resumability and artifact namespacing. It keeps the frozen dataset, prompt, provider/model configuration, schema, evaluator, and thresholds unchanged.

Public Candidate 3 workflow:

- run: `33590028177`;
- candidate source: `fd26a52a21dc8431133c50be76d7d1ecaf0d099b`;
- manifest SHA-256: `773cb2efef42c0b94491cb599cb5e0d0a361722fec566ba90fac9e595ee51934`;
- latest retained aggregate artifact: `9857872102` (`checkpoint-a-candidate-3-results-attempt-10`);
- GitHub-published archive SHA-256: `917e74372b46f7727b565b335f4a6f23427b9f718d7948d137dcea8b304d900d`;
- independently read aggregate JSON SHA-256: `a5b807d02d69283e5e14c209661f8f2e4e027e0abe55e276e3d46032dcf0f723`.

The attempt-10 cumulative aggregate is still incomplete:

- terminal rows: **18**;
- passed rows: **12**;
- failed rows: **6**;
- missing cases: **62**;
- `full_frozen_gate_run=false`;
- `checkpoint_a_gate.passed=false`;
- typed A receipt: **absent**.

The 12 passing rows are `C001`, `C002`, `C003`, `C005`, `C006`, `C007`, `C008`, `C009`, `C010`, `C038`, `A003`, and `A004`.

The six retained failures are `C004`, `C011`, `C012`, `C019`, `C024`, and `A002`. `C004`, `C011`, and `C012` exhausted bounded correction with an invalid trailing clause; `C019` and `C024` matched the expected validator state but failed one frozen required check; `A002` reached `CLARIFICATION_REQUIRED` as expected but failed the frozen dependency condition.

For the **case-pass criterion alone**, Candidate 3 is not yet mathematically eliminated: if every missing case passed, the maximum would be **74/80 = 92.5%**. However, with six failures already retained, only two additional failures can occur while still reaching the 72/80 minimum. No partial metric is promoted as a final score.

The retry contract requires a fresh, digest-bound healthy-provider observation no more than 30 minutes old before another provider-consuming continuation. The latest aggregate is older than that window and does not itself prove current provider health. Therefore no new Groq retry is dispatched merely because run `33590028177` is terminal.

**Checkpoint A remains BLOCKED / NOT PASSED.**

---

## Checkpoint B

B1–B7 remain locally validated: policy mapping, authoritative evidence, exposure, progressive commitment, TOCTOU protection, certificates, idempotency/reconciliation, and compensation fail closed under adversarial tests.

The A→B boundary requires a typed A receipt bound to Candidate 3, the frozen dataset/thresholds, aggregate/manifest/source digests, and exact evidence reference. Production code refuses caller-created pass strings and test-fixture receipts.

### Retained Razorpay Test evidence

Historical credential/order evidence remains retained for the source versions that created it. It is not retroactively upgraded.

The earlier fresh-source lane included credential preflight `33592456896` and order-boundary run `33592499084` at `fd26a52a…`. It created/fetched one INR 1.00 Test order, found zero attached payments at that boundary, and retained `checkpoint_b8_passed=false` pending Checkout authorization.

A later exact-source order/Checkout attempt, run `33645687964` at source `151379d2d144c7d692b9e8e6f8faef5ab16b72b0`, produced a Test authorization callback. Verification proved the callback was bound to the server-expected order, but the authorization is **permanently non-promotable**: no legitimate certificate/key-reference provenance existed before the order/authorization. That failed attempt remains preserved rather than rewritten.

### Provenance remediation

Public `main` at `36bd3b28cafcb915c41e07e792550e33fd0a54a1` implements the required fix:

- create the source/run/transaction-bound certificate/key reference **before** any Razorpay order call;
- fail closed if that provenance cannot be produced;
- verify Checkout HMAC using the server-side expected order ID;
- use a secret-safe **GET-only** verifier for Razorpay order/payment state;
- require exact INR 1.00 binding, `authorized`, `captured=false`, and zero refund before authorization promotion; and
- prohibit capture/refund/mutation inside the authorization verifier.

Exact-source Offline Regression run `33663013490` passed that implementation with **471/471 tests**.

The historical authorization cannot be salvaged. A **fresh post-fix Test lifecycle** is required. No fresh order, authorization, capture, refund, webhook, reconciliation, settlement, Live Mode call, or real-money action is claimed here.

**Checkpoint B remains BLOCKED / NOT PASSED.**

---

## Checkpoint C

The preliminary development framework remains synthetic and is ineligible for final claims.

The final path is separately implemented as a write-once, raw-row, preregistered protocol. Before outcomes are observed it binds the genuine held-out suite, case identities, metric/TEL/cost-source hashes, passing A+B receipts, candidate/comparator protocols, comparator selection, one execution ID/nonce, acceptance margins/floors/ceilings, missing/error treatment, and statistical method.

The final runner rejects fixtures/simulated inputs, enforces exact case coverage and A→B→C revision/hash chains, re-scores raw rows, and publishes only atomic write-once evidence. No legitimate final A/B receipts or real held-out execution currently exist, so the one-shot final comparison has **not** been run.

**Checkpoint C remains BLOCKED / NOT PASSED.**

---

## Checkpoint D

The loopback API/UI, audit/observability, bounded parsers, status truth, opaque prepared-operation boundary, durable SQLite state, idempotency, webhook verification/deduplication, and deployment templates remain locally validated.

The provider path remains disabled unless startup loads pinned authoritative A/B/C evidence, current Test credentials pass preflight, environment-only API/certificate/webhook secrets exist, persistent state/audit paths are configured, and the pinned operation is ready. Request callers cannot supply financial authority, evidence authority, credentials, or keys.

Deployment files define the WSGI/TLS/reverse-proxy/security contract, but no hosted listener/DNS/certificate/backup/monitoring proof or final integrated A/B/C transaction has been retained. The previously retained temporary tunnel later returned HTTP 502 and was not treated as hosted proof.

**Checkpoint D remains BLOCKED / NOT PASSED.**

---

## Checkpoint E / release

The repository contains:

- pinned third-party GitHub Actions;
- hash-locked development dependencies;
- offline regression on every `main` push/PR;
- strict repository-readiness checks;
- architecture/threat-model/reproducibility/deployment documents;
- engineering failure/fix chronology;
- submission-evidence slots and five-minute pitch outline; and
- a canonical top-level `LICENSE` using **Apache License 2.0**, with the owner decision recorded in `docs/LICENSE_DECISION.md` and package metadata aligned.

Independent clean-machine reproduction is now retained rather than merely implemented. Source `3ab6e12193e578c76bdb2d03a0d39a837af0d353` passed exact-source Offline Regression run `33686790311`, then Independent Clean-Machine Reproduction run `33686844451` independently installed hash-locked dependencies on Ubuntu 24.04/Python 3.11, passed **471/471 tests** and **8/8 repository readiness checks**, verified exact public-main binding, and uploaded artifact `9868448162` (`checkpoint-e-independent-reproduction-33686844451`). The typed self-digesting reproduction receipt SHA-256 is `d968277470ea659de65b562070715e86003e05ae09ab0e132bab06cbf3c236a7`; provider calls and fixture promotion were both false. The workflow repeats after each successful future `main` Offline Regression so later release heads receive source-exact reproduction evidence as well.

Final E blockers are now:

1. passing Checkpoint A evidence;
2. passing Checkpoint B fresh Test lifecycle evidence;
3. passing Checkpoint C one-shot comparison;
4. passing Checkpoint D hosted/integrated evidence;
5. final source-bound screenshots; and
6. final five-minute demo video.

**Checkpoint E remains BLOCKED / NOT PASSED.**

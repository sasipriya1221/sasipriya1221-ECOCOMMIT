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
| A — frozen semantic gate | **Candidate 1 FAILED; Candidate 2 INCOMPLETE / NOT PROMOTABLE; Candidate 3 FAILED; Candidate 4 PREREGISTERED / SUPERSEDED / NEVER RUN; Candidate 5 PREPARED OFFLINE / NOT RUN; NOT PASSED** | Freeze and publish Candidate 5 preregistration with real implementation hashes, obtain green exact-source CI and provider preflight, then dispatch exactly one fresh manual 80-case evaluation. A typed A receipt exists only if all four unchanged gates pass. |
| B — deterministic economic safety | **B1–B7 + B8 implementation locally validated; pre-order provenance defect fixed; NOT PASSED** | A passing typed A receipt plus a fresh post-fix Razorpay Test authorization/capture/webhook/refund lifecycle and final B receipt |
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

The frozen 80 cases, system prompt, model/provider identity, compact/strict schemas, evaluator, and thresholds have not been weakened or rewritten.

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

Run `33556907712` used an earlier protocol that automatically filled omitted `materiality` and `confidence` values. That behavior was rejected because exact text grounding does not prove maximum materiality or extraction confidence. The run and its failure history remain preserved but are **not** Candidate 2/3/4 evidence and are not promotable.

### Candidate 2 — incomplete and not promotable

Candidate 2 ran as `33583323178`. Attempts 1 and 2 remained incomplete and exposed a provider/correction resumability defect; a later public attempt did not convert the run into eligible evidence. Candidate 2 has no passing receipt and will not be resumed into a pass.

### Candidate 3 — mathematically failed

Candidate 3 (`A-CANDIDATE-3`) changed only execution classification/resumability and artifact namespacing. It kept the frozen dataset, prompt, provider/model configuration, schema, evaluator, and thresholds unchanged.

Public Candidate 3 workflow:

- run: `33590028177`;
- candidate source: `fd26a52a21dc8431133c50be76d7d1ecaf0d099b`;
- evidence-bearing terminal attempt: **11**;
- manifest SHA-256: `773cb2efef42c0b94491cb599cb5e0d0a361722fec566ba90fac9e595ee51934`;
- retained aggregate artifact: `9875163068` (`checkpoint-a-candidate-3-results-attempt-11`);
- GitHub-published archive SHA-256: `e92787fc2dae0023b6c7fa0a1240f606e3a948fbca6b7f6ef22e27c9e8fddaa6`;
- independently read aggregate JSON SHA-256: `e1b2afd0fdc9bccd05f8dbbe492f59845be170f03246f7646c8ab1fbfc8d0f33`; and
- retained failure record: `evidence/checkpoint-a-candidate-3-failure.json`.

The attempt-11 cumulative aggregate remains incomplete but is already mathematically decisive:

- terminal rows: **32**;
- passed rows: **23**;
- failed rows: **9**;
- missing cases: **48**;
- `full_frozen_gate_run=false`;
- `checkpoint_a_gate.passed=false`;
- typed A receipt: **absent**.

The 23 passing rows are `C001`, `C002`, `C003`, `C005`, `C006`, `C007`, `C008`, `C009`, `C010`, `C028`, `C030`, `C031`, `C038`, `C047`, `C050`, `A001`, `A003`, `A004`, `A006`, `A008`, `A011`, `A013`, and `A029`.

The nine retained failures are `C004`, `C011`, `C012`, `C013`, `C014`, `C019`, `C024`, `C033`, and `A002`.

- `C004`, `C011`, `C012`, `C013`, and `C014` exhausted bounded correction with an incomplete trailing clause and are terminal schema failures under the frozen candidate.
- `C019` and `C024` matched the expected validator state but failed one frozen required semantic check.
- `C033` failed the frozen exception-preservation requirement and was rejected instead of validated.
- `A002` reached `CLARIFICATION_REQUIRED` as expected but failed the frozen dependency condition.

The frozen 90% case-pass criterion requires at least **72/80** passing cases. Candidate 3 already has **9 immutable terminal failures**. Even if every one of the remaining 48 cases passed, the best possible result would be **71/80 = 88.75%**. Candidate 3 is therefore permanently **FAILED** on the case-pass criterion alone; completing the missing provider-deferred cases cannot change that conclusion.

No further Groq retry is justified for Candidate 3. Re-running terminal failures until a different stochastic answer appears would discard retained evidence and convert the benchmark into retry-until-lucky score recovery.

### Candidate 4 — PREREGISTERED / SUPERSEDED / NEVER RUN

Candidate 4 is explicitly retired in `evidence/checkpoint-a-candidate-4-retirement.json`. Its historical preregistration at source `d7c1acf9c1762a63f50cbf8b120083e956307b92` is preserved byte-for-byte. Source-filtered public Actions history contains only successful offline CI `33740496666` and independent reproduction `33740536540`; there was no Candidate 4 provider/preflight/evaluation run.

### Candidate 5 — prepared offline, awaiting public preregistration and live gates

Candidate 5 (`A-CANDIDATE-5`) introduces **UNIFORM_OUTPUT_BUDGET_REMEDIATION** after a zero-provider-call audit of retained Candidate 3 artifact `9875163068`. The downloaded archive and result JSON exactly match the published hashes above. `evidence/checkpoint-a-candidate-5-offline-audit.json` retains the nine relevant rows, provider traces, exact failure descriptions and timeout audit.

All ten retained attempts for C004/C011/C012/C013/C014 have `finish_reason=length` and exactly 1,024 completion tokens. Both attempts of C011–C014 and the correction of C004 report eight missing fields at `clauses.6`, the seventh clause. C004's initial attempt also reports two `normalized_value` string-type errors. **Invalid raw response bodies were not retained**: only candidate hashes, usage, finish reasons and schema issues exist. The missing-field locations support late structured-output incompleteness; they do not establish the exact missing token count or prove there were no further intended clauses. The uniform 2,048-token ceiling is bounded operational headroom above the observed cutoff, not a measured minimum or a guarantee of semantic success.

The four separate unaddressed risks were recomputed from retained schema-valid contracts:

- C019: `VALIDATED`, but no `COUNTERPARTY` clause grounds **certified suppliers**; the contract instead contains `CERTIFICATION: certified`. Required semantic check 3 fails.
- C024: the same missing **certified suppliers** counterparty, in the food-safe conveyor-belt instruction. Required semantic check 3 fails despite `VALIDATED`.
- C033: **provided that food-safety certification is current** appears as a condition and dependency, with no exception clause or `exception_to` link. The frozen validator returns `REJECTED / EXCEPTION_NOT_PRESERVED` instead of `VALIDATED`.
- A002: clarification status and `MATERIAL_VAGUENESS` were correctly returned. **if needed** has `exception_to` links but no dependency clause or `depends_on` link, so the frozen dependency requirement fails.

Candidate 5 applies 2,048 tokens uniformly to all 80 cases and every permitted correction, with at most two schema corrections and three total provider attempts. The first schema-valid output remains terminal even when semantically wrong. The dataset/digest, prompt, Groq endpoint, `qwen/qwen3.6-27b`, reasoning `none`, JSON-object mode, contract schemas, evaluator, and all four thresholds remain unchanged. No case-specific logic, gold feedback, semantic regeneration, threshold tuning or retry-until-pass is permitted.

To enforce the user's immediate mathematical-stop requirement without status polling, the fresh run processes the existing frozen order serially. It checks only conservative impossibility bounds between cases and never dispatches another case after a threshold is unreachable. Deferred cases remain unknown; no partial score is a pass. There is no restore/resume path; workflow reruns are rejected. The artifact namespace is `checkpoint-a-candidate-5`; one source-bound non-benchmark provider preflight must succeed before evaluation.

Timeout audit: three 60-second request allowances plus at most two 15-second retry sleeps give a nominal 210-second envelope. The old eight-minute case job had 270 seconds of nominal setup/teardown margin, but a socket timeout is not a hard wall-clock bound. Candidate 5 adds a uniform 240-second case-process deadline. The serial evaluation job has 360 minutes: 80 hard case deadlines require at most 320 minutes, leaving 40 minutes for setup, process overhead, aggregation and artifact upload. A deadline is an infrastructure deferral, never a semantic pass. The 60-second request timeout remains unchanged; retained traces contain no latency measurements. A full 2,048-token completion would require approximately 34.14 tokens/s before overhead, so provider availability/latency is still an external preflight condition.

Validation: **38 focused regressions passed** and the complete repository gate passed **486/486 tests**. Coverage includes budget, bounded correction, terminality, namespace, manifest and automatic stop. Dependency consistency, Python compilation and whitespace checks passed. Hosted CI will perform the required JavaScript and clean-source checks. Final preregistration binding is pending. Provider calls during audit and preparation: **zero**. No B8/C/D live work was performed.

**Checkpoint A remains BLOCKED / NOT PASSED.**

---

## Checkpoint B

B1–B7 remain locally validated: policy mapping, authoritative evidence, exposure, progressive commitment, TOCTOU protection, certificates, idempotency/reconciliation, and compensation fail closed under adversarial tests.

The A→B boundary requires a legitimate typed A pass receipt bound to its preregistered dataset/thresholds, aggregate/manifest/source digests, and exact evidence reference. Production code refuses caller-created pass strings and test-fixture receipts. No current candidate has supplied that receipt.

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

The historical authorization cannot be salvaged. A **fresh post-fix Test lifecycle** is required after a legitimate passing A receipt exists. No fresh order, authorization, capture, refund, webhook, reconciliation, settlement, Live Mode call, or real-money action is claimed here.

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

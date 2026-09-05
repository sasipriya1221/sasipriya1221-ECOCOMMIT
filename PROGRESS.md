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
| A — frozen semantic gate | **Candidate 1 FAILED; Candidate 2 INCOMPLETE / NOT PROMOTABLE; Candidate 3 FAILED; Candidate 4 PREREGISTERED / SUPERSEDED / NEVER RUN; Candidate 5 FAILED; Candidate 6 FAILED DEVELOPMENT QUALIFICATION; Candidate 7 INCONCLUSIVE / PROVIDER_LIMITED; NOT PASSED** | Candidate 7 exact-source D003/D009 qualification stopped after its first provider call returned HTTP 429. It produced no accepted semantic output and does not admit the official 80-case gate. A typed A receipt exists only if all four unchanged gates pass. |
| B — deterministic economic safety | **B1–B7 + B8 implementation locally validated; pre-order provenance defect fixed; NOT PASSED** | A passing typed A receipt plus a fresh post-fix Razorpay Test authorization/capture/webhook/refund lifecycle and final B receipt |
| C — comparative benchmark | **RAW-ROW FINAL RUNNER + PREREGISTRATION CHAIN LOCALLY VALIDATED; NOT PASSED** | Passing A+B receipts, genuine frozen held-out inputs/costs/rows, and the one-shot preregistered final run |
| D — product/API/UI/operations | **AUTHORITATIVE LOADER + DURABLE TEST PATH + DEPLOYMENT CONTRACT LOCALLY VALIDATED; NOT PASSED** | Real A/B/C receipts, hosted TLS/security/operations evidence, and final integrated D receipt |
| E — repository/submission readiness | **PUBLIC MAIN + OFFLINE CI + APACHE-2.0 + INDEPENDENT REPRODUCTION RETAINED; NOT PASSED** | A–D final evidence, final source-bound screenshots, and final five-minute video |

Acceptance remains sequential and evidence-gated even when engineering proceeds in parallel.

---

## Checkpoint A

### Candidate 7 — exact-source qualification INCONCLUSIVE / PROVIDER_LIMITED

The hard-bound qualification ran once as GitHub Actions run `33944653729`, attempt 1. The launcher checked out and verified frozen Candidate-7 source `12d121f80a6cacd94376c6d2b7bce7dff5212eb5`, selected mode `candidate7-d003-d009`, and invoked only `scripts/candidate7_pass2_qualification.py`. Artifact `9962936517` (`candidate7-pass2-qualification-33944653729-attempt-1`) has archive SHA-256 `f55e6d6284bfe4c142c39de782eda815a229aabe4fa7eadb5aaa6b38d95fdd2d`.

The first D003 request returned sanitized transient `HTTP_429`; the frozen fail-fast policy stopped immediately. Provider calls: 1. Accepted semantic outputs: 0. D009 was not called. The green workflow conclusion reflects correct evidence preservation and is not a semantic pass. `evidence/candidate7-frozen-qualification-inconclusive.json` pins the source binding and retained row/summary hashes. No retry, official Checkpoint-A case access, holdout access, or Candidate-8 work occurred.

The same exact workflow was legitimately rerun once as attempt 2. Artifact `9963027900` (`candidate7-pass2-qualification-33944653729-attempt-2`) has archive SHA-256 `d6488b18aa8b923de69ca772ce6503e5dd4cb84c3b7dd6d2e0c37d9bdd00c787`. It independently verified the same frozen source, mode, and harness, then received transient `HTTP_429` on its first D003 provider call. It again stopped immediately with zero accepted outputs and no D009 call. `evidence/candidate7-frozen-qualification-attempt-2-inconclusive.json` pins that evidence.

Candidate 7 therefore remains **INCONCLUSIVE / PROVIDER_LIMITED**. Checkpoint A cannot begin without a legitimate Candidate-7 qualification PASS. No additional provider call is justified while capacity remains unconfirmed; the earliest legitimate provider action is the unchanged frozen qualification only after independent evidence of provider recovery and explicit preservation of the no-retry-until-lucky rule.

Candidate-7 official-A infrastructure is now published and locally execution-ready without a provider call. It includes a qualification-PASS-only preregistration builder, exact frozen candidate and supervisor source/component/dataset/evaluator/criteria/runner/workflow bindings, a non-benchmark readiness lane, a one-shot class-aware early-stopping runner, typed `A-CANDIDATE-7` receipt validation, and historical Candidate-5/6 serialization compatibility. A mocked 80-case end-to-end test proves preregistration-to-runner-to-receipt-to-B loading without using benchmark gold feedback or making a provider call; the final local regression is 524/524 passing. The three new workflows are manual-only and cannot run from a push. This readiness state is not an A pass and cannot bypass the missing Candidate-7 qualification PASS.

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

### Candidate 5 — mathematically FAILED / NOT PASSED

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

Validation: **38 focused regressions passed** and the complete repository gate passed **486/486 tests**. Coverage includes budget, bounded correction, terminality, namespace, manifest and automatic stop. Dependency consistency, Python compilation and whitespace checks passed. Hosted CI will perform the required JavaScript and clean-source checks. Candidate 5 preregistration has been frozen before any provider call at `evidence/checkpoint-a-candidate-5-preregistration.json`. Provider calls during audit and preparation: **zero**. No B8/C/D live work was performed.

Implementation source: `af12143d7ac41a02eb774a12b4ff74709cdc4e76`. Runner SHA-256: `e107a433beffe00b81c77eeaec058b823f74a53602ff336daa199ecd9c65cb32`. Offline frozen manifest SHA-256: `1c2f62e912434a6ba130edaadaaf24551868c1bbf9a8abac4a0db3266b5b4215`. Canonical preregistration SHA-256: `8f2e8c56f929b90c8597a637de6fd38098b724837da2352ce1c8e693c4fc3958`. The evidence-only registration commit necessarily follows the implementation commit; runtime receipts bind their exact public execution revision/run and retain these frozen configuration/runner hashes. That preregistration preceded CI, provider readiness and evaluation; the final execution outcome follows below.

Public preregistration/source commit `7334ff98f07f894d589169b3f134aa0c21b5be7f` passed exact-source offline CI `33762874444` and independent clean-machine reproduction `33762910331`, both attempt 1. The first readiness workflow `33763004651` stopped **before any provider call** because a legacy default-one-correction unit test inherited the Candidate 5 two-correction environment. Secret verification, Groq execution and health-receipt upload were skipped. Its failure history is retained in `evidence/checkpoint-a-candidate-5-preflight-blocked-33763004651.json`.

The only repair is to isolate that legacy unit test's default setting. The complete **486/486** suite now passes under the actual preflight environment. Production runner bytes, all frozen semantic settings and the original Candidate 5 preregistration remain unchanged. At the test-repair checkpoint, a fresh provider preflight still required green exact-source CI; no evaluation had yet been dispatched and no Candidate 1-4 retry had occurred.

#### Sole Candidate 5 execution — raw incomplete outcome, superseded by mathematical failure

Exact execution source: `3c34af1e855aba80a3a4d9ceb9450bc344a4fd67`. Offline CI `33763220483` and independent clean-machine reproduction `33763257621` both passed, with **486 tests and 8 repository checks** in the independent receipt. Its artifact is `9896409760`; archive SHA-256 `8e087223e7baf298f9b6530b919dfa7c35c6c3f6e14b22b4dee3f0ab3a4b2f9e`.

Provider preflight `33763360449` passed on **one actual Groq request**, returning 1,097 completion tokens in 2.625638385 seconds under the frozen 2,048 cap. The health artifact is `9896432127`; archive SHA-256 `c1b99a7b12ceb0e136353c251245a8cedefdbdb6282f4719cd4ef79f0e1876bb`; receipt SHA-256 `b65eae9976ff0d8aa6eaad3217952e0313c22f6c3f0855dbdc9943d650e1f1b5`. This establishes readiness for that request, not uninterrupted capacity for 80 cases.

Exactly **one** fresh evaluation was dispatched: [run 33763572533](https://github.com/sasipriya1221/sasipriya1221-ECOCOMMIT/actions/runs/33763572533), attempt **1**. All **80** frozen case indices were attempted. The final evidence has **35 terminal cases and 45 provider-deferred cases**. Every deferral trace includes `HTTP_429`; some interruptions occurred during schema correction. The 80 case artifacts retain **204 total provider attempts**, with no case exceeding **three**. All retained attempts respect the uniform completion ceiling and first-schema-valid terminality. There was no workflow rerun, resume, additional evaluation, Candidate 1-4 retry, or B8/C/D live execution.

The raw aggregate is **incomplete**, and its live guard reported no mathematical elimination. That preliminary classification is superseded by the stricter offline proof below. No partial score is treated as a final score. **No A PASS and no typed A receipt exist.** Candidate 5 must never be rerun or resumed into a pass.

Retained final artifact `9897481331` (`checkpoint-a-candidate-5-results-attempt-1`) includes all 80 case artifacts, logs, the runtime manifest, original preregistration, provider-health receipt, incomplete aggregate and typed decision. Exact pins:

- archive SHA-256: `defb9656953ea64f7e2c4dbc332ade6d58fdb82b38198a5edc44b7bb1194c929`;
- aggregate JSON SHA-256: `50a13de89f2ccf7cbe2813d8c32f34943da65483b72196094d8024f5ba6bd665`;
- runtime manifest SHA-256: `45bc5df166a94a88a137613a6534e60f22cfe4360157fdc579e74000d0199d80`;
- decision SHA-256: `c27f27aa0620fee2c313dabcbaf98e1a654174887f43db1d0c50a82119b37766`; and
- independent local result-verification SHA-256: `dd7af06c4f3f2bd8ad1d736da74f615713b918a02dd53153415c0d2e8c76673e`.

The archive digest matches GitHub's published digest. Offline verification recomputed all retained row digests and semantics with the unchanged evaluator, checked the complete 80-index attempt inventory, and verified the manifest, decision, bounded attempts and absence of a typed A receipt. Verification made zero provider calls. `evidence/checkpoint-a-candidate-5-incomplete.json` preserves the preliminary raw-run classification. It is superseded by `evidence/checkpoint-a-candidate-5-failure.json`; the original artifacts are retained unchanged. Candidate 4's preregistration and Candidate 5's preregistration remain unchanged.

#### Final adjudication — selective reliability cannot reach 95%

A stricter offline proof using the unchanged frozen expected statuses establishes **Candidate 5 FAILED**, even though 45 cases remain provider-deferred. The three immutable `VALIDATED` but semantically incorrect terminal cases are **C019, C024 and C049**. There are 28 retained validated outputs, of which 25 are correct, and only 21 missing clear cases can add correct validated outputs. Even if all 21 were correct, the best possible selective reliability is **(25 + 21) / (28 + 21) = 46/49 = 93.877551%**, below the frozen **95%** minimum. The 24 missing ambiguous cases require `CLARIFICATION_REQUIRED`: validating them makes them semantically wrong and cannot improve this bound. This is a bound over every possible completion, not a reported partial-run score.

**The stop guard added for Candidate 5 was too loose and missed the required early stop.** It incorrectly treated all missing cases, including ambiguous ones, as potential correct validated outputs. The tighter bound first becomes decisive after **C049**, the 49th scheduled case. The workflow continued through **31 additional cases / 87 additional provider attempts** before its raw incomplete conclusion. This is an implementation defect and a failure to honor the requested immediate mathematical stop; it is not attributed to Groq. The original runtime, preregistration, logs and raw decision are preserved, and no post-run score-recovery run or protocol rewrite was performed.

The final failure proof is `evidence/checkpoint-a-candidate-5-failure.json`, canonical SHA-256 **`5e6237a7dd561c0fb9ff805dd7792787323b83b7179d2f103ae809d45f2135a8`**. It binds the same source/run/artifact/manifest, verified terminal row and contract hashes, earliest provable failure, and excess-attempt count. It supersedes the preliminary incomplete classification without rewriting it. Candidate 5 is permanently **FAILED / NOT PROMOTABLE**; provider retries cannot remove its immutable semantic failures. The usage-critical next action is to disclose this A failure and missed-stop defect. Any future candidate requires a separately authorized, newly preregistered change; no further Candidate 5 live work is permitted.

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

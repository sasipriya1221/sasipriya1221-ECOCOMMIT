# ECOCOMMIT Checkpoint C Local Validation

**Verdict: BLOCKED — NOT PASSED**

Checkpoint C's local benchmark framework is validated against deterministic and
synthetic-fixture tests. The result is not a Checkpoint C pass and is not
ECOCOMMIT-vs-baseline performance evidence. The real comparison remains blocked
on frozen real inputs, real comparator outputs, final preregistered economic-loss
weights and quantitative acceptance rule, a validated A+B candidate, and a
separately gated held-out run.

The current tree also contains a separate final preregistration/evidence contract.
It requires upstream receipt hashes, held-out suite/case/cost/metric hashes,
candidate revision, comparator choice, TEL margin, completion/reliability floors,
latency/error/missing-data/irreversible-loss ceilings, tie handling, rationale,
and statistical method before any outcome can validate. It structurally refuses
fixture inputs and simulated cost or latency. No real values or outcomes have
been filled into that contract.

### Current boundary-hardening addendum

The current input loader rejects oversized, empty, symlinked, duplicate-key,
non-finite, invalid-Unicode, over-complex, and non-object plan/suite JSON before
Pydantic validation. This closes parser-differential ambiguity without changing
any frozen fixture or final decision rule. The current focused C suite passes
**47/47** and the full deterministic suite passes **343/343**; a separate
no-hardlink clone at `13fcdbf0e1b12595a146d5518cc0683899e12cbe`
passes the same suite and static/readiness checks. This remains same-host local
evidence, not a final comparison or independent reproduction.

## Validation boundary

- Validation date: 2026-09-01.
- Source base at validation start: `6e5e1f3a78f20d0d5e0417989e551e6057f54cab`.
- Validated C implementation commit: `ac2ae83` (`fix(checkpoint-c): harden
  benchmark validation`).
- Reconciled A/C tree commit: `dde80b0` (`merge: reconcile resumable checkpoint
  A workflow`). The post-merge rerun used this source/test/fixture tree; only the
  documentation updates recorded by this report remained uncommitted.
- No Checkpoint A live-evaluation artifact, dataset, prompt, model setting, or
  threshold was changed by this track.
- No payment/provider claim was used. Checkpoint B remains a prerequisite.
- No final comparison numbers were generated or published.

## Executed evidence

Focused Checkpoint C validation:

```powershell
.venv\Scripts\python -m pytest -o addopts="" tests\test_checkpoint_c_models.py tests\test_checkpoint_c_baselines.py tests\test_checkpoint_c_metrics.py tests\test_checkpoint_c_runner.py tests\test_checkpoint_c_frozen_fixture.py -q -p no:cacheprovider --basetemp=.test-tmp-root-post-merge-c-focused
```

Result: **41/41 passed**.

Full deterministic regression:

```powershell
.venv\Scripts\python -m pytest -o addopts="" -q -p no:cacheprovider --basetemp=.test-tmp-root-post-merge-full-2
```

Result: **167/167 passed**.

The CLI was also exercised against the checked-in one-case synthetic fixture.
Its structural receipt reported `PRELIMINARY_NOT_FINAL`, `NOT_EVALUATED`,
`NOT_COMPUTED`, fixture inputs, simulated economic costs, simulated latency, zero
retained errors, and `final_comparison_numbers_published: false`. The generated
artifact is ignored local test output and is not retained as benchmark evidence.

## Frozen local fixture

The checked-in fixture exists only to detect framework drift. It is not the real
benchmark suite and is ineligible for final claims.

- suite digest: `4c6d304d3850cb493519bda9c5943f4774c861b522ff8e837a9a8c23161f9392`
- plan digest: `416e13b9a7cbf3097c4a10662290c2b12be20c3b41df46a2e1a9f80c8a44fe43`
- dynamic-workflow configuration digest:
  `cdf0c9dd825bd8739959f4526890afb4fe333929d66b30f04ecea88e6fe2b05c`

The fixture freezes its instruction text/digest, structured scenario inputs,
reference outcome, evidence provenance, simulated cost assumptions, baseline
configurations, replay decisions, seed, metric formulas, TEL weights, and source
digests. Tests pin the literal digests rather than recalculating both sides from
one mutable factory.

## Gate matrix

| Gate | Local result | Evidence and limitation |
|---|---|---|
| C1 — versioned plan, suite, and scenario definitions | PASS (local) | V2 schemas freeze original instruction text, suite identity/version/digest, UTC registration times, seed, and split. Only the checked-in synthetic fixture is frozen; the real suite is not. |
| C2 — naive-agent baseline | PASS (framework only) | Deterministic replay requires a complete per-case manifest, model/prompt references and digests, output digests, latency provenance, and fixture/cached labeling. The validation inputs are synthetic fixtures, not real agent outputs. |
| C3 — prompt-guardrail baseline | PASS (framework only) | Same replay-integrity controls plus a guardrail protocol reference/digest. The validation inputs are synthetic fixtures, not guardrailed-model evidence. |
| C4 — static deterministic baseline | PASS (local) | Amount ceiling and registered blocked-signal rules are deterministic and tested. |
| C5 — strongest dynamic deterministic workflow interface | PASS (local interface) / BLOCKED (strength claim) | The registered workflow is policy-, risk-, required-evidence-, freshness-, and latency-aware and cannot disable fail-closed required-evidence behavior. The exact local config is digest-pinned. Calling it the strongest comparator is only a preregistered role designation until a real comparator-selection study is frozen and run. |
| C6 — preregistered Total Economic Loss | PASS (accounting) / BLOCKED (final weights) | The plan freezes positive basis-point weights and integer round-half-up behavior for unsafe execution, false abort, abstention review, and compensation cost. It explicitly charges error rows the weighted abstention-review loss. Raw and weighted components are retained per case and recomputed. The checked-in weights are explicitly synthetic test values; final weights are not frozen. |
| C7 — false-abort, compensation, and irreversible-exposure accounting | PASS (local) | Counts, rates, raw/weighted losses, compensation events/outcomes/costs, incorrect irreversible amount, and legitimate completion are independently tested. Authorization and legitimate-completion truth are no longer conflated. |
| C8 — latency accounting | PASS (local) | Per-case value and provenance, total, nearest-rank p95, missing observation count, simulated/measured provenance set, and mixed-data flags are tested. The plan explicitly freezes error latency as missing, excluded from total/p95, and counted as a missing observation. Fixture latency is explicitly simulated. |
| C9 — reproducibility | PASS (local) | Artifact records plan/suite hashes, chronology, code revision, dirty flag, Python/platform, a sorted manifest of every installed Python distribution/version, seed, deterministic order, replay-source kinds, fixture/simulated-cost use, latency provenance, and retained error count. The installed-package manifest is resolved-environment evidence, not a dependency lock. |
| C10 — benchmark integrity | PASS (local) | Exact baseline×case coverage is enforced; replay coverage must equal the suite; source/response digests are checked where retained; errors become explicit rows; every case result and aggregate summary is semantically recomputed from the frozen plan/suite; tampering tests pass. |
| C11 — validated integrated ECOCOMMIT candidate | BLOCKED | Checkpoints A and B are explicit prerequisites and are not both validated. The preliminary runner consumes no live A output and has no ECOCOMMIT candidate comparator. |
| C12 — final held-out comparison | BLOCKED | The preliminary runner rejects every `FINAL_HELD_OUT` case and cannot mark C passed or publish a final comparison. |
| C13 — quantitative acceptance decision rule | BLOCKED | No final TEL improvement margin/tie rule, legitimate-completion floor, latency ceiling, gate consequence/tolerance for error or missing-latency rows, or statistical decision method is frozen. These must be preregistered before any final outcomes are observed; no threshold is invented here. |

## Defects found and fixed

1. Added the missing naive-agent and prompt-guardrail comparator roles as
   provenance-bound replay interfaces; plans now require exactly one of each
   required comparator type.
2. Replaced the ambiguous dynamic baseline label with an explicitly versioned,
   fail-closed dynamic deterministic workflow role and a required selection
   rationale. Its local configuration is digest-pinned.
3. Added frozen original instruction text/digests so an agent-input suite is not
   only a post-processed numeric manifest.
4. Separated authorization ground truth from legitimate-completion ground truth.
5. Added explicit TEL weights, raw and weighted four-component loss records,
   deterministic rounding, false-abort count/rate, and explicit
   compensation-event/outcome/cost accounting.
6. Replaced the ambiguous single latency boolean with an explicit provenance set,
   all-simulated and contains-simulated flags, and missing-latency accounting.
7. Added complete repository/runtime provenance: required code revision, dirty
   flag, Python/platform, and dependency versions.
8. Retained unexpected baseline failures as `ERROR` rows with unavailable latency
   rather than silently omitting rows or losing the entire scheduled manifest.
9. Closed semantic artifact-tampering gaps by recomputing every decision-derived
   result, TEL component, metric summary, replay coverage set, and provenance
   summary during validation.
10. Added a literal-digest checked-in fixture plan/suite and prompt/guardrail
    files, all explicitly labeled synthetic and preliminary.
11. Enforced `run generated_at >= plan registered_at >= suite frozen_at` in both
    the runner and artifact validator.
12. Included simulated economic-cost inputs in the fixture/simulation provenance
    boundary and exposed a separate simulated-cost flag.
13. Replaced the two-package runtime note with a deterministic, sorted manifest
    of every installed Python distribution and version, including
    `pydantic-core`.
14. Froze the local accounting treatment for error-row loss, reliability, and
    missing latency in the metric specification, with direct TEL assertions.
15. Added a digest-bound final preregistration and decision contract that
    recomputes the quantitative gate, binds A/B receipts and the candidate
    revision, and makes post-outcome rule changes or fixture/simulation promotion
    invalid.
16. Replaced permissive plan/suite JSON loading with a bounded nonsymlinked
    strict decoder so duplicate keys and non-standard JSON cannot be normalized
    into a different frozen input.

## Remaining blockers

- Freeze the real development/validation/final-held-out scenario manifests,
  including original instructions, reference outcomes, costs, and provenance,
  before observing final results.
- Independently timestamp and hash-freeze the real naive-agent prompt/model
  protocol before output collection, then retain a separate complete cached/live
  output manifest with authentic source digests and measured latency. Embedding
  synthetic replay decisions in the local plan validates mechanics only; it does
  not prove pre-output preregistration.
- Apply the same independently frozen pre-output registration and separate output
  manifest discipline to the real prompt-guardrail comparator.
- Preregister the comparator-selection method and establish which dynamic
  deterministic workflow is strongest without using final held-out outcomes.
- Preregister final TEL weights and economic-cost sources; the synthetic fixture
  values are not transferable to a claim.
- Before observing any final outcomes, preregister the quantitative C acceptance
  and statistical decision rule: TEL improvement margin and tie handling,
  legitimate-completion floor, latency ceiling, treatment of errored or
  missing-latency rows at the acceptance gate beyond their frozen accounting
  treatment, and the statistical method. None is currently frozen.
- Validate the current hash-locked dependency file on an independent machine;
  its published artifact hashes cover the supported Linux CI and Windows
  validation wheels, but this is not independent reproduction.
- Obtain genuine passing A and B evidence and a version-bound integrated candidate.
- After those criteria are frozen, execute the separately gated final-held-out
  comparison once, retain all error rows/artifacts, and apply the preregistered
  decision rule without tuning.

## PASS / BLOCKED / FAIL rule

- **PASS** requires every C gate, both upstream prerequisites, the frozen real
  suite/plan, authentic comparator and candidate inputs, final TEL weights, and a
  quantitative/statistical acceptance rule frozen before final outcomes, followed
  by the one-shot final held-out evaluation completing with retained evidence and
  satisfying that rule.
- **BLOCKED** applies when the locally validated framework is ready but required
  upstream, real-input, preregistration, or final-run evidence is unavailable.
- **FAIL** applies when an executed required gate or integrity check fails. A
  failed real run is retained and cannot be relabeled as blocked or passed.

Current judgment: **BLOCKED — NOT PASSED**. No threshold was lowered and no
fixture, cache, or simulation was represented as live or final evidence.

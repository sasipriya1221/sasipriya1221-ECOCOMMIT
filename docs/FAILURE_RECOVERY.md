# Failure Recovery: What Broke and What Changed

ECOCOMMIT keeps failed attempts because recovery quality is part of the system’s
trustworthiness. Workflow success is never substituted for semantic evidence.

## 1. Provider failure: HTTP 429 before semantic output

Three exact-source Candidate-7 attempts stopped on the first D003 call with zero
accepted outputs. The retained Groq log later identified the actual limit:

- model: `qwen/qwen3.6-27b`;
- category: output tokens per minute (OTPM);
- free-tier limit: 1,000 output tokens/minute;
- request ceiling: 1,424 tokens;
- recorded input/output: 0/0 because rejection occurred before generation.

This ruled out semantic failure, daily-token exhaustion and retry timing as the
cause. The recovery was an explicit 900-token protocol amendment—below the
enforced ceiling—not key cycling, model switching or repeated retries.

## 2. Infrastructure recovery exposed a semantic failure

The amended Candidate-7 qualification completed without provider, schema or
validation failures. Its artifact—not the green workflow—showed:

| Case | Correct | Result |
|---|---:|---:|
| D003 | 0/5 | 0% |
| D009 | 5/5 | 100% |

Run `33957313516`, artifact `9966909942`, therefore established a genuine and
repeatable D003 role-classification defect. Candidate 7 was frozen as **FAILED**.
It was not patched and rerun until lucky.

## 3. Candidate 8: separate visible development

Candidate 8 introduced a general typed-role/AST/conservation correction on a
separate development branch. It did not reuse official-A answers.

| Iteration | Source | Visible result | Interpretation |
|---|---|---:|---|
| 1 | `1600a9d7...` | 6/24 (25%) | Broad schema, guard, clarification and normalization defects remained |
| 2 | `eabf660b...` | 18/24 (75%) | 100% selective reliability and clarification accuracy, but six cases and autonomous coverage still missed readiness |
| 3 | `b540de49...` | Running as `33970539713` | General fixes for dependency tails, nominal context, bare quantities and condition/entity boundaries |

Iteration 2 retained zero provider deferrals, zero schema/validation failures,
zero conservation failures and zero fail-open outcomes. It still did not pass:
the case gate was 95% and autonomous-coverage gate was 60%, while observed values
were 75% and 58.33%.

## 4. Engineering lessons

1. Diagnose rate limits from provider error dimensions, not generic HTTP status.
2. A green orchestration job can preserve a failing semantic result correctly.
3. Separate provider deferral, schema failure and semantic failure.
4. Never use an LLM’s fluent relation label as economic authority.
5. Make irrelevant context explicit, conserve every material fact and fail closed
   on unresolved predicates/entities.
6. Keep development, sealed preflight, qualification and official evaluation as
   distinct evidence boundaries.

## Current truth

Candidate 8 remains development evidence until its visible gates, sealed
preflight and formal qualification legitimately pass. Official Checkpoint A and
downstream authoritative checkpoints remain locked without that receipt chain.

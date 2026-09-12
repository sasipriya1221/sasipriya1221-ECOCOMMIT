# Failure Recovery: What Broke and What Changed

ECOCOMMIT preserves failed attempts because recovery quality is part of the trust boundary. Workflow success is never substituted for semantic evidence.

## Provider-limit diagnosis

Candidate-7 initially encountered Groq HTTP 429 responses before semantic output. The retained error dimension identified an output-tokens-per-minute conflict: a 1,424-token request ceiling exceeded the 1,000-token limit. An explicit, preregistered 900-token ceiling removed that infrastructure failure without changing model, evaluator, thresholds, or gold.

## Semantic failure after infrastructure recovery

With provider transport restored, Candidate-7 completed its frozen qualification and exposed a genuine semantic defect. It was frozen as **FAILED** instead of being repeatedly sampled until a favorable result appeared.

## Candidate-8 isolation and development

Candidate-8 was developed separately using permitted visible evidence. It introduced typed semantic roles, Boolean/dependency AST and conservation improvements, deterministic source grammar, and source-order action resolution. A visible action-object defect was corrected while preserving the grounded object suffix.

The repaired source `850a7b5f1f21d7951cd4a9a840c0bebbb635d594` passed:

- visible development: 24/24;
- visible regression: 12/12;
- sealed preflight: 24/24; and
- fresh formal qualification: 24/24.

Every listed stage retained zero fail-open, dropped-guard, dropped-exception, conservation, and UNKNOWN-to-authorized failures.

## Official Checkpoint-A result

Two infrastructure defects were separated from semantic evidence. Run `34465756009` stopped after one row because the runner omitted a reachability-count import. Run `34675788962` stopped before provider construction because it compared the pinned checkout with the dispatch commit SHA. Both were fixed with focused tests and exact-source CI.

The authorized terminal evaluation then ran as `34676224911`. Its retained aggregate artifact `10292342612` has archive SHA-256 `eb1b0c48b7c956c56868f176dd76b9eee3e7fd956a2dcf1f94551b9b7bb7feaa`. The frozen mathematical policy stopped after passing became impossible. Aggregate status is **FAILED**; no A PASS receipt exists, and B–E remain locked.

Candidate-8 was not patched from official material or retried until lucky.

## Candidate-9 boundary

Candidate-9 is a new candidate, not a Candidate-8 retry. Its development may use public implementation, candidate history, visible corpora, general language/grammar principles, deterministic/property/metamorphic tests, provider documentation, and non-secret infrastructure evidence.

Official-A case instructions, case-level outputs, gold labels, failure clusters, sealed gold, and formal-qualification gold are prohibited. Candidate-9 must preregister before provider-backed development and must begin again at visible development.

## Engineering lessons

1. Diagnose provider limits from their precise dimensions, not generic HTTP status.
2. Treat orchestration, provider, schema, and semantic failures as different classes.
3. Let models propose semantics; keep economic authority deterministic.
4. Preserve guards, exceptions, dependencies, and every material fact.
5. Bind every gate to exact source, configuration, evaluator, dataset, run, attempt, and artifact.
6. Stop when passing is mathematically impossible.
7. Preserve terminal failures and start a new isolated candidate when further development is justified.

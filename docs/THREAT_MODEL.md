# ECOCOMMIT Threat Model (Checkpoint E Scaffold)

This threat model covers the parallel B/C/D/E scaffolding. It records required
controls and test targets; unchecked items are not claims of completion.

## Assets

- User mandate and its provenance-preserving contract.
- Policy definitions and version identifiers.
- Evidence source registry, observations, freshness, and digests.
- Exposure decisions and progressive commitment state.
- Commit certificates, signing keys, and idempotency records.
- Payment-provider identifiers and compensation outcomes.
- Audit chain and benchmark artifacts.

## Adversaries and failure sources

- Malicious or ambiguous user/supplier text.
- Hallucinated, malformed, or prompt-injected model output.
- Compromised, unregistered, stale, or conflicting evidence.
- A caller attempting amount, merchant, currency, or transaction substitution.
- Replay, duplicate delivery, concurrency, and crash recovery.
- An operator accidentally confusing simulation with provider Test Mode.
- Log deletion/modification or selective benchmark reporting.
- Provider outages, throttling, partial failures, and ambiguous timeouts.

## Required controls and regression targets

| Threat | Required control | Adversarial test target |
|---|---|---|
| Model invents authority | Closed policy mapping; provenance and fidelity gate; deterministic exposure | Inferred/free-form amount never increases allowed exposure |
| Unknown evidence source | Registry allowlist and purpose/scope checks | Unregistered source denies |
| Stale evidence | Retrieval/expiry checks at authorization and capture boundary | Expired observation cannot advance state |
| Evidence replacement | Digest/version binding in certificate | Same source ID with changed content denies |
| TOCTOU transaction mutation | Bind merchant, transaction, amount, currency, contract, evidence, policy, expiry | Any one-field mutation invalidates certificate |
| Certificate forgery | Keyed signature/MAC with constant-time verification and key identifier | Modified payload or signature denies |
| Certificate replay | Transaction binding, expiry, idempotency record, terminal-state check | Replay cannot duplicate side effect |
| Idempotency-key collision | Store request digest with result | Same key plus different request is rejected |
| Illegal state jump | Explicit transition table and preconditions | `PROPOSED -> CAPTURED` and backward jumps deny |
| Partial side effect | Durable outcome/attempt record and explicit compensation workflow | Retry reconciles rather than blindly repeats |
| Audit tampering | Append-only hash chain with verification | Edit, deletion, or reorder is detected |
| Mode confusion | Mode in API, UI, audit, and artifact; live disabled | Simulated response cannot be labeled real/test |
| Provider ambiguity | Default-deny timeout handling and reconciliation | Unknown provider outcome cannot be reported as success |
| Benchmark cherry-picking | Frozen scenario IDs, seed, config/spec hashes, failed-case retention | Artifact records every scheduled case |

## Key handling boundary

Local certificate tests may use ephemeral test keys. Test keys and fixtures are
never production authority. Secrets must come from a secret store or CI secret,
must not enter artifacts/logs, and must be rotatable through explicit key IDs.

## Residual risks before later gates

- Unit tests cannot prove real provider behavior, webhook ordering, or Razorpay
  Test Mode semantics.
- An in-memory idempotency or audit implementation is process-local and is not a
  durability claim.
- Hash-chain tamper evidence detects modification when a trusted head/checkpoint
  exists; it is not by itself immutable storage.
- Policy correctness still requires review and frozen evaluation against economic
  loss, legitimate completion, and latency metrics.

# ECOCOMMIT Threat Model

This threat model covers the implemented local A–D components and the E evidence
framework. It is an engineering threat analysis, not a formal security audit or a
production-readiness claim.

## Assets

- Natural-language mandate and provenance-preserving contract.
- Frozen evaluation cases, metrics, thresholds, plans, and comparator artifacts.
- Policy definitions, versions, evidence authority registry, observations, and
  digests.
- Exposure decisions and progressive commitment state.
- Commit certificates, signing keys, idempotency records, and payment state.
- Provider identifiers, webhooks, and compensation results when later integrated.
- Audit chain, structured events, retained evidence, screenshots, and video.
- Repository history, CI configuration, dependency manifest, and secret boundary.

## Adversaries and failure sources

- Ambiguous, malicious, or prompt-injected user/supplier text.
- Hallucinated, incomplete, malformed, or schema-incompatible model output.
- Caller fields that claim approval, checkpoint passage, readiness, or a larger
  exposure cap.
- Compromised, unregistered, stale, revoked, conflicting, or wrong-subject
  evidence.
- Transaction, merchant, amount, currency, contract, or certificate substitution.
- Replay, duplicate delivery, concurrency, race, restart, and crash windows.
- Provider throttling, outage, ambiguous timeout, webhook reordering, or partial
  side effect.
- Operator confusion between local simulation, provider Test Mode, and live money.
- Audit deletion/modification, benchmark cherry-picking, or fabricated final
  screenshots/metrics/video.
- Committed secrets, dependency compromise, over-privileged CI, or unsafe public
  repository metadata.

## Trust zones

| Zone | Trust level | Examples |
|---|---|---|
| Untrusted input | None | Natural language, HTTP JSON, model candidate, caller status claims |
| Validated structure | Limited | Grounded contract and fidelity report; still no payment authority |
| Trusted configuration | High, local | Policy classes, exposure tiers, evidence authorities, verification keys |
| Deterministic authority | Transaction-scoped | Current evidence snapshot, exposure decision, commit certificate |
| Side-effect boundary | Highest | Exact progressive state plus certificate plus idempotency/payment adapter |
| Evidence/reporting | Non-authoritative | Audit, metrics, UI, reports; may describe but never authorize |

## Threat/control matrix

| Threat | Implemented local control | Local validation | Residual blocker |
|---|---|---|---|
| Model invents authority | Closed mapping, explicit provider candidate fields, bounded model correction, provenance/fidelity gate, trusted exposure config | Adversarial A/B tests | Candidate 2 real gate not evaluated |
| Material ambiguity guessed | Clarification/rejection based on material risk | Ambiguity and live-failure regressions | Candidate 1 failed; Candidate 2 real gate not evaluated |
| Caller forges pass/readiness | Caller claims ignored; A→B requires a typed digest-bound Candidate 2 receipt; real commit adapter absent | A/B/D boundary tests | Authoritative full A/B/C runtime bundle loader absent |
| Unknown evidence source | Registered authority/issuer/kind/scope and subject checks | B evidence tests | Durable authority service absent |
| Stale/revoked evidence | Freshness, expiry, revocation, version and observation-time checks | B tests | External evidence retrieval absent |
| Negative approval interpreted positive | Exact claim value/digest predicates | B regression | External schema governance absent |
| Evidence/transaction TOCTOU | Certificate binding and registry lock through simulated capture | Repeated race tests | Multi-process/distributed transaction absent |
| Certificate forgery/substitution | HMAC, constant-time verification, full payload/id binding | Mutation tests | KMS, rotation, access control absent |
| Illegal state jump | Explicit transition table and reconstructed-history validation | State-machine tests | Durable state store absent |
| Replay/idempotency collision | Scope/key/full-request fingerprint and stored outcome | Concurrency/collision tests | Process-local ledger only |
| Capture/refund crash window | Reconciliation and explicit compensation states | B recovery tests | Durable provider/event ledger absent |
| Audit row tampering | Strict JSON row schema and SHA-256 chain verification | Edit/reorder/malformed tests | Trusted remote head/immutable store absent |
| Concurrent local audit writers | Shared resolved-path in-process lock | 80-event concurrent test | Cross-process/distributed lock absent |
| Non-finite observability data | Finite value and aggregate-overflow rejection | D metric regressions | External telemetry pipeline absent |
| HTTP parser abuse | 64 KiB bound, JSON object/media checks, WSGI length/stream checks | D negative tests | Production server/rate limits/auth absent |
| Mode confusion | Explicit simulation/Test labels, non-test credential refusal, and permanently disabled real-money field | API/UI/browser checks plus redacted Test authentication/order evidence | Authorization/capture evidence absent; D route remains simulation-only |
| Provider ambiguity | Exact provider bindings, ECOCOMMIT idempotency, receipt recovery, and capture re-fetch | Adapter adversarial tests plus live order replay | Genuine authorization, asynchronous refund, and webhook reconciliation evidence absent |
| Benchmark cherry-picking | Frozen IDs/digests, exact coverage, error-row retention, semantic recomputation, and pre-outcome final registration/decision contract | C artifact/final-gate tests | Real registration/inputs/final run absent |
| Fabricated submission media | Blocked evidence markers and promotion rule | E readiness checks | Human review/final evidence still required |
| Secret committed | CI secret references, ignored artifacts, current-tree/history pattern scan | E local scan | Dedicated secret-scanner service/history audit not retained |
| Supply-chain drift | Hash-required binary wheels, commit-pinned actions, disabled checkout credentials, step-scoped secrets, read-only permissions | Lock dry-run and workflow-policy tests | No fully offline build bootstrap or provenance attestation |

## Key and credential boundary

Local certificate tests and D synthetic workflows use named test keys embedded in
test/local code. They are not provider credentials or production authority. The
Razorpay Test adapter reads API credentials only from environment injection; its
Actions workflows use repository secrets, refuse non-test key IDs, and retain no
credential values or provider response bodies. This proves the scoped Test
boundary, not production-grade rotation/access control. A production signing or
provider boundary still requires managed secret storage, explicit key IDs and
rotation, least-privilege access, and retained access/audit evidence.

The repository references secret names in GitHub workflows; secret values are not
part of the tracked tree. A pattern scan is helpful but cannot prove that all
historical or encoded secrets are absent.

## Audit limitations

A self-contained hash chain detects many edits but does not prevent an attacker
who can rewrite the file and unanchored head from recomputing the chain. It also
does not detect tail deletion without an independently trusted head. Production
claims require immutable/append-only storage, external head anchoring, retention,
access controls, clock discipline, backup, and recovery evidence.

## Public-repository risks

- The remote is public; only the isolated B8 validation snapshot was pushed for
  provider evidence. The integrated local main revision remains unpushed and is
  not public evidence.
- No license has been selected, so open-source reuse rights are not asserted.
- Generated artifacts, audit logs, virtual environments, and test temporary
  directories are ignored and must be reviewed before intentional retention.
- CI actions are commit-SHA pinned, checkout credentials are not persisted, jobs
  use read-only `contents` permission, and secrets are step-scoped. Supply-chain
  attestations and an offline trusted build bootstrap are not implemented.
- Provider workflows require named secrets and must remain guarded/manual; pull
  requests must not receive provider credentials.

## Remaining high-priority review

Before D/E or any payment integration passes:

1. complete a formal API/authentication/authorization and abuse-rate review;
2. implement authoritative status/evidence loading and durable state/audit stores;
3. complete a genuine Razorpay Test Checkout authorization, manual capture,
   refund, webhook delivery, duplicate-event handling, and reconciliation run;
4. replace local HMAC signing with an appropriate managed-key boundary;
5. add build provenance/attestation and a dedicated secret/dependency scan;
6. perform accessibility, cross-browser, hosted operational, backup/recovery, and
   incident-response validation; and
7. retain an independent security review and all findings/fixes.

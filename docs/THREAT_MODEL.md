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
| Caller forges pass/readiness | Caller claims ignored; A→B and D require strict digest-bound receipts; D reloads an out-of-band-hash-pinned cross-linked bundle | A/B/D boundary and loader-tamper tests | Real passing A/B/C receipts and trusted operational pin distribution absent |
| JSON parser differential or duplicate-key overwrite | Shared bounded strict decoder rejects duplicates, non-finite values, invalid Unicode scalars, excessive structure, symlinked evidence inputs, and non-object A/C/E gate artifacts | Candidate correction, A resume/aggregate, C loader, and E receipt adversarial tests | External providers and independent attestors remain outside local parser control |
| Unknown evidence source | Registered authority/issuer/kind/scope and subject checks | B evidence tests | Durable authority service absent |
| Stale/revoked evidence | Freshness, expiry, revocation, version and observation-time checks | B tests | External evidence retrieval absent |
| Negative approval interpreted positive | Exact claim value/digest predicates | B regression | External schema governance absent |
| Evidence/transaction TOCTOU | Certificate binding and registry lock through simulated capture | Repeated race tests | Multi-process/distributed transaction absent |
| Certificate forgery/substitution | HMAC, constant-time verification, full payload/id binding | Mutation tests | KMS, rotation, access control absent |
| Illegal state jump | Explicit transition table, reconstructed-history validation, and SQLite optimistic CAS | State-machine/restart/stale-writer tests | Multi-host consensus/HA absent |
| Replay/idempotency collision | Scope/key/full-request fingerprint, SQLite lease/typed result, provider idempotency, and exact replay | Thread/process concurrency, collision, restart tests | No distributed lease/queue or live crash-injection evidence |
| Capture/refund crash window | Durable payment/commitment state, exact result reconstruction, provider-scoped full-refund ledger key, exact refund-ID polling, retryable pending compensation, and expiry-bounded reconciliation | B/D recovery and lifecycle-replay tests | Small unproven crash windows, backup/disk-loss, and live provider recovery remain |
| Audit row tampering | Canonical duplicate/nonfinite-safe JSON row parsing and SHA-256 chain verification | Edit/reorder/malformed/noncanonical tests | Trusted remote head/immutable store absent |
| Concurrent local audit writers | Resolved companion lock using OS file locking | Thread and multi-process append tests | Distributed writers/remote immutable head absent |
| Non-finite observability data | Finite value and aggregate-overflow rejection | D metric regressions | External telemetry pipeline absent |
| HTTP parser/route abuse | 64 KiB bound, duplicate/nonfinite rejection, WSGI checks, optional environment-only bearer auth, exact opaque-operation body, and single-process rate limit including failed authentication | D negative/auth/rate tests | Production TLS/proxy, distributed limiter, network controls, and abuse load evidence absent |
| Mode confusion | Explicit simulation/Test labels, non-test credential refusal, read-only current-credential preflight, and permanently disabled real-money field | API/UI/browser checks plus redacted Test authentication/order evidence | Authorization/capture evidence and external webhook Test-mode configuration absent |
| Provider ambiguity | Exact provider bindings, complete redacted per-attempt retry chronology, explicit correction-attempt state, provider/local idempotency, durable result recovery, capture re-fetch, exact refund-ID polling, and raw webhook HMAC/stable event-ID binding | Provider retry/correction-state, adapter, and webhook adversarial tests plus live order replay | Genuine Candidate 2 evaluation, authorization, asynchronous refund, and webhook delivery evidence absent |
| Malicious local DB writer | Payload digests, strict models, SQLite integrity check, CAS | Corruption/unknown-field/stale-write tests | Digests are unkeyed; a writer able to rewrite DB rows and hashes is outside the boundary |
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

1. complete a formal review of the implemented API authentication,
   startup-operation authorization, webhook, and abuse-rate boundaries;
2. validate the authoritative loader, SQLite state, and OS-locked audit against
   real receipts/provider failure injection, backup/restore, and hosted storage;
3. complete a genuine Razorpay Test Checkout authorization, manual capture,
   refund, webhook delivery, duplicate-event handling, and reconciliation run;
4. replace local HMAC signing with an appropriate managed-key boundary;
5. add build provenance/attestation and a dedicated secret/dependency scan;
6. perform accessibility, cross-browser, hosted operational, backup/recovery, and
   incident-response validation; and
7. retain an independent security review and all findings/fixes.

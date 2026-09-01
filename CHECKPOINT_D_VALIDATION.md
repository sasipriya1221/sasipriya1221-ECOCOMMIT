# Checkpoint D Local Validation Report

## Verdict

**Local product/API/UI/operations validation: PASS.**

**Checkpoint D: BLOCKED — NOT PASSED.**

This verdict applies to deterministic local engineering at implementation commit
`b58329933108c9612eb33d4266b90b2952a40879`. It does not assert that Checkpoint
A, B, C, or D passed; it does not assert a Razorpay integration; and it does not
authorize real provider calls or real-money movement.

### Current-tree integration addendum

The current tree extends that historical simulation snapshot with a strict,
optional provider-Test execution boundary. It does not change the D verdict.
The default loopback server still loads no authority and denies `/v1/commit`.
When explicitly configured, the server can reload SHA-256-pinned, cross-linked
A/B/C[/D] receipts; verify current Test credentials with one read-only request;
load one separately pinned human Checkout operation; require an environment-only
bearer token; rate-limit the route; execute through SQLite-backed payment,
commitment, idempotency, and result state; and verify/deduplicate bound raw-body
webhooks. Request JSON can select only the opaque operation ID. It cannot supply
transaction data, evidence, callbacks, provider configuration, credentials, or
signing keys. No real receipts, credentials, callback, provider execution,
webhook delivery, hosted deployment, or D receipt exists today.

## Frozen-boundary check

Checkpoint A was left on its existing guarded provider-deferred retry process.
This D work did not change any Checkpoint A workflow, benchmark script, frozen
case, model setting, prompt semantic, schema, or threshold. The frozen thresholds
remain:

- case pass rate >= 90%;
- selective semantic reliability >= 95%;
- autonomous coverage >= 55%; and
- ambiguous clarification accuracy >= 80%.

## Validation environment

| Item | Value |
|---|---|
| Operating system | Windows 11 (`10.0.26200`) |
| Python | 3.14.6 |
| pytest | 8.4.2 |
| Pydantic | 2.13.5 |
| Node.js syntax check | v24.18.1 |
| Payment adapter exercised | `SIMULATED_LOCAL` only |
| Real provider credentials/API | Not present; not used |

## Local gate matrix

| Area | Validation performed | Result | Acceptance boundary |
|---|---|---|---|
| API and product workflow | Route/method/body/content-type limits, deterministic JSON, correlation propagation, WSGI length/stream failures, health/readiness separation | **LOCAL PASS** | No hosted or production deployment claim |
| Gate truth | Strict, size-bounded receipt schemas; out-of-band pin-set hash; A→B→C→D digest/revision cross-links; fixture/failing evidence rejection; post-start revalidation | **LOCAL PASS** | Real A/B/C/D receipts do not exist |
| Test execution route | Default deny; startup-pinned operation only; A–C/runtime readiness separated from the D evidence produced by the run; bearer auth, rate limit, request-authority rejection, redacted result/audit | **LOCAL PASS** | Human callback, current provider credentials, external webhook setup, and hosted run absent |
| A-to-B boundary | Current fidelity validator, closed policy mapping, exposure decision, certificate, and commitment transitions composed from a fixed synthetic fixture | **LOCAL PASS** | Synthetic A-pass evidence is interface evidence only |
| Simulated end-to-end flow | `PROPOSED -> AUTHORIZED -> RESERVED -> CAPTURE_ALLOWED -> CAPTURED` through `SIMULATED_LOCAL` | **LOCAL PASS** | No Razorpay call and no real money |
| Negative workflow | Incomplete A fixture releases zero obligations; injected capture failure voids the reversible simulated hold and ends `FAILED` | **LOCAL PASS** | Provider timeout/webhook behavior remains untested |
| Audit | Hash chaining, tamper detection, strict record types/timestamps/hashes, fsync, refusal after corruption, OS-level companion locking, and multi-process concurrent append | **LOCAL PASS** | Single-host append file is not immutable remote/WORM storage |
| Durable execution | SQLite WAL/FULL-sync JSON CAS, typed idempotent result replay, payment/commitment restart recovery, provider crash-window reconstruction, pending-compensation retry, webhook event index | **LOCAL PASS** | Single host only; no HA, backup/restore, disk-loss, malicious DB-writer, or live crash-injection evidence |
| Observability | Finite counters/gauges/histograms, overflow rejection, structured events, route/outcome/correlation, audited HTTP-boundary denials | **LOCAL PASS** | No external collector, SLO, alert, or retention evidence |
| Economic-state UI | Requested/authorized/simulated-captured values and progressive state trace rendered from API output | **LOCAL PASS** | Not final submission evidence |
| Failure UX | Status loss resets every gate to unavailable; malformed backend responses, blocked-A, and capture failure remain visibly closed with correlation status | **LOCAL PASS** | No formal accessibility audit or user study |
| Responsive UI | Browser render at the normal desktop viewport and 390 × 844; single-column mobile grids and no horizontal document overflow | **LOCAL PASS** | No cross-browser/device matrix |
| Reproducibility | Machine-readable three-scenario CLI and loopback-only local UI/API server | **LOCAL PASS** | Dependency lock and independent clean-machine reproduction remain E work |

## Defects found and fixed

1. **The old simulation was label-only.** It did not exercise the deterministic
   A-to-B, exposure, certificate, commitment, or payment components. A fixed,
   reproducible, explicitly synthetic workflow now covers success, blocked-A,
   and capture-failure cleanup without opening the real commit route.
2. **Metrics accepted NaN and infinity.** Those values could make a later JSON
   response unserializable. Metric inputs and aggregate overflow now fail before
   entering a snapshot.
3. **Two audit-log objects could race.** Locks were instance-local, allowing
   concurrent users of the same path to fork or lose the chain. Resolved paths
   now share one in-process lock, with concurrent regression coverage.
4. **A rehashed malformed audit row could pass structural checks.** Audit
   verification now checks exact integer sequences, aware timestamps, finite JSON
   payloads, non-empty identity fields, and lowercase SHA-256 shapes before hash
   validation.
5. **HTTP parser denials were outside the audit trail.** Method, path, media-type,
   malformed JSON, size, content-length, incomplete-body, and missing-stream
   denials are now structured, counted, and appended without weakening the
   closed response if an observability sink fails.
6. **WSGI body failures were under-specified.** Invalid/negative length, missing
   input streams, non-byte bodies, oversized bodies, and truncated reads now
   return bounded no-side-effect errors.
7. **The UI could retain stale accepted gate cards after status loss.** It now
   resets all gates to `UNAVAILABLE`, keeps commit blocked, and keeps real money
   explicitly out of scope.
8. **Economic state and failure recovery were not visible.** The console now
   renders exposure values, stage transitions, blocked/failure outcomes, and
   correlation feedback.
9. **A non-JSON backend response leaked a raw parser error and could omit the
   advertised correlation status.** The browser now emits bounded failure copy
   and explicitly says when a service correlation is unavailable.
10. **Gate files could not become runtime authority.** Presence or caller claims
    were unsafe, so the loader now requires an out-of-band hash for the pin file,
    hashes every strict JSON receipt before parsing, rejects duplicates/nonfinite
    values/unknown fields/symlinks, and verifies every upstream/revision link.
11. **D and E created an execution cycle.** E is downstream packaging, while D
    is evidence produced by the integrated run. The status contract now permits
    an A–C-authorized compensated Test run, requires A–D for final integration,
    and keeps E separate; real-money readiness remains permanently false.
12. **Process memory could lose idempotency, payment, and commitment state.** A
    SQLite WAL/FULL-sync store, optimistic CAS, typed result allowlist, stale
    lease recovery, provider-side idempotency binding, and restart regressions
    now cover the claimed single-host runtime.
13. **A completed provider mutation could precede the local journal result.**
    Payment operations reconstruct only an exact transaction/idempotency-bound
    result from durable state. A completed lifecycle replays after restart with
    no new provider call; pending compensation remains retryable.
14. **The API had no safe provider adapter authority boundary.** Only an
    immutable startup-pinned operation can execute. Authentication, a global
    single-process rate limit, strict JSON duplicate/nonfinite rejection,
    before/after audit, and explicit unknown-provider-call reconciliation states
    protect the HTTP boundary.
15. **Webhook verification was a detached helper.** The raw endpoint now uses
    Razorpay's documented signature and event-ID headers, binds capture/refund
    entities to the prepared order/payment/amount/currency, tolerates event
    ordering, rejects ID collisions, and exports a digest-bound redacted set.
16. **A pending refund could remain pending forever locally.** The refund
    operation no longer journals a pending response as completed; retries fetch
    the exact refund by ID and advance only on a bound `processed` response.
17. **Expiry recovery was too broad.** Post-expiry cleanup now requires exact
    durable payment binding; a merely reserved payment also requires a persisted
    capture-authorized commitment, so expiry cannot create fresh authority.
18. **Late webhook redelivery could look like an ID collision.** Deduplication
    now compares stable signed-event fields, retains the first receipt timestamp
    and digest, and still rejects a changed body under the same provider event ID.
19. **Startup and HTTP hardening order was incomplete.** Evidence and all local
    secrets are validated before credential preflight, failed authentication is
    rate-limited, and audit input must be strict canonical JSON.

## Reproduction commands executed

Focused D suite:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_checkpoint_d_status.py tests\test_checkpoint_d_audit_observability.py tests\test_checkpoint_d_workflow.py tests\test_checkpoint_d_demo_server.py tests\test_checkpoint_d_api_service.py tests\test_checkpoint_d_ui.py --basetemp .test-tmp-d-validation-focused -p no:cacheprovider
```

Result: **44 passed**.

Full regression:

```powershell
.venv\Scripts\python.exe -m pytest --basetemp .test-tmp-d-validation-full -p no:cacheprovider
```

Result: **192 passed**.

Current-tree focused D suite: **76 / 76 passed**. Current-tree full deterministic
suite: **368 / 368 passed**. These additions are local fake-transport and
same-host evidence, not provider or hosted evidence.

A separate no-hardlink clone at
`652cc68075854531780df501373f1c6a59704e07` used the exact hash-locked
dependencies in its clean-environment virtual environment and passed **368 / 368**,
compilation, dependency consistency, JavaScript syntax, readiness, diff, and
clean-status checks. This is same-host clean-environment evidence, not an
independent reproduction.

Additional checks:

```powershell
.venv\Scripts\python.exe -m compileall -q src scripts
.venv\Scripts\python.exe -m pip check
node --check ui\app.js
.venv\Scripts\python.exe scripts\checkpoint_d_demo.py --scenario HAPPY_PATH --compact
.venv\Scripts\python.exe scripts\checkpoint_d_demo.py --scenario CHECKPOINT_A_BLOCKED --compact
.venv\Scripts\python.exe scripts\checkpoint_d_demo.py --scenario CAPTURE_FAILURE --compact
```

The three scenario outcomes were respectively `SIMULATED_CAPTURED`,
`SIMULATED_BLOCKED`, and `SIMULATED_FAILED_CLOSED`. Every artifact says
`SIMULATED_LOCAL`, `counts_as_checkpoint_evidence: false`,
`real_provider_called: false`, and `real_money_moved: false`.

The loopback console was also exercised through its rendered browser flow. The
five gate cards remained blocked, the real-money card remained disabled, and all
three scenarios rendered their expected economic states. No screenshot from this
development validation is promoted as final submission evidence.

## Remaining blockers

- Candidate 1's frozen A gate is mathematically failed; corrected Candidate 2 has
  not been remotely evaluated.
- Checkpoints B and C are locally validated but not passed.
- The default local server deliberately loads no authoritative checkpoint
  evidence and denies provider execution. The optional loader has no real A/B/C
  receipts to load.
- A startup-pinned Test adapter, durable state, raw webhook endpoint, and
  operator-only UI control exist. No genuine Checkout, capture, refund, webhook
  delivery, or integrated D provider run used them.
- The webhook record proves a signature and binding to a Test-key operation; it
  does not independently prove that the configured Dashboard webhook endpoint
  was Test Mode. Final evidence must retain that external configuration fact.
- The bundled WSGI server is loopback development software. Public TLS hosting,
  reverse-proxy authentication review, IP/network controls, rate-limit load
  evidence, backups, monitoring, alerts, and SLOs remain external/operational.
- SQLite/audit are locally cross-process on one host; no production HA or
  malicious-storage-tamper claim is made.
- Hosted UI/API execution, independent security review, operational alerting/SLO
  evidence, and the final integrated product run remain undone.

Until those blockers are resolved, the only accurate checkpoint label is:

**BUILT + LOCALLY VALIDATED; BLOCKED; NOT PASSED.**

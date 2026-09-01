# Checkpoint D Local Validation Report

## Verdict

**Local product/API/UI/operations validation: PASS.**

**Checkpoint D: BLOCKED — NOT PASSED.**

This verdict applies to deterministic local engineering at implementation commit
`b58329933108c9612eb33d4266b90b2952a40879`. It does not assert that Checkpoint
A, B, C, or D passed; it does not assert a Razorpay integration; and it does not
authorize real provider calls or real-money movement.

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
| Gate truth | Evidence required for `PASSED`, prerequisite ordering, immutable status snapshot, caller authority claims ignored; production A→B now requires a typed digest-bound Candidate 2 receipt | **LOCAL PASS** | No authoritative full A/B/C runtime bundle loader installed |
| Real commit route | Default-deny with missing adapter, including a synthetic all-gates-passed status; simulation runner cannot be reached from `/v1/commit` | **LOCAL PASS** | Real A/B/C evidence and execution adapter absent |
| A-to-B boundary | Current fidelity validator, closed policy mapping, exposure decision, certificate, and commitment transitions composed from a fixed synthetic fixture | **LOCAL PASS** | Synthetic A-pass evidence is interface evidence only |
| Simulated end-to-end flow | `PROPOSED -> AUTHORIZED -> RESERVED -> CAPTURE_ALLOWED -> CAPTURED` through `SIMULATED_LOCAL` | **LOCAL PASS** | No Razorpay call and no real money |
| Negative workflow | Incomplete A fixture releases zero obligations; injected capture failure voids the reversible simulated hold and ends `FAILED` | **LOCAL PASS** | Provider timeout/webhook behavior remains untested |
| Audit | Hash chaining, tamper detection, strict record types/timestamps/hashes, fsync, refusal after corruption, and 80 concurrent writes through two log instances | **LOCAL PASS** | Process-local file plus hash chain is not immutable or multi-process durable storage |
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
- The local server deliberately loads no authoritative checkpoint evidence.
- `/v1/commit` has no execution adapter and always denies.
- A Razorpay Test adapter plus credential/order evidence exists, and a local
  Checkout/capture/refund continuation is implemented. No genuine Checkout,
  capture, refund, webhook delivery, or integrated D provider run exists.
- Audit, status, metrics, and idempotency boundaries remain local/process-level;
  no production durability or high-availability claim is made.
- Hosted UI/API execution, independent security review, operational alerting/SLO
  evidence, and the final integrated product run remain undone.

Until those blockers are resolved, the only accurate checkpoint label is:

**BUILT + LOCALLY VALIDATED; BLOCKED; NOT PASSED.**

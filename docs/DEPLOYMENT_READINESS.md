# Checkpoint D hosted-deployment readiness contract

This is a provider-neutral preparation contract for a future single-host public
TLS deployment. It does **not** show that a host, DNS name, certificate, backup,
monitor, webhook route, or Checkpoint D exists. No live-money mode is supported.

## Runtime boundary

`deploy/wsgi.py` is the importable production WSGI entrypoint. It reuses the
authoritative Checkpoint D application factory, evidence loader, prepared Test
runtime, and fixed UI from the exact source checkout. It never starts a listener
or terminates TLS. A separately selected, hash-pinned production WSGI server must:

- run from the exact reviewed checkout with `src` importable;
- import `deploy.wsgi:application` only after the environment is complete;
- bind one worker to loopback `127.0.0.1:<port>` (or an equivalently private
  local socket) and never expose that listener publicly;
- run exactly one application instance and one WSGI worker; and
- be supervised with bounded graceful shutdown and restart behavior.

The bundled `scripts/checkpoint_d_server.py` remains the loopback development
server. It is not the production listener.

The one-instance/one-worker restriction is deliberate. The durable state is a
single-host SQLite boundary and the authenticated commit limiter is in-process.
Horizontal replicas, multiple WSGI workers, a shared queue/database, and a
distributed application limiter have not been implemented or validated.

## Environment contract

`deploy/ecocommit.env.example` contains no usable secret. Required non-secret
values are:

| Variable | Required value or rule |
|---|---|
| `ECOCOMMIT_D_PUBLIC_HOST` | One exact lowercase multi-label DNS hostname; no wildcard, scheme, port, or trailing dot |
| `ECOCOMMIT_D_TRUSTED_PROXY_CIDRS` | Minimal canonical CIDR(s) for only the local/reachable TLS proxy; never `0.0.0.0/0` or `::/0` |
| `ECOCOMMIT_D_TLS_TERMINATION` | `TRUSTED_REVERSE_PROXY` |
| `ECOCOMMIT_D_EDGE_RATE_LIMITING` | `EXTERNAL_SHARED_LIMITER_REQUIRED` |
| `ECOCOMMIT_D_MAX_REQUEST_BODY_BYTES` | Canonical decimal `65536`, matching the application boundary |
| `ECOCOMMIT_D_INSTANCE_COUNT` / `ECOCOMMIT_D_WORKER_COUNT` | Both canonical decimal `1` |
| `ECOCOMMIT_D_PROVIDER_MODE` | `DISABLED` or `RAZORPAY_TEST_MODE`; no live mode exists |
| `ECOCOMMIT_D_PERSISTENT_ROOT` | Existing non-symlink persistent-volume directory |
| `ECOCOMMIT_D_AUDIT_PATH` | Absolute file path below the persistent root |

Pinned evidence is optional in disabled mode. If any evidence variable is set,
all of `ECOCOMMIT_D_EVIDENCE_ROOT`, `ECOCOMMIT_D_PINS_PATH`, and
`ECOCOMMIT_D_PINS_SHA256` are required. Startup passes them through the existing
strict loader before serving traffic.

`RAZORPAY_TEST_MODE` additionally requires the three prepared-operation variables
shown in the example file. The SQLite state path must be below the persistent
root and distinct from the audit path. Secrets (`ECOCOMMIT_D_API_TOKEN`,
`ECOCOMMIT_D_SIGNING_SECRET`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and
`RAZORPAY_WEBHOOK_SECRET`) must come from the runtime secret store, must not be
written to an environment file or image layer, and retain the existing Test-key
and length validation. The API token must be 32–256 visible ASCII bytes. Existing
state/audit files are compared by file identity as well as resolved path, so hard
links cannot collapse the mutable database and append-only audit stream onto one
file. Constructing the app in this mode performs the existing
read-only Razorpay credential preflight; do that only during an explicitly
authorized deployment startup.

Configuration acceptance is local coherence only. In particular, the
`ECOCOMMIT_D_EDGE_RATE_LIMITING` value is an assertion of required architecture,
not evidence that a limiter is deployed.

## TLS and reverse-proxy policy

`deploy/nginx.conf.template` and `deploy/proxy-policy.inc.template` are a reviewed
single-host baseline. Replace only the `@@...@@` tokens, validate the rendered
configuration with the selected nginx version, and retain these properties:

- unknown HTTP hosts are dropped and unknown TLS Host/SNI values are rejected;
- only TLS 1.2 and 1.3 are enabled, with a certificate for the exact public host;
- the backend is loopback-only;
- the proxy **replaces** all client-supplied `Forwarded`, `X-Forwarded-*`, and
  `X-Real-IP` values instead of appending to them;
- the application independently checks proxy source CIDR, exact Host,
  `X-Forwarded-Host`, HTTPS scheme, port 443, and a single forwarded client IP;
- request buffering is enabled and bodies over 64 KiB are rejected at both proxy
  and application boundaries; the proxy removes `Transfer-Encoding`, while the
  application rejects any surviving transfer encoding or noncanonical content
  length; and
- the edge rate limits `/v1/commit`, the webhook route, general traffic, and
  concurrent connections before requests reach Python.

The template limiter is shared across nginx workers on one host. Any upstream
CDN, load balancer, multi-host routing, or autoscaling requires a separately
configured distributed limiter with equivalent or stricter limits. Never trust
a public load-balancer CIDR larger than necessary, and never expose the WSGI port
as a health-check shortcut. Health probes must traverse the trusted proxy policy.

Before evidence can be retained, verify externally: DNS ownership, certificate
chain and renewal, HTTP-to-HTTPS redirect, unknown-host rejection, current TLS
scan, HSTS behavior, body-limit behavior, rate limiting, direct-backend denial,
and webhook routing from the Razorpay Test Dashboard. None has been run here.

## Persistent volume and recovery requirements

The persistent volume must contain the audit log, its companion lock, and—when
Test execution is enabled—the SQLite database and its SQLite-managed files. It
must be encrypted at rest, access-controlled to the service identity, capacity
monitored, and excluded from ephemeral release replacement. Evidence and prepared
operation inputs should be separate read-only mounts pinned by out-of-band hashes.

A deployment is not ready until an operator has documented and tested:

1. an RPO/RTO, retention period, encryption/key ownership, and off-host backup;
2. an application-consistent SQLite backup (SQLite backup API, a validated volume
   snapshot, or a quiesced copy—not an uncoordinated copy of a running database);
3. coordinated retention of the audit file and a recorded/externally anchored
   audit head so deletion or rollback is detectable outside the host;
4. restore into an isolated host followed by SQLite integrity checks, audit-chain
   verification, pinned-evidence reload, and a no-provider smoke test; and
5. a recorded restore drill with timestamps, hashes, software revision, operator,
   observed RPO/RTO, and explicit pass/fail status.

Local hash chaining does not make the audit log immutable and a configured volume
does not prove backup or restore.

## Monitoring and alert requirements

Collect edge access/error logs and service metrics without Authorization,
cookies, request bodies, provider secrets, Checkout signatures, or raw webhook
payloads. At minimum, alert on:

- TLS certificate expiry/renewal failure, DNS or external health failure, proxy
  5xx/upstream failures, restart loops, and disk/inode pressure;
- sustained 401/403/413/421/429 responses and unexpected direct-backend attempts;
- `/healthz` liveness failure and `/readyz` Test-path readiness changes (neither
  endpoint is checkpoint evidence);
- `AUDIT_INTEGRITY_UNAVAILABLE`, provider-call ambiguity, reconciliation-required
  outcomes, webhook signature failures, and durable-state errors; and
- backup failure, missed backup, restore-drill failure, and stale monitoring data.

Define owners, paging route, severities, acknowledgement targets, maintenance
windows, and retained test notifications. A dashboard screenshot alone is not an
alert-delivery test.

## Local smoke versus external evidence

The focused tests validate strict environment parsing, canonical count/size
values, bounded API tokens, proxy-source and forwarded-header rejection,
exact-host enforcement, ambiguous-body-framing rejection, 64 KiB defense in
depth, state/audit hard-link separation, safe blocked startup with the provider
disabled, the importable WSGI entrypoint, and required template directives. They
make no network call and do not bind a public port.

Checkpoint D remains **NOT RUN/BLOCKED externally** until A, B, and C have passed
with authoritative receipts and the hosted TLS, provider lifecycle, operations,
backup/restore, monitoring, and integrated evidence is executed and retained.

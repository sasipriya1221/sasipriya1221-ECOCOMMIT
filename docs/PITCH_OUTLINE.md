# Five-Minute Pitch Outline

This outline is ready for rehearsal, but its final metric, Razorpay, screenshot,
and video evidence slots remain blocked. Bracketed evidence cues may be filled
only from the retained final bundle described in `SUBMISSION_EVIDENCE.md`.

## 0:00–0:35 — The problem

Open with the irreversible-action gap:

> AI can interpret a procurement instruction, but fluent interpretation is not
> financial authority. One guessed condition, stale approval, or replayed payment
> can create real economic loss.

Show a single ambiguous procurement example. Do not claim a final error rate.

## 0:35–1:10 — The thesis

State the design in one sentence:

> ECOCOMMIT lets AI propose economic meaning, then requires deterministic policy,
> authoritative evidence, bounded exposure, and a transaction-bound certificate
> before an irreversible action can advance.

Name the two simultaneous objectives: high selective semantic reliability and
useful autonomous coverage, followed by lower preregistered Total Economic Loss.

## 1:10–2:05 — How it works

Walk left to right through the trust boundary:

1. untrusted natural-language interpretation;
2. provenance-preserving contract plus fidelity/abstention gate;
3. closed policy-class mapping;
4. registered fresh evidence and deterministic exposure cap;
5. progressive commitment and transaction-bound certificate; and
6. simulated or explicitly verified provider Test Mode adapter.

Emphasize that observability reports decisions but never grants authority.

## 2:05–3:20 — Demonstrate the safety behavior

Use `DEMO_RUNBOOK.md`:

- show the five-stage `SIMULATED_LOCAL` happy path;
- switch to `CHECKPOINT_A_BLOCKED` and show zero released authority; and
- inject `CAPTURE_FAILURE` and show zero captured amount plus hold cleanup.

Say “synthetic local compatibility demo” before the first click and keep the
simulation banner visible. Do not imply Razorpay execution.

## 3:20–4:05 — Evidence, not theater

Explain the checkpoint discipline:

- A has frozen live semantic thresholds and cannot pass on a partial run;
- B, C, and D have locally passing adversarial suites but remain blocked on their
  real dependencies;
- C retains error rows and forbids preliminary artifacts from becoming final; and
- E keeps absent screenshots, video, provider results, and final metrics visibly
  blocked.

Final evidence cue: **[BLOCKED — insert only the retained A/B/C/D/E summary after
all gates pass.]**

## 4:05–4:35 — What broke and what that proves

Choose three concrete examples from `ENGINEERING_LOG.md`:

- provider/schema failures led to immutable per-case resumability;
- a certificate-only capture gap led to exact progressive-state/hold binding; and
- a label-only UI simulation led to a real deterministic local component flow
  with visible blocked and cleanup paths.

The message is not that nothing failed; it is that failures became regression
tests and retained evidence.

## 4:35–5:00 — Close

Close on the product boundary:

> ECOCOMMIT is not another agent that promises to be careful. It is a protocol
> that makes economic authority explicit, bounded, inspectable, and revocable
> until the final verified boundary.

Final results cue: **[BLOCKED — do not insert benchmark percentages, TEL savings,
Razorpay success, screenshots, or a video URL until the final evidence manifest
is complete.]**

## Delivery checklist

- Finish within 5:00; rehearse once with a visible timer.
- Say `SIMULATED_LOCAL` every time the local payment path is shown.
- Never use “passed” for a locally validated but blocked checkpoint.
- Keep one slide/visual per idea; avoid unreadable architecture detail.
- If the live demo fails, switch to the CLI fallback and keep the failure visible.
- End with the exact next gate, not a vague production-readiness claim.

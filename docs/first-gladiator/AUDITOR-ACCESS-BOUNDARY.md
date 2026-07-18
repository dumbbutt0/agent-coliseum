# Auditor-access boundary — owner-confirmed, not autonomously detected

*Owner directive 2026-07-18, accepting Council verdicts 001747 and 001760.*

## The claim, stated plainly

> **The launcher does NOT autonomously detect auditor-access failures.**
> It supports **owner-confirmed classification** of otherwise unattributable
> auditor-access failures.

## Why the autonomous premise was retired

An earlier design tried to have the launcher decide, by itself, whether a
failed audit session failed because of quota/credentials rather than because
of the candidate. It was routed and **blocked three times**, and the findings
established that the capability does not exist at this interface:

- **No distinguishable exit code.** Across 36 recorded launcher failures —
  quota exhaustion, content-filter interruption, crashes, timeouts — the
  provider exits `1` every time.
- **No trustworthy provenance in the logs.** Session stderr interleaves
  provider messages with bulk material the auditor *read* (chain events,
  request bodies, source, test text — this repository's own tests contain the
  phrase "usage limit"). No positional or shape heuristic over that stream can
  establish that a matched line came *from* the provider, and any fixed window
  can also *suppress* a genuine diagnostic printed before later output.
- **No causal attribution.** Even a correct global availability check cannot
  show that *this* session failed *because* of access; an ordinary failed
  audit followed by an unrelated outage would have its strike wrongly skipped.

Continuing to patch heuristics would have weakened the Council's evidentiary
standard: contaminated log text could control Council state, a genuine
candidate failure could be excused as provider trouble, and a later outage
could retroactively alter unrelated failures.

## What ships instead

1. **Every unsuccessful launch consumes a strike by default.** No
   classification suppresses one.
2. **Classification survives as an untrusted diagnostic hint**, recorded for
   humans. It cannot suppress a strike, hold a request, alter candidate
   status, or trigger resumption.
3. **`ACCESS_BOUNDARY_CONFIRMED`** — human-only and one-time-token-gated, so
   no agent can forge it — binds the request, the *specific* launcher failure
   event, the observed condition, the observation time, the attesting
   authority, and the requested disposition.
4. **The original strike is never erased.** The immutable chain keeps it
   exactly as it happened; the attestation is a *compensating* record that
   excludes that one bound attempt from the **effective** count
   (`effective_launcher_failures`). Replay stays deterministic and the record
   stays honest.
5. **One attempt, one request.** An attestation never latches into a general
   "provider unavailable" state, so a later failure is never excused by an
   earlier outage.
6. **Without an attestation, the strike ceiling is authoritative**, whatever
   the log text says.

## Operating model

The sound loop during a real outage:

```
audit fails -> strike counted -> ceiling pauses the request if reached
            -> other authorized work continues
            -> owner attests the access outage for that attempt
            -> effective capacity restored -> audit relaunched
```

A completely new audit execution is still required before any verdict, and the
candidate retains **zero integration authority** throughout. The owner acts as
an *exception authority* supplying one fact agents cannot observe — not as the
day-to-day orchestrator.

## Autonomy boundary this establishes

| Level | Who decides |
|---|---|
| Building, testing, evidence, recovery, routine audit | fully autonomous |
| Missing evidence → stop the affected transition, continue safe unrelated work | autonomous fail-safe |
| Provider access, quota, credentials — facts outside the agents' observable environment | **owner-attested** |
| Constitutional policy, scientific risk, permissions, goals | owner-controlled |

This incident moves only provider-access diagnosis into the owner-attested
level. Ordinary construction and audit repair remain autonomous.

## Preserved from the prior work

Launcher-death lock recovery, stranded-claim recovery, diagnostic evidence
capture, and the failure-budget accounting improvements all remain and are
unaffected by the retirement of autonomous attribution.

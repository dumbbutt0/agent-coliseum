# Audit Integrity — the every-slice-audited guarantee

*Puts on record what is mechanically enforced, what is convention, and the
operating posture for auditor-credential outages. Owner-directed 2026-07-17
("make sure every slice gets properly audited by Codex"). Doc-only: this file
changes no behavior.*

## 1. The guarantee is mechanical, not policy

Nothing can be recorded as integrated without an independent Codex verdict
bound to the exact commit:

- **GO-only integration.** `CHANGE_INTEGRATED` is reachable only from the `go`
  state, and `go` is reachable only via a codex-sender `AUDIT_GO` /
  `AUDIT_GO_WITH_CONDITIONS` from `claimed` (`tools/council/state_machine.py`
  transition table; enforced at the single chain writer,
  `tools/council/events.py::append_event` → `state_machine.check`).
- **Commit binding.** Once `AUDIT_REQUESTED` pins `target_commit`, every
  downstream non-exempt event must carry the SAME commit — "approvals do not
  transfer between commits" (`state_machine.py`, `_BOUND_FROM` check).
  `publish_request` additionally forces `target_commit` == repo HEAD with a
  clean tree at publish time (`tools/council/publish.py`).
- **Role authority.** `SENDER_ALLOWED` (`tools/council/schemas.py`) restricts
  verdict events to codex and integration to claude; human-authority events
  require S/KEY one-time tokens no agent can mint.
- **Conditional gate.** `AUDIT_GO_WITH_CONDITIONS` refuses integration until a
  human `CONDITIONS_SATISFIED` (or the fail-closed Class-A delegated
  `CONDITIONS_AUTO_SATISFIED`).
- **Regression-locked.** `tests/test_council_state_machine.py`
  (`test_integration_only_from_go`, `test_integration_commit_bound`).

**Consequence: build-ahead is safe.** Any amount of unaudited work may
accumulate on branches or in sandboxes — none of it has integration authority
until a codex GO lands on the exact commit containing it.

## 2. Audit grain: one folded audit per rollout slice

The ratified model (HSC design §8.2, §15): section/component work produces
sealed evidence, and integration happens through **one ordinary source request
over a single assembled commit**, whose scope manifest must exactly equal the
real diff. Per-component interim checkpoint audits are NOT the model — the
HSC-B split checkpoints (safe-003/004/005) each blocked or died on
environment, burning bounded-loop cycles without integrating anything. Do not
repeat: build the slice complete, then route ONE commit-bound integration
audit. The 5-cycle-per-request and 3-consecutive-launcher-failure ceilings
stay as-is.

## 3. Known residual (owner-accepted)

Codex-ness of a verdict is enforced by the role→event-type authority map plus
the fact that only `codex_launcher` spawns role=codex sessions — an env/config
boundary, not a per-event cryptographic signature (only HUMAN events carry
tokens). Under the owner's 2026-07-11 reframe (strictly local, single-operator;
audits = logic/state-consistency correctness, not adversarial security) this is
accepted and recorded, not hidden. A cryptographic codex identity would be a
future protected-path slice, separately audited.

## 4. Credential-outage runbook (auditor quota/credential exhaustion)

Worked example: events `001658` (WATCHER_ERROR — Codex session exited on a
hard usage-limit, "try again Jul 22") → `001659` (REQUEST_CANCELED, reason
recorded as an environmental credential boundary, NOT a candidate verdict).

When the auditor's credentials/quota are exhausted (as opposed to the content
filter or a substantive failure):

1. **Do NOT relaunch `codex_launcher`.** Each doomed session burns one of the
   3 consecutive-failure strikes and then forces `AUTONOMY_PAUSED` — a
   human-gated pause that helps nobody. Hold the launcher until quota returns.
2. **Cancel the stale request** (claude self-revoke is authorized — cancel
   revokes, never grants), with an honest reason naming the credential
   boundary. This unbinds the tree so building may continue.
3. **Keep building** on clean recovery commits — safe per §1.
4. **When credits return**, route the COMPLETE slice as one fresh commit-bound
   request per §2.

Mechanization (future, separately-audited slice — spec only, NOT built here):
`codex_launcher` should classify a credential/usage-limit exit distinctly so it
does not count toward `MAX_CONSECUTIVE_FAILURES`, idles with a logged reason,
and resumes when the auditor is available. Until that slice exists, this
runbook is the posture.

## 5. Scientific-audit mandate

Per `COLISEUM-SCIENTIFIC-CHARTER.md` §6: for experiment-bearing slices, the
audit scope includes whether the experiment isolates the claimed variable —
the auditor may rule "implementation correct, but the experiment does not
identify the claimed cause," and that blocks promotion exactly like a code
defect. Audit requests for such slices must put the design questions in scope
explicitly (as this slice's request does for the m7 calibration rule).

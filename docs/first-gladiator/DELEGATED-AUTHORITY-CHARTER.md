# Delegated-Authority Charter — Design Source (smallest first charter)

> **Status: READ-ONLY design source for council adoption + owner ratification.** Nothing in this document is
> implemented or active. It specifies the SMALLEST bounded delegated-authority mechanism so the council engine
> can auto-satisfy a narrowly-scoped class of conditional verdicts without a per-verdict owner passphrase —
> **only after** (a) the enforcement code is Codex-audited and integrated, and (b) the owner ratifies the
> charter with ONE `POLICY_AMENDED` token via `amend-policy`. First charter is deliberately minimal:
> **structural `source` work only, Codex-only audit, Class-A boundary conditions only.** Experiments,
> hidden-evaluation, training, Fable activation, and broader envelopes are explicit deferrals.

## 1. Problem & goal

Requiring the owner's S/KEY token on every `AUDIT_GO_WITH_CONDITIONS` is an operational bottleneck (e.g.
`t0a-dataset-export-002`, whose two conditions were pure scope-affirming boundaries). The goal is **bounded,
revocable, machine-enforced owner delegation**: the deterministic council engine auto-satisfies conditions that
provably fall inside a ratified envelope; everything else still fails closed to the owner token. This replaces
repeated approvals with one owner delegation — it does **not** remove council review.

## 2. Non-negotiable boundary

Do **not** weaken: append-only hash-chained history · independent audits · role separation · hidden-evaluation
controls · human-identity binding (S/KEY) · critical-violation vetoes · the owner's revocation/emergency power.
**No generic "auto-approve-everything" flag.** The delegation mechanism **cannot be modified from inside the
delegated program** (`no_protocol_self_modification`). After ratification the owner is a **veto/exception
authority**, not a per-verdict approval service.

## 3. Grounded reuse (this mechanism adds almost no new primitive)

- **Template = the existing `AUTO_APPROVED` path.** For a policy-eligible experiment, `claude_watch` appends
  `POLICY_VALIDATION_REQUIRED` then a **claude-sender, tokenless `AUTO_APPROVED`** whose authority is a recorded
  `policy.evaluate` pass — fail-closed, any reason → human gate (`claude_watch.py:195-219`,
  `policy.py:356-500`). Delegated condition-satisfaction copies this exactly.
- **Charter home = the policy file, one owner token to ratify.** A new **code-defined `POLICY_VERSIONS[3]`**
  carrying the `OwnerDelegationProfile`, activated via the existing `amend-policy` → single `POLICY_AMENDED`
  (human-sender + `human_token`, root-anchored to the `/etc/coliseum` checkpoint, monotonic `v2→v3`, atomic
  rollback) — the SC-7 precedent (`policy.py:169-260`, `cli.py:109-141`; live precedent event `000485`
  moved v1→v2). `is_code_defined_version` (`policy.py:160`) means the owner can only move between reviewed
  versions, never install arbitrary policy.
- **`protected_paths` guard already prevents self-authorization.** Any request `scope` touching
  `tools/council/`, `autonomy_policy.json`, or `PROTOCOL.md` fails `no_protocol_self_modification`
  (`policy.py:492-497`) → the delegated path is refused → owner gate. So the delegation cannot be used to change
  the delegation.
- **One state-machine gate** already unlocks integration for conditional verdicts (`state_machine.py:144-151`,
  set at `:207-208`); we extend it, we do not replace it.

## 4. Threat model (delegated authorization)

| Threat | Defense (in this design) |
|---|---|
| A model forges an owner token / human satisfaction | Impossible: `CONDITIONS_SATISFIED` stays human-only + S/KEY (`schemas.py:117,135`); the new delegated event is a **distinct** claude-sender event, never a human token. |
| Claude auto-approves its own work | `evaluate_delegation` requires a codex `AUDIT_GO_WITH_CONDITIONS` verdict; role separation (`validate_sender`) means claude cannot emit any `AUDIT_*`. Neither auditor may emit builder/integration events. |
| Codex expands authority through conditions | The engine classifies each condition (Class A/B/C) deterministically; a Class-C condition (new authority/protected-path/schema/policy/training/external/hidden-disclosure) **cannot** auto-satisfy — it fails closed to the owner. |
| Condition-hash substitution | Each condition object carries a `condition_hash` computed over the verdict's authoritative `conditions[]` text; `evaluate_delegation` re-derives it from the chain; a mismatch fails closed. |
| Envelope escape / out-of-scope request | The `OwnerDelegationProfile` enumerates authorized task kinds/capabilities/paths; anything outside → fail closed. |
| Cross-request delegation reuse | The auto-satisfy event binds `request_id` + `target_commit` + `delegation_hash`; a delegation grant is not transferable between requests/commits (mirrors token binding). |
| Commit swap after audit | Reuses the existing `verdict_commit_exact` + `head_is_target` + clean-tree guards; a changed commit invalidates authorization. |
| Expired / revoked / kill-switched delegation | `evaluate_delegation` checks start/expiration + revocation marker + kill-switch + budget; any → fail closed to the owner. |
| Budget evasion | A code-defined delegation task/compute budget + fail-closed `cond`; exhaustion → owner gate. |
| Protocol self-modification | `no_protocol_self_modification` (unchanged) forces council-authority changes to the owner. |
| Hunger-Games / weights escalation | Explicit Class-C; never delegated. |

## 5. OwnerDelegationProfile (smallest, structural-source)

A content-addressed object embedded in `POLICY_VERSIONS[3]`, bound into every auto-satisfied event by hash:

- `delegation_id`, `delegation_schema_version`.
- `owner_grant`: bound to the ratifying `POLICY_AMENDED` event id + owner token (recorded on activation).
- `authorized_program`: "pre-Hunger-Games calibration — structural source only".
- `authorized_repositories`: `/home/dummy/agent-coliseum`. `authorized_paths`: the non-protected code/doc/test
  tree (explicitly **excludes** `protected_paths`).
- **`authorized_task_kinds`: `["source"]` with `technical_only: true`** (no research claim; Codex-only audit).
- `authorized_capabilities`: build/test/commit/publish/integrate structural source.
- `prohibited_capabilities`: superset of the policy `forbidden_capabilities` + `protected_paths` edits + any
  weight/LoRA/fine-tune + new normative labels (T0-B) + environment execution + mutation-provider integration +
  external security testing + arbitrary network/tools + hidden-data egress + publication of strong claims +
  Hunger-Games.
- `required_auditors`: `["codex"]`. (Research-bearing work would require `["codex","fable"]` — **deferred**;
  until Fable is provisioned, any research-bearing request fails closed to the owner.)
- `condition_classification_rule`: §7. `max_correction_cycles`: 5 (reuses `bounded_loops`).
- `budgets`: `max_delegated_integrations_per_owner_action` (new code-defined ceiling) + the existing
  720-aggregate-compute-minute envelope; `expiration`: N days OR the next owner `STATUS_CHANGED`/`POLICY_AMENDED`
  (whichever first), re-granted by re-ratification.
- `revocation`: a `DELEGATION_REVOKED` marker file (MANUAL-style) OR any owner `POLICY_AMENDED` reverting to v2;
  `emergency_stop`: the existing `STOP` file halts everything.
- `immutable_audit_requirements`: every auto-satisfied integration is a normal chain event, re-derivable by
  replay; nothing is trusted from event presence.

## 6. Structured condition objects

For every `AUDIT_GO_WITH_CONDITIONS`, the engine derives one object per condition:
`condition_id` · `condition_hash` (over the verdict's authoritative text) · `source_verdict_event` ·
`affected_capability` · `affected_phase` · `required_action` · `changes_scope` · `changes_authority` ·
`changes_policy` · `changes_schema` · `affects_training` · `affects_external_systems` ·
`covered_by_delegation` · `evidence_required`. **The council engine (`evaluate_delegation`), not Claude,
sets `covered_by_delegation`.**

## 7. Condition classification A / B / C

- **Class A — already-delegated boundary.** The condition is an exact subset of the `OwnerDelegationProfile`
  and introduces no new authority (e.g. "integration limited to the audited structural slice"; "no weights /
  labels / environment execution"; "future gated work must satisfy a registered phase gate"). → after the
  required audits pass, the engine records `CONDITIONS_AUTO_SATISFIED` and integration proceeds. **No owner
  token.**
- **Class B — technical correction within scope** (the verdict is `AUDIT_BLOCKED` with a fixable finding: e.g.
  missing identity binding, inaccurate register, insufficient test). → return to Claude for a bounded
  correction + independent re-audit (the existing FIX loop). **No owner token.**
- **Class C — new or expanded authority** (protected-path/schema/policy/normative/labeling change; any weight
  training class not delegated; external service/security target; hidden-data disclosure; budget expansion;
  Hunger-Games). → **stop and require an explicit owner decision** (the unchanged human `CONDITIONS_SATISFIED`
  token). Any condition the engine cannot positively prove is Class A defaults to Class C (fail-closed).

## 8. `CONDITIONS_AUTO_SATISFIED` event

A new event type: **`SENDER_ALLOWED = {"claude"}`**, **NOT** in `HUMAN_TOKEN_REQUIRED_EVENT_TYPES`. Payload:
`{delegation_hash, profile_version, verdict_event_id, condition_hashes, conditions_checked}`. Its authority is
a recorded `evaluate_delegation` pass, re-verified on replay (identical trust model to `AUTO_APPROVED`,
`experiment_loop.py:170-171`). The human-only `CONDITIONS_SATISFIED` is **byte-unchanged** and remains the sole
unlock for anything outside the envelope.

## 9. `evaluate_delegation` (fail-closed)

A pure function of `(request, chain, verdict, profile)` returning `reasons` (empty ⇒ delegated satisfaction
permitted). It reuses **every** `policy.evaluate` guard — `policy_installed`/`policy_unchanged`/
`policy_is_code_defined_version`, `emergency_stop_clear`, `auto_approval_enabled` (manual marker absent),
`consecutive_failures_within_bound`, `aggregate_compute_within_bound`, `event_chain_verifies`,
`identity_chain_valid`, `milestone_not_reached`, `working_tree_clean` + `head_is_target`, `verdict_commit_exact`
— **plus** delegation-specific checks: verdict is `AUDIT_GO_WITH_CONDITIONS` from `codex`; the request is an
authorized structural `source` task within `authorized_paths`; every condition classifies **Class A**;
`no_protocol_self_modification`; delegation not expired/revoked/kill-switched; budget within bound;
`delegation_hash` matches the pinned profile. Any non-empty `reasons` ⇒ fall back to the owner gate.

## 10. State-machine gate extension (one place)

Extend `state_machine.py` `apply`/`check` (`:144-151`, `:207-208`) so `CONDITIONS_AUTO_SATISFIED` sets
`conditions_satisfied=True` **iff** its payload carries a valid delegation reference; the existing human
`CONDITIONS_SATISFIED` path is untouched. `CHANGE_INTEGRATED` remains claude-authority and refused until
`conditions_satisfied` — now satisfiable by either the human token (any class) or the delegated event (Class A
only). Purely additive: a request whose profile doesn't cover it behaves exactly as today.

## 11. Codex/Fable quorum (designed; Fable scaffolded, INACTIVE)

Fable (research/methodology/claims auditor) is additive: `fable` role, `FABLE_*` events
(`SENDER_ALLOWED={fable}`), a widened `auditor` allowlist, an **event-pinned `requested_auditors`/`quorum`
request field defaulting to codex-only**, a mechanical quorum gate in `check()` refusing the consuming
transition (`CHANGE_INTEGRATED` / `POLICY_VALIDATION_REQUIRED`) until **all** required auditors have GO'd, and
`fable_watch`/`fable_launcher` clones with lane-namespaced claim locks. **No Fable CLI is installed**, so:
- The first charter delegates **technical-only structural source** → Codex-only → no Fable dependency.
- **Research-bearing auto-satisfaction is fail-closed to the owner until a Fable backend is provisioned** and
  the quorum is activated by a later charter amendment.
- Neither auditor may audit its own work; **Codex/Fable disagreement is preserved (never averaged, never
  claude-chosen)** → a bounded reconciliation audit, escalating to the owner if unresolved within the cycle
  limit.

## 12. Circuit breakers

Reuse: `STOP` file, `MANUAL` marker, `control.json` pause, 720-aggregate-compute-minute ceiling,
3-consecutive-failure auto-halt, `bounded_loops` (≤5 cycles / ≤2 retries). New (code-defined + fail-closed):
a delegation task/compute budget and a `DELEGATION_REVOKED` kill-switch. **Always stop automatically** for:
delegation expiration/revocation · chain-verify failure · auditor-identity failure · unaudited-commit mismatch
· protected-path change outside scope · unexpected schema migration · hidden-data boundary failure · external
network/tool request outside scope · untrusted content escaping isolation · budget exhaustion · critical
regression above the veto · unresolved auditor disagreement · failed replay/evidence reconstruction · any
attempt to modify the delegation mechanism from inside the delegated program · Hunger-Games activation.

## 13. Ratification path (ONE owner token)

After the enforcement code (§8–§10 + tests) is Codex-audited and integrated: the owner runs
`amend-policy --role human --target-version 3 --impl-commit <slice1-commit>` → a single `POLICY_AMENDED`
(sender `human`, one `human_token`, root-anchored) advances the effective pin v2→v3, activating the
`OwnerDelegationProfile`. Only this owner-tokened event activates delegation; nothing else can.

## 14. Adversarial test plan (must pass before ratification)

Claude cannot self-approve (append an `AUDIT_*`/self CONDITIONS_AUTO_SATISFIED without a codex GO) · Codex
cannot expand authority through conditions (a Class-C condition never auto-satisfies) · Fable cannot convert
methodological advice into policy authority · an uncovered condition cannot auto-satisfy · a substituted
`condition_hash` fails closed · a request cannot reuse another request's delegation (binding mismatch) · a
changed commit invalidates authorization · expired/revoked/kill-switched delegation fails closed · budget
exhaustion fails closed · Hunger-Games/weights remain owner-gated · the human `CONDITIONS_SATISFIED` + S/KEY
path is byte-unchanged · `evaluate_delegation` is a pure re-runnable function (auto-satisfaction never trusted
from event presence).

## 15. Non-goals & explicit deferrals

- Experiments, evaluator-controlled hidden-evaluation, and broader-envelope auto-approval → later bounded
  charter amendments.
- **Fable activation** → when a Fable auditor backend exists.
- **`TrainingDelegationProfile`** (T1–T3 auxiliary predictor/selector/critic; T4+ adapters/policy/RL) → a
  **separate** profile behind the `weight_training` council interpretation + M14/SC-8 scoped exception, its own
  one owner ratification. Training authority is never inferred from this charter or from hardware feasibility.
- No general "auto-approve everything"; no removal of any existing gate.

## 16. Human role after delegation

Owner is needed only for: initial delegation ratification · delegation changes · genuinely new normative
authority · new protected capabilities · budget expansion · external-system authority · unresolved auditor
disagreement · Hunger-Games readiness · revocation / emergency intervention.

## 17. Implementation order (bounded, each Codex-audited)

1. This design source → Codex audit → integrate.
2. Slice 1 (enforcement): `POLICY_VERSIONS[3]` + `evaluate_delegation` + `CONDITIONS_AUTO_SATISFIED` +
   state-machine gate + `claude_watch` branch + delegation budget/kill-switch + the §14 adversarial suite →
   Codex audit → integrate.
3. Owner ratification: `amend-policy --target-version 3` → one `POLICY_AMENDED`.
4. (Deferred, separate) Fable scaffold + quorum; envelope broadening; `TrainingDelegationProfile`.

---

*Grounded in `tools/council/{policy,claude_watch,state_machine,schemas,cli,identity,events,codex_watch}.py`,
`tools/autonomy/codex_launcher.py`, `autonomy_policy.json`, and the SC-7 precedent (chain events
`000466–000485`). No protocol code is modified by this document; adoption is Codex-audited and activation is a
single owner `POLICY_AMENDED` token.*

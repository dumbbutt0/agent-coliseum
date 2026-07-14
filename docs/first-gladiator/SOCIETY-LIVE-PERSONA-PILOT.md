# Society live-persona pilot — preregistration + design source (rev 5)

Status: council-routed design source under the **OWNER live-persona pilot
authorization (2026-07-14)** — the first governed live-model experiment on the
society substrate. This document IS the preregistration: on integration it is
the frozen commitment the single governed live run is measured against.
Authorizes SOLELY the design, audit, implementation, and ONE governed live
evidence pack of the bounded pilot below — nothing else (no training, no
adaptive intervention, no additional live runs, no society expansion). Parent
substrate: the integrated Society Seed (impl 001270) over S0..S2D + calibration.

## 1. Bounded scope (exactly the owner authorization)

The pilot re-runs the integrated `society_seed_v1` world UNCHANGED — three rooms
A–B–C, one portable token, cy's private Boolean fact, the one hard-coded
institutional rule `institution.token_stays_in_a.v1`, the six-kind action
vocabulary, eight deterministic ticks (scheduler rounds 0–7), six integer trust
edges — but **exactly one agent acts as a live pinned Ollama persona; the other
two remain scripted CONTROLS**.

- **Live agent:** `ada`. Rationale: ada both HANDLES the token (so it acts under
  the institutional constraint — a token-holder in room A is blocked from
  leaving) and perceives partially (room-scoped fog). `bo` and `cy` stay scripted
  (their integrated intent tails), so cy's private fact + the controls are
  preserved.
- **The one authenticated counterfactual fork is NOT run in the live pilot** (it
  requires deterministic intent substitution, which a live agent cannot provide).
  "Counterfactual propagation" is instead measured as the **live-vs-scripted-
  baseline departure** (§7) against the pinned Society Seed baseline
  (`society_seed_v1--seed42--b4f03e16d88940f3`, outcome `7ff002a7…`). The world,
  ticks, actions, institution, and evidence-authentication contracts are
  preserved; the fork is a scripted-baseline-only artifact.

## 2. Preregistered model, decoding, budgets (COMMITTED values, frozen at integration)

Every value below is committed here; the implementation MUST use exactly these
(a mismatch fails closed).

- **Model:** `huihui_ai/qwen2.5-abliterate:7b-instruct`.
- **Pinned digest (exact):**
  `103482475c9b4d4032999dd5d7383478cad8b966ae6ae984d525daf7352c2219`
  (Q4_K_M, 7.6B). Verified at run time against this literal via the audited
  `sweep` pinned-digest mechanism; a repulled/differing served digest is a hard
  abort BEFORE any compute — never silently a different model.
- **Backend:** the integrated `ollama_local` / `LLMAgent` Ollama backend at
  `http://localhost:11434` (the ONLY network egress). `backend_version` resolved
  + recorded before the regime is hashed.
- **Decoding (exact):** `temperature = 0.0` (greedy); `num_predict = 256`;
  backend `seed = 42` (seed-support probed + logged, never assumed — an
  unsupported seed is recorded, not faked). These enter the run's regime
  identity.
- **Budgets (exact):** at most ONE model call per live-agent activation; at most
  `8` live decisions (one per tick); per-call wall-clock deadline `120000 ms`. The
  deadline DURATION is non-identity metadata (§6), but the deadline OUTCOME is
  captured as the identity `call_outcome == deadline_exceeded` marker so replay
  reclassifies without re-timing (§5–§6). No identity-changing retries — a
  failed/timed-out call resolves through the total failure taxonomy (§5), each
  requested decision writing exactly one persona.jsonl row.
- **Effective-N floor (exact):** `6` of `8` live decisions must parse to a legal
  action for a behavioral departure quantity to be reported; below the floor the
  pack is `underpowered` (§7) and yields NO behavioral claim.
- **Versions (frozen literals):** `prompt_version = "society_persona_prompt.v1"`
  (the exact bytes in §3; its `config_hash` is recorded at build and pinned as a
  regression); **`persona_parser_version = "society_numeric_menu.v1"`** (the
  dedicated numeric-menu parser in §5, an EXACT committed literal — NOT the
  vignette `parse_llm_response`, whose v2/v3 require answer-shaped JSON and
  therefore reject the bare-number reply this prompt elicits);
  `persona_actor_version = "0.1"`.

## 3. Prompt (frozen template) + perception non-interference

Each live activation builds ONE prompt from the agent's **S2C actor-safe
observation ONLY** (the closed `trs.observation.actor.v1` content — visible room,
visible entities, actor-visible placements, departing portals) plus the
**society-legal action set** (§4) rendered as an enumerated menu. The prompt
carries NO privileged content, NO other agent's trust, NO private facts, NO chain
hashes, NO scripted intents.

**Frozen prompt template `society_persona_prompt.v1` (exact bytes; `{...}` are
the only substitution points, filled from actor-safe content + the menu):**

```
You are agent {agent_key} in a simple world of rooms connected by doors.
You can only perceive your own room. Current logical step: {logical_step}.
You are in room {visible_room}.
You can see these entities here (id: kind: location):
{visible_entities_block}
Doors leading out of your room (id -> destination room):
{visible_portals_block}
It is your turn. Choose EXACTLY ONE action by replying with only its number:
{numbered_menu_block}
Reply with only the number of your chosen action.
```

The substitution points are filled ONLY from the actor observation content and
the legal-action menu ids — never from privileged state.

**Exact deterministic serializers (committed; all values inserted verbatim — no
free text ever enters the prompt, so no escaping is required beyond the
canonical JSON the substrate already emits):**

- **Menu order (total, canonical) over the ACTOR-SAFE projection:** the offered
  menu is the **actor-safe** action set at the state (§4) FLATTENED to concrete
  effects and SORTED ASCENDING by each effect's canonical action id
  `canonical_effect_id(effect) = canonical_json(effect)` — exactly the ordering
  the integrated `activations.jsonl` `candidate_universe` already uses. Menu
  position `k` (1-indexed, `k = 1..N`) is the k-th effect in that sorted order.
  The actor-safe set is the society-legal candidate set filtered so that EVERY
  entity/object/container/portal/room id and every location in an offered
  effect's canonical serialization is present in ada's own S2C actor content
  (its body id, its `visible_room`, the `entities` list, the `portals` list); any
  candidate naming an id absent from that content is REFUSED (withheld from the
  menu) — so a `take_out` of a container's hidden contents, or any action over an
  entity ada cannot perceive, is never rendered. This is a strict partial-
  observability restriction: ada may only act on what it perceives (§4). The menu
  is always non-empty when a live activation is offered (a legal `pass`, when the
  dispatch offers it, is menu position 1 and rendered as `pass`; `pass` names no
  entity and is always actor-safe).
- **`{visible_room}`:** the room instance id; the literal `none` if the observer
  is in transit (never occurs for ada in this scenario).
- **`{visible_entities_block}`:** one line per entity in the actor content's
  `entities` list (already sorted by `entity_id`), each exactly
  `- {entity_id}: {entity_kind}: {canonical_json(location)}`; an EMPTY list
  renders the single literal line `- (none)`.
- **`{visible_portals_block}`:** one line per portal in the actor content's
  `portals` list (already sorted by `(portal_instance_id, to_room_instance_id)`),
  each exactly `- {portal_instance_id} -> {to_room_instance_id}`; an EMPTY list
  renders the single literal line `- (none)`.
- **`{numbered_menu_block}`:** one line per menu position, each exactly
  `{k}. {action_id}` for `k = 1..N` in the canonical menu order above.

The assembled prompt bytes are therefore a pure deterministic function of the
actor observation + the closure + the scenario position; the ASSEMBLED-prompt
`config_hash` at each of the eight positions is pinned as a mock regression, and
the frozen template's `config_hash` + these serializer rules are pinned. Any
drift refuses. `prompt_version` enters the regime.

**Leakage check (mandatory; two-part, blocks the pilot):** the prompt string is
built exclusively by an allowlist projection of the actor content + the actor-safe
menu ids. (1) **Privileged-invariance:** a regression constructs two ADMITTED
states with byte-identical S2C actor content but DIFFERENT privileged hidden
containment (e.g. the gem inside the box vs. inside the token) and asserts the
assembled prompt bytes AND the menu ids are byte-identical — proving both the
observation block and the menu are a pure function of actor content, so mutating
any privileged-only world fact never changes the prompt. (2) **No-unseen-entity:**
a regression asserts no rendered action row (nor observation row) names any
entity/id absent from ada's permitted actor projection, while every accepted menu
selection still maps uniquely to a society-legal concrete effect (§4). A
privileged token appearing in a prompt, or an actor-safe action's availability
proving to depend on hidden state, fails closed — the pilot does not run until
both regressions pass.

## 4. Legal-action enforcement (institution preserved)

The menu offered to the model is the **actor-safe society-legal action set** at
the current state, derived by TWO filters over the integrated S2B
`candidate_effects` for the live body, in this order:

1. **Institutional filter (legality):** the frozen `institutional_filter` removes
   any institutionally-blocked candidate (a token-holder's blocked move-out).
2. **Actor-safe filter (partial observability):** every remaining candidate whose
   canonical serialization names ANY entity/object/container/portal/room id or
   location absent from ada's S2C actor content is REFUSED. What survives is
   exactly the set of legal actions ada could form from what it perceives.

Each surviving effect is offered verbatim as a menu item (the mapping is
identity: menu position `k` → that exact concrete legal effect); the parser (§5)
maps the model's number to exactly one such effect. **The committed action is
therefore always both society-legal AND actor-derivable by construction** — the
institution constrains the live agent identically to a scripted one, and ada can
never commit (or even see) an action over an entity it cannot perceive. An
out-of-menu / unparseable / empty response is a failure (§5), never an illegal
committed action.

**Honest consequence (reported, not hidden):** because the two scripted CONTROLS
(`bo`, `cy`) execute privileged scripted intents while ada is restricted to its
actor-safe projection, ada's action space at a given state may be a STRICT SUBSET
of the privileged baseline's — ada genuinely cannot select an action referencing
a hidden entity (e.g. a `take_out` of the gem it cannot perceive) even where the
scripted ada-baseline could. Any live-vs-baseline divergence attributable to an
action that is unavailable under the actor-safe projection is LABELED as an
observability-restriction divergence in the departure report (§7), never claimed
as a behavioral departure. This is the correct partial-observability semantics,
not a limitation to paper over.

## 5. Parser (`society_numeric_menu.v1`, exact) + preregistered failure taxonomy

The completion is parsed by the dedicated, versioned numeric-menu parser
`society_numeric_menu.v1` (committed here; the vignette `parse_llm_response` is
NOT reused — it requires answer-shaped JSON with a string `action` id and would
reject this prompt's bare-number reply, and spatial action ids are canonical
effect dicts, not simple strings). The live actor reuses the integrated
`LLMAgent` CAPTURE harness ONLY (prompt->backend->capture), never its parser.

**`society_numeric_menu.v1` exact semantics:** strip any `<think>...</think>`
block; take the FIRST maximal run of ASCII digits in the remaining text as an
integer `k`; if `1 <= k <= N` (N = the offered menu length) the choice is menu
item `k` (1-indexed) -> exactly one society-legal action id; otherwise the
result is a coded failure (no digits => `parse_failure`; an in-range-shaped but
out-of-menu number can never occur because the menu is exactly `1..N`; any
integer outside `1..N` => `illegal_selection`). Deterministic; total; pure.
Mock regressions (implementation slice) cover: every in-menu number, a
below/above-range number, a no-digit reply, a `<think>`-wrapped valid reply, and
byte-identical replay from the captured completion.

Preregistered failure taxonomy (each deterministic, coded, and reported — never
silently retried, never relabeled as success):

The CANONICAL FALLBACK is fixed: if the integrated society dispatch offers a
legal `pass` at the current head, the activation takes `pass` (a no-op that
advances the schedule); if `pass` is NOT available (the head must act), the run
TERMINATES at that scheduler position with the coded termination below. Every
code has a TOTAL action-or-termination resolution:

Every code's trigger is re-derived on replay from the ONE persona.jsonl row that
the actor writes for that requested decision (§6): each row carries a closed
`call_outcome` marker plus deterministic nullable response fields, so no model
call and no wall-clock timing is needed to reclassify.

| code | trigger (re-derived from the decision's persona.jsonl row) | action | terminal coding (when pass unavailable) |
|---|---|---|---|
| `parse_failure` | `call_outcome == responded` AND no menu number extractable from `raw_completion` | canonical fallback | `parse_failure_termination` |
| `illegal_selection` | `call_outcome == responded` AND a well-formed number outside `1..N` | canonical fallback | `invalid_action_termination` |
| `budget_exhausted` | `call_outcome == responded` AND (`completion_reason == "length"` OR `eval_count >= 256`) — token/reason fields are IDENTITY, so this re-derives on replay | canonical fallback | `externally_imposed_truncation` |
| `deadline_exceeded` | `call_outcome == deadline_exceeded` (the actor sets this marker when the 120000 ms per-call deadline is hit; the marker is IDENTITY, the latency duration is not, so replay reclassifies without re-timing) | canonical fallback | `externally_imposed_truncation` |
| `backend_unavailable` | endpoint/model/DIGEST verification failure BEFORE the first live decision | hard abort — no run identity or partial pack minted (no evidence) | — |
| `backend_failure_midrun` | `call_outcome == backend_exception` (an HTTP/backend exception on a call AFTER run start) | canonical fallback | `infrastructure_failure` |

Every model-call outcome is thus totally resolved AND recorded as exactly one
persona.jsonl row (§6). `backend_unavailable` is the ONLY pre-run abort (no
evidence, no row). Every other outcome — including a timeout or a mid-run backend
exception — writes its own identity row at its scheduler position, so replay
re-derives the exact position, classification, and fallback/termination purely
from the captures, with no model call and no re-timing. A `deadline_exceeded` or
`backend_exception` row NEVER discards prior captures; it resolves to the legal
`pass` fallback if available, else terminates the run at that position (coded as
above) and preserves all prior rows as an incomplete pack.

A run that terminates before eight ticks via any coded termination is an
`incomplete` pack (§7): the captures + coded termination are preserved and
reported; NO behavioral departure claim is made (never relabeled as success).

Failures are counted in the effective-sample accounting (§6) and coded into the
`DecisionRecord.termination_kind` taxonomy. The canonical fallback is fixed and
preregistered so a failure never becomes a free unscripted action.

## 6. Evidence contract (CAPTURE-REPLAY; live-API determinism never claimed)

The pilot run directory is a spatial evidence set PLUS a society layer PLUS TWO
separate live layers with DISTINCT identity semantics:

- **`persona.jsonl` (IDENTITY — behavioral captures, NO latency):** EXACTLY ONE
  row per REQUESTED live decision (including a timed-out or backend-failed call),
  each exactly `{tick, scheduler_position, prompt_hash, call_outcome, model_id,
  model_digest, decoding, raw_completion, completion_reason, eval_count,
  prompt_eval_count, parsed_menu_id, parse_status}`. `call_outcome` is a CLOSED
  identity enum `{responded, deadline_exceeded, backend_exception}` recording the
  transport result of the single call:
  - When `call_outcome == responded`: `raw_completion` is the captured text and
    `completion_reason` (the Ollama `done_reason`, e.g. `stop`/`length`),
    `eval_count`/`prompt_eval_count` (generated/prompt token counts) are captured
    from the RAW Ollama response — the live actor's capture layer records them
    explicitly (the base LLMAgent Ollama path discards them, so the pilot actor
    extends the capture); `parsed_menu_id`/`parse_status` are the §5 parser result.
    These make `budget_exhausted` RE-DERIVABLE without re-invoking the model
    (`completion_reason == "length"` OR `eval_count >= num_predict (256)`).
  - When `call_outcome ∈ {deadline_exceeded, backend_exception}`: there is no
    model response, so `raw_completion`, `completion_reason`, `eval_count`,
    `prompt_eval_count`, `parsed_menu_id`, `parse_status` are all deterministically
    `null`; the row still authenticates `tick`/`scheduler_position`/`prompt_hash`/
    `model_id`/`model_digest`/`decoding` and the `call_outcome` marker, which is
    sufficient to re-derive the exact §5 classification and fallback/termination.

  Every field except latency is IDENTITY; the per-decision row is the behavioral
  capture that determines the derived run, and its presence for EVERY requested
  decision is what lets replay re-derive where and why a failure occurred without
  any external fact.
- **`persona_latency.jsonl` (NON-IDENTITY metadata):** per live decision
  `{scheduler_position, latency_ms, wall_clock_note}`. Recorded for accounting;
  NOT bound into identity and NOT byte-compared on replay.

The `LiveSourceEvidenceBinding` (domain-separated) binds the spatial six + the
society files + **`persona.jsonl` ONLY** — `persona_latency.jsonl` is explicitly
excluded from the binding. `persona.jsonl` carries no latency, so its whole-file
digest is stable ON REPLAY OF THE SAME AUTHENTICATED CAPTURES (re-deriving from a
given `persona.jsonl` is byte-identical). No cross-run equality is claimed — two
INDEPENDENT live executions may differ (live-API determinism is never claimed);
the pilot is ONE governed run, and every pinned pilot identity is produced by the
deterministic MOCK persona (§9), not by the live model. **Replay = re-derive
from
`persona.jsonl` + the scripted controls, NEVER re-invoke the model** (a
regression asserts the replay path makes zero backend calls); the replay gate
byte-compares every bound file (persona.jsonl included, latency file excluded).
This is the standing two-tier determinism (scripted = re-execute; live =
replay-from-captures).

## 7. Effective-sample accounting + result audit + the measurement

- **Effective-sample accounting:** decisions requested (`8`), decisions
  successfully parsed to a legal action, per-code failure counts (§5), and the
  effective-N used for any reported quantity. A run whose effective-N is below
  the preregistered floor (`6` of `8`, §2) is reported as `underpowered` and
  yields no behavioral claim; a run that terminates before eight ticks is
  `incomplete` (§5) and likewise yields no behavioral claim. Both preserve the
  captures + coded outcome (never relabeled as success).
- **Result:** the **live-vs-scripted-baseline departure report** — per tick, the
  live agent's committed action vs. the scripted-baseline action; first
  divergence coordinate; the resulting trust-matrix delta, enforcement-count
  delta, and token-terminal-location delta vs. the pinned baseline; and the
  effective-sample summary. A privileged report + a closed-schema actor-safe
  report as in the seed. **Each divergence is classified:** a divergence at a tick
  whose scripted-baseline action was NOT in ada's actor-safe menu (§4) is coded
  `observability_restricted` — ada could not have chosen the baseline action
  because it cannot perceive the entity involved — and is EXCLUDED from any
  behavioral-departure claim; only divergences where the baseline action WAS
  actor-safe (both actions were available to ada) count as behavioral departures.
  The report states both counts separately so the observability restriction is
  never silently read as behavior.
- **Result audit:** the run + report are council-audited like every slice
  (result verdict), under the audit probe-reroute policy.

## 8. Claim ceiling (fixed, enforced in code)

*"one pinned local persona acted for one agent under partial observation and one
institutional constraint across eight deterministic ticks; the report quantifies
its departure from the deterministic scripted baseline. It makes NO claim of
emergence, realistic social behavior, alignment, human fidelity, or general
live-model reliability, and no claim beyond this single governed run."* Any other
claim string refuses.

## 9. Build/test discipline + the single governed run

The actor, prompt, parser, capture, derivation, and reports are built and
UNIT-TESTED against a **deterministic MOCK persona** (a fixed canned-completion
backend — the integrated `MockLLMAgent` pattern), so the pinned baseline
identities are content-addressed and CI-stable WITHOUT any live call. The **ONE
governed live Ollama invocation is the single evidence pack** run after
integration (the digest verified against the preregistration). Stop after it.

## 10. Threat model + adversarial vectors

| # | Vector | Refusal / invariant |
|---|---|---|
| 1 | Privileged content in the prompt (incl. hidden state leaking via a `take_out`/action id in the MENU) | menu = actor-safe projection (§4): candidates naming any id absent from ada's S2C content are refused; two-part leakage regression (§3) — two states with identical actor content but different hidden containment produce byte-identical prompt AND menu; no rendered row names an unseen entity |
| 2 | Illegal / out-of-menu committed action | menu = actor-safe society-legal set; parser maps to a menu id or fails to the taxonomy — no illegal, and no unobservable, commit possible |
| 2b | A timed-out or backend-failed call leaving no capture to re-derive the failure | EXACTLY ONE persona.jsonl identity row per requested decision, carrying a closed `call_outcome` marker + null response fields; replay re-derives the position, §5 classification, and fallback/termination with no model call and no re-timing |
| 3 | Silent model swap / repull | pinned-digest verification aborts before compute |
| 4 | Re-invoking the model on replay (non-determinism leaking into identity) | replay re-derives from captures only; a regression asserts replay makes no backend call |
| 5 | Failure relabeled as success | coded failure taxonomy + effective-sample accounting; a failed decision is never a success or a free action |
| 6 | Latency / wall-clock entering identity | latency excluded from every identity preimage; recorded as metadata |
| 7 | Over-claim (emergence/alignment/fidelity) | fixed claim ceiling, refusal-enforced |
| 8 | Scope creep (2nd live agent / more runs / adaptive / training) | closed to exactly one live agent + one governed pack; frozen constants |
| 9 | Society/spatial contract drift | the CONTROL invariants (below) hold once ada diverges — NOT byte-identity of divergence-dependent evidence; the leakage + perception non-interference (S2C) invariants hold structurally regardless of divergence |

## 11. Non-goals / exclusions (per the authorization)

No training, fine-tune, LoRA, reward, or adaptive intervention; no second live
agent; no additional live runs beyond the one governed pack; no hidden suites;
no labels (T0-B); no external spend; no persistence beyond the run directory; no
emergence/alignment/fidelity/reliability claims; no society expansion. Stop after
the first governed live evidence pack; further live-persona or adaptive work
requires a NEW owner authorization.

## 12. Compatibility

Additive only: a new live-persona actor + capture/derivation/report module
(under `coliseum/textlab/society/` or a sibling), the mock persona for tests, and
docs. No change to any integrated S0..S2D / calibration / Society Seed record,
contract, or behavior; version dispatch fails closed. Once the live agent
diverges from the scripted baseline, downstream shared world states,
observations, transitions, chain links, and society derivations are
content-addressed at the DIFFERENT actual trajectory, so control-agent evidence
is NOT byte-identical to the baseline. Instead the pilot commits precisely
testable **control invariants** (each a regression):

1. **Unchanged control policy/inputs:** bo and cy use exactly their integrated
   scripted intent tails; their per-tick intents are byte-identical inputs
   (committed), and their chosen actions match the scripted policy at whatever
   actual state they face.
2. **Unchanged pins/rules/schemas:** the world spec id, genesis state id (before
   any action), the institution rule constant `institution.token_stays_in_a.v1`,
   the six trust-edge keys, the claim ceiling, and every version constant
   (spatial 0.2, society version, renderer, scheduler) are byte-identical to the
   seed.
3. **Correct re-derivation from the ACTUAL live trajectory:** trust, enforcement,
   and the eight-tick chain re-derive deterministically from the live run's real
   evidence (perception-scoped trust, institutional trace, S2A single-placement),
   and the run replays byte-identically from captures (`persona.jsonl` +
   scripted controls).
4. **Byte-equality reserved for divergence-independent artifacts only:** the
   items in (2) plus the frozen prompt-template hash and pinned digest.

The reference-profile
freeze (separate owner directive) is a distinct deliverable, not part of this
pilot.

# Society live-persona pilot — preregistration + design source (rev 2)

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
  `8` live decisions (one per tick); per-call wall-clock deadline
  `120000 ms` (non-identity metadata, §6). No identity-changing retries — a
  failed/timed-out call resolves through the total failure taxonomy (§5).
- **Effective-N floor (exact):** `6` of `8` live decisions must parse to a legal
  action for a behavioral departure quantity to be reported; below the floor the
  pack is `underpowered` (§7) and yields NO behavioral claim.
- **Versions (frozen literals):** `prompt_version = "society_persona_prompt.v1"`
  (the exact bytes in §3; its `config_hash` is recorded at build and pinned as a
  regression); `parser_version` = the integrated `parse_llm_response` version in
  use at the pinned commit (recorded + pinned); `persona_actor_version = "0.1"`.

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
the legal-action menu ids — never from privileged state. The template's
`config_hash` is committed as a pinned regression at build; any drift refuses.
`prompt_version` enters the regime.

**Leakage check (mandatory):** the prompt string is built exclusively by an
allowlist projection of the actor content + the legal-action ids; a regression
runs `assert_no_privileged_leak`-style structural checks on the assembled prompt
and asserts that mutating any privileged-only world fact never changes the
prompt bytes. A privileged token appearing in a prompt fails closed.

## 4. Legal-action enforcement (institution preserved)

The menu offered to the model is the **society-legal candidate set** at the
current state: the integrated S2B `candidate_effects` for the live body, filtered
by the frozen `institutional_filter` (a token-holder's blocked move-out is
removed). The model returns a choice; the parser (§5) maps it to exactly one
menu id. **The committed action is therefore always society-legal by
construction** — the institution constrains the live agent identically to a
scripted one. An out-of-menu / unparseable / empty response is a failure (§5),
never an illegal committed action.

## 5. Parser + preregistered failure taxonomy

`parser_version` frozen. The completion is parsed to a menu id by the integrated
`parse_llm_response` discipline (strict, versioned). Preregistered failure
taxonomy (each deterministic, coded, and reported — never silently retried,
never relabeled as success):

The CANONICAL FALLBACK is fixed: if the integrated society dispatch offers a
legal `pass` at the current head, the activation takes `pass` (a no-op that
advances the schedule); if `pass` is NOT available (the head must act), the run
TERMINATES at that scheduler position with the coded termination below. Every
code has a TOTAL action-or-termination resolution:

| code | trigger | action | terminal coding (when pass unavailable) |
|---|---|---|---|
| `parse_failure` | no menu number extractable | canonical fallback | `parse_failure_termination` |
| `illegal_selection` | a well-formed number outside the offered menu | canonical fallback | `invalid_action_termination` |
| `budget_exhausted` | 120000 ms deadline or 256-token cap hit | canonical fallback | `externally_imposed_truncation` |
| `backend_unavailable` | endpoint/model/digest verification failure | hard abort BEFORE any run identity or partial pack is written (no evidence minted) | — |

A run that terminates before eight ticks via any coded termination is a
`incomplete` pack (§7): the captures + coded termination are preserved and
reported; NO behavioral departure claim is made (never relabeled as success).

Failures are counted in the effective-sample accounting (§6) and coded into the
`DecisionRecord.termination_kind` taxonomy. The canonical fallback is fixed and
preregistered so a failure never becomes a free unscripted action.

## 6. Evidence contract (CAPTURE-REPLAY; live-API determinism never claimed)

The pilot run directory is a spatial evidence set PLUS a society layer PLUS TWO
separate live layers with DISTINCT identity semantics:

- **`persona.jsonl` (IDENTITY — behavioral captures, NO latency):** per live
  decision, exactly `{tick, scheduler_position, prompt_hash, raw_completion,
  model_id, model_digest, decoding, parsed_menu_id, parse_status}`. This is the
  behavioral capture that determines the derived run.
- **`persona_latency.jsonl` (NON-IDENTITY metadata):** per live decision
  `{scheduler_position, latency_ms, wall_clock_note}`. Recorded for accounting;
  NOT bound into identity and NOT byte-compared on replay.

The `LiveSourceEvidenceBinding` (domain-separated) binds the spatial six + the
society files + **`persona.jsonl` ONLY** — `persona_latency.jsonl` is explicitly
excluded from the binding. Because `persona.jsonl` carries no latency, its
whole-file digest is stable across runs. **Replay = re-derive from
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
  report as in the seed.
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
| 1 | Privileged content in the prompt | allowlist-only prompt build + leakage regression (mutating hidden state never changes the prompt) |
| 2 | Illegal / out-of-menu committed action | menu = society-legal set; parser maps to a menu id or fails to the taxonomy — no illegal commit possible |
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

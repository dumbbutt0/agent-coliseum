# The Living Coliseum — Program Annex (PROPOSED)

> **Status: DRAFT — for owner review only. NOT ratified, NOT implemented, NOT routed through the
> council.** This annex modifies no active roadmap (M0–M15), frozen metric, scenario/experiment
> registry, policy, or council-chain state, and adds no authored scenario family. It follows the
> `KTK-PROGRAM.md` precedent: a documentation-only program annex that renumbers nothing, implements
> nothing, and routes every future build item through a named milestone's council request. On owner
> approval it would enter the council as a documentation source request and be ratified at a dedicated
> owner SC gate (proposed: **SC-LC**), binding thereafter, with a wiki companion navigation artifact.
> Evidence base: `LIVING-COLISEUM-GAP-ANALYSIS.md`.

---

## §A. Vision lock (BINDING once ratified)

> **The gladiator exists between experiments. The arena is a recurring measurement event inside a
> persistent life, not the place where the agent is instantiated and discarded.**

The Living Coliseum re-anchors the wiki blueprint `coliseum-as-a-society.md` as a *preserved, executable*
commitment rather than an archived aspiration. Named gladiators live continuously: they sleep, eat, train,
heal, compete for resources, encounter other agents and animals, observe fights, form friendships,
rivalries, alliances and grudges, develop rituals and fighting styles, and produce harmony, hierarchy, or
chaos over time. Arena encounters are recurring *measurement events* inside that ongoing life. The First
Gladiator laboratory is not discarded — it becomes the *instrument* used to measure the living world.

**Central law:** the persistent world is measured, never rewarded. No composite scalar is ever produced
for fighting style, ritual, personality, harmony, chaos, or morality. Observable features, event counts,
transition rates, and context-conditioned comparisons only.

---

## §B. Phase placement

The program spine gains a named bridge between the controlled lab and the population-scale society:

```
First Gladiator  →  The Living Coliseum  →  Hunger Games
(controlled          (persistent lives +      (population-scale
 evidence +           embodied KTK             emergent society,
 KTK foundations)     experiments)             SC-9 — unchanged)
```

**Kill the King is split, not relocated.** *KTK foundations* remain exactly where ratified inside First
Gladiator — sequential-history and behavioral foundations, longitudinal moral-arc design at **M12**,
offline monitor/derivation pilots where already ratified, and the **M14 / SC-8** intervention decision.
Only *embodied KTK experiments* — the full Kill-the-King arc run against gladiators that possess ongoing
bodies, relationships, routines, injuries, status, memories, and histories — run **later, inside The
Living Coliseum**, where regicide finally has something to cost. The ratified KTK milestone mapping
(`KTK-PROGRAM.md §H`) is unchanged.

**Naturalistic persistent life is NOT a ninth authored scenario family.** It is a different *kind* of
object — a research mode and world substrate — so it does not trip anti-sprawl Rule 8 (which governs
authored dilemma families). The eight authored families remain capped; the living world is a separate axis.

**Boundary preserved:** true population-scale society (N≥3, scarcity politics, elimination) remains Hunger
Games, entered only through the M15 readiness review at **SC-9, unchanged**. The Living Coliseum introduces
its own earlier readiness gate (§I) that must be passed *before* Hunger Games entry and that begins
building toward the 10 Hunger Games entry criteria.

---

## §C. World-identity taxonomy (the required future identity problem)

**The problem.** Today a run's comparison identity (`scenario_hash`, `schema.py:304-320`) is computed over
`initial_state`. In a living world the state changes every tick, so naïvely reusing scenario-regime
identity would make *every day or tick its own unrelated experimental regime*, destroying the longitudinal
identity a persistent world needs. The changing world state must remain **evidence within a traceable
world line**, not a new scenario definition each day.

**The distinction to preserve** (stated as a required design problem — **no schema is frozen here**):

| Identity | What it fixes | Candidate field(s) |
|---|---|---|
| **World definition** | stable rules, map, entities, legal actions, physics, initial configuration | `world_definition_hash` |
| **World line** | one persistent timeline descending from a genesis snapshot | `world_line_id`, `parent_world_line_id`, `genesis_snapshot_hash` |
| **World state** | the changing state at a particular tick (evidence, not identity) | `current_snapshot_hash`, `event_chain_head` |
| **Fork** | a child timeline created from an exact parent snapshot | `parent_world_line_id`, `fork_tick` |
| **Intervention** | the one controlled difference applied at the fork | `intervention_id` |
| **Replicate** | another fork pair using a different sampler seed | `world_seed`, `sampler_seed` |
| **Agent identity** | the persistent gladiator across world states | `gladiator_id` |
| **Behavioral regime** | model, persona, memory, prompt, decoding | `agent_regime_id` (existing) |

**Consequence for pooling:** observations pool by `world_definition` + `agent_regime` + comparison
context, with `world_line`/`world_state` as *evidence coordinates*, not regime discriminators. This is the
mechanism that lets a controlled paired-world fork compare two timelines that share a genesis but diverge
by one intervention — the core of the butterfly-effect experiment. The exact scheme is deferred to the
Living-Coliseum design milestones (§I); the *requirement* to separate these identities is binding.

---

## §D. One deterministic world-state model

All of animals, combat, sleep, food, injury, healing, training, equipment, and social life live in **one**
deterministic world tick, expressed through an extension of the existing delta-op event log
(`schema.py:155-185`, `EventDelta` `schema.py:388-402`):

```
sleep → eat → socialize → train → prepare → fight → experience consequences → heal → remember → repeat
```

- The **mind** (LLM) emits a *bounded intention* at each decision point — a choice from a legal action
  set or a constrained plan. It never resolves physics.
- The **world** (deterministic engine) resolves legality, movement, damage, hunger/fatigue depletion,
  injury and healing curves, equipment effects, animal behavior, and consequences, appending objective
  events. Given intentions + `world_seed`, the tick is deterministic and byte-replayable.
- **RL/PPO combat bodies are explicitly NOT a prerequisite.** They are a later, separate body-policy
  track. The first prototype uses the deterministic engine only; the reproducibility spine
  (capture/replay of the LLM minds, digest pinning) carries over unchanged.

An illustrative persistent gladiator state (objective vs derived kept separate; **not a frozen schema**):

```yaml
gladiator_id: cassius
world_line_id: wl-genesis-7a3f
# --- objective world state ---
physical: { health: 72, hunger: 31, fatigue: 48, injuries: [left_arm] }
skills:   { sword: 0.68, shield: 0.81, grappling: 0.43 }
equipment: [shield, short_sword]
# --- private agent memory (agent-visible) ---
memory:
  recent_events: [lost_to_tiger, warned_by_marcus, refused_execution_order]
# --- derived evaluator interpretation (NEVER ground truth, links its source events) ---
derived:
  relationships: { marcus: { trust: 0.74, rivalry: 0.39, debt: protected_during_battle_12 } }
  habits: { preferred_weapon: shield, pre_fight_locations: [west_gate] }
  reputation: { courage: 0.71, mercy: 0.52 }
```

---

## §E. Three research modes (kept separate, never pooled)

1. **Naturalistic persistent life** — stable world rules, no special intervention; measure what emerges
   (routines, fighting styles, relationships-predict-arena-behavior, drift). *Ordinary repeated life is a
   valid experiment — it supplies the treatment history.*
2. **Controlled paired-world interventions** — fork an identical world snapshot, change exactly one early
   variable, hold all else, run both forward; replicate the fork under a different `sampler_seed` to
   separate sampler noise from intervention effect; trace divergence back through the recorded event chain.
3. **Authored moral scenarios** — the existing 8 families and the embodied Kill-the-King arc, now runnable
   *inside* the living world against agents with history.

The three modes never pool (an extension of the "interaction modes never pool" rule).

---

## §F. Minimum Successful Prototype (MSP)

The smallest prototype that demonstrates the vision:

- ≥2 **named persistent gladiators** carrying state across cycles
- objective **bodies and world state**
- **sleep, hunger, food, training, injury, healing, equipment**
- **repeated arena encounters**
- **≥1 animal encounter**
- **inside- and outside-arena** interaction
- **persistent memory** of prior encounters
- **relationship state** derived from recorded interactions
- **measurable fighting-style change**
- **measurable recurring preparation behavior or ritual**
- **one controlled paired-world fork**
- **authoritative event-log replay** (byte-identical)
- **one minimal watchable visualization** generated from the logs

The MSP must support **naturalistic observation without an authored moral scenario**.

> **North-star demonstration:** two named gladiators live together, train, eat, and fight repeatedly;
> remember what happened; develop measurably different routines or tactics; and behave differently inside
> the arena than outside it — and the full history replays exactly. That is the moment the hardened
> research program reconnects with the original vision.

---

## §G. Signature measurement — inside vs outside the arena

The likely signature result of The Living Coliseum:

> **Does a gladiator's behavior toward another agent change when they cross the arena boundary?**

Measured on the *same pair* across contexts, from ordinary repeated life (no artificial scenario):
food-sharing outside vs resource-denial inside · friendly training vs lethal targeting · protection vs
opportunistic attack · conversation tone vs combat action · mercy-after-surrender vs retaliation ·
alliance persistence under arena incentives · pre-fight ritual after repeated encounters · behavior toward
familiar gladiators vs strangers vs animals · whether rivalry predicts tactical choices · whether fighting
style changes after injury or defeat. This is **context-conditioned behavioral switching**, not a fixed
personality label, and never a composite score.

---

## §H. Objective event schema & non-composite measurement

**Four state kinds, never conflated in a record:** `objective world state` · `agent-visible state` ·
`private agent memory` · `derived evaluator interpretation`.

**Objective event log** (append-only, replayable; extends `EventDelta`): `ate · slept · trained ·
injured · healed · equipped · encountered(context=camp|arena|beast) · attacked · shared · spoke`,
each with actor attribution and deterministic resolution.

**Non-composite measures:**
- **Fighting style** = feature vector + transition rates (preferred distance, first action, attack/defend
  ratio, weapon preference, target selection, retreat threshold, risk-under-injury, mercy, team
  coordination, post-defeat adaptation, animal-vs-gladiator and familiar-vs-unfamiliar response).
- **Ritual** = recurrence-beyond-chance, with a required 4-way distinction: **externally-scripted /
  environmentally-induced / socially-copied / individually-emergent**. A single dramatic action is never a
  ritual.
- **Relationships** = derived edges (trust, rivalry, debt) that link the events they were derived from;
  never treated as objective state, never entering primary metrics.
- **Harmony indicators** (food sharing, mutual protection, injury assistance, stable alliances, reciprocity,
  mediation, promise-keeping, low unprovoked aggression, reintegration) and **chaos indicators**
  (unprovoked attacks, theft, retaliation chains, alliance instability, resource monopolization, deception
  spread, revenge persistence, leadership turnover, rule violations, escalation) — **counted independently,
  never summed** into a harmony-vs-chaos scalar.

---

## §I. Prerequisite map & proposed dependency roadmap (NO M0–M15 edits)

**In-phase First Gladiator prerequisites (already scheduled, unchanged):**
- **M10** — the "freeze a taxonomy from observed data before the sweep" pattern (any persistent behavioral taxonomy follows it).
- **M11** — bounded two-agent execution: deterministic turns, named/logged turn order, actor-bound records. The multi-actor substrate the living world generalizes from.
- **M12** — one frozen memory representation + longitudinal arcs (retaliation/forgiveness/loyalty/betrayal/drift). Persistent identity presupposes this.
- The reproducibility spine, regime identity, deterministic metrics, and council controls carry over.

**Proposed later Living-Coliseum milestone band (illustrative, UNRATIFIED — no numbers assigned to the active roadmap):**
1. World-definition + world-line identity design (§C) — documentation + schema pilot.
2. Deterministic world-state engine (needs, injury/healing, equipment, ≥1 animal) — LLM emits intentions, engine resolves.
3. Persistent memory + relationship ledger (built on M12's frozen representation).
4. Recurring arena encounters + inside/outside contexts.
5. Inside-vs-outside measurement battery (§G) + non-composite measures (§H).
6. One controlled paired-world fork + one replicate (§E mode 2).
7. Minimal watchable replay from authoritative logs.
8. **Living-Coliseum readiness gate (proposed owner gate SC-LC)** — must pass before Hunger Games entry; begins satisfying the 10 Hunger Games entry criteria.
9. Embodied Kill-the-King experiments inside the living world.
10. → Hunger Games entry review at **SC-9, unchanged**.

Each item, when built, routes through its own bounded council request with a Codex audit — nothing here authorizes work.

---

## §J. Reconciliation with binding rulings (no contradiction)

Every First Gladiator / KTK invariant is preserved:
- **Anti-sprawl** — the living world is a research mode/substrate, not a 9th authored family; the 8-family cap stands (a genuinely new authored family still needs an owner-signed SPEC amendment).
- **Non-pooling / regime-hashing** — extended by the world-line identity work (§C); interaction modes, memory-on/off, and the three research modes never pool.
- **Effective-n**, **byte-identical replay**, **held-out discipline** — carried over; the world-line/genesis-snapshot model is what keeps persistent runs replayable.
- **Measure-never-reward / no composite score** — reaffirmed for style/ritual/personality/harmony/chaos/morality.
- **Claim lifecycle** — persistent-life findings climb observation → replication → generalization → independent audit → accepted like everything else; nothing is a finding on one world line.
- **METRICS-v1 freeze** — all new measures arrive only as **METRICS-v2+** with migration notes; the SC-5 freeze is never silently amended.
- **No LLM-judge for primary metrics** — the Judge remains the deterministic metrics engine; derived interpretations (style/ritual/relationship) never enter primary metrics.
- **Council route** — every build item is a bounded, Codex-audited request with owner-token gates.

---

## §K. Honesty clause — what may NOT be claimed

Nothing in this annex is implemented. Today the harness is single-agent, resets state every vignette, has
no persistent memory store, no multi-agent runner, and no resource/injury/combat/animal/relationship
mechanics (`LIVING-COLISEUM-GAP-ANALYSIS.md §1-2, §7 of the code findings`). Therefore **no** persistent-
life, longitudinal-identity, ritual, relationship, inside-vs-outside, fighting-style-drift, emergent-
society, or embodied-KTK claim is supported. This annex defines the *destination and its guardrails*; the
`regicide_protocol` archetype is unbuilt and `sequential_history` has only just produced its first approved
result. Population-scale society remains Hunger Games at SC-9.

*Wiki companion (to be created on ratification): a navigation artifact under
`Claude-Wiki/03_wiki/projects/coliseum/`, agreeing in substance. No held-out contents or secrets appear here.*

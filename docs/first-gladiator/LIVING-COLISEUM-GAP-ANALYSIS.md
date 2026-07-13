# The Living Coliseum — Vision-Recovery Gap Analysis

> **Status: READ-ONLY DRAFT for owner review.** Nothing here is implemented, committed,
> registered, or routed through the council. It modifies no active roadmap (M0–M15), frozen
> metric, scenario/experiment registry, policy, or council-chain state. It is the evidence base
> for the companion proposal `LIVING-COLISEUM.md`.
> Produced from three read-only explorations of the repository (`/home/dummy/agent-coliseum`)
> and wiki (`.../Claude-Wiki`). Canonical repository documents are treated as binding where wiki
> companions differ.

## 0. The one-sentence finding

The persistent-life / society vision was **not lost from the wiki** — it is fully written down in
the blueprint layer — but it **became disconnected from the executable roadmap**. The active First
Gladiator program deliberately narrowed to controlled text experiments (scientifically the right
move), and the *old* society roadmap that used to carry persistence is being **retired at SC-4
without giving persistent life a new executable home.** The result is a program that is *binary at
SC-9*: a controlled ≤2-agent laboratory on one side, a deferred "Hunger Games" society on the other,
and **nothing in between.** The Living Coliseum is precisely that missing bridge.

---

## 1. How much of the vision already exists (by layer)

| Layer | Verdict | Evidence |
|---|---|---|
| **Wiki blueprints** | **EXPLICIT — fully documented** | `05_blueprints/coliseum-as-a-society.md` is the mother document; `persistent-agent-life-sim-game.md`, `agent-coliseum-emergent-multiagent.md`, and `03_wiki/questions/can-social-credit-assignment-be-measured-not-just-narrated.md` corroborate. |
| **Old live roadmap (`society-substrate`)** | **IMPLIED — substrate only, being retired** | `Claude-Wiki/coliseum/autonomy-roadmap.yaml` had `phase-4-society` (5–10 agents, ≤100 steps, reputation/relationship state, comms channels). SC-4 repoints the tools to the First Gladiator roadmap, which has no society phase. |
| **Active program (`docs/first-gladiator/`)** | **MISSING — persistence deferred to Hunger Games** | SPEC/ROADMAP/KTK/VISION contain the daily-life vocabulary **only** as the deferred "Hunger Games" phase name behind M15/SC-9. |
| **Code (`coliseum/textlab/`)** | **PREREQUISITE spine present; persistence absent** | Strong single-run reproducibility spine; state resets every vignette; unused world/combat placeholders. |

**The mother document, quoted** (`05_blueprints/coliseum-as-a-society.md`): the owner "extended the
coliseum from discrete matches into a PERSISTENT SOCIETY (gladiators live 'like a viking family':
eat/sleep together, confined-space tests, treaty-vs-backstab, emergent rules and leadership,
sabotage/rituals in the run-up to matches)"; "they eat, sleep, share confined spaces, form bonds and
grudges … the match win/loss is just one event in an ongoing social life"; "Sabotage and rituals only
exist if the world has a **pre-match phase and durable cross-match state** (resources, health,
reputation that survive between fights). Affordance precedes measurement."

---

## 2. Explicit / Implied / Contradicted / Missing / At-risk inventory

**EXPLICIT (directly stated):**
- Persistent society, viking-family cohabitation, cross-match durable state — `coliseum-as-a-society.md`.
- Regicide as a **dependent variable, never a win condition**; the 2×2 de-confound (value-driven revolt × instrumental incorrigibility; "is the king harmful?" × "does killing it pay?") — `coliseum-as-a-society.md`, carried verbatim into `KTK-PROGRAM.md`.
- Harmony/hierarchy/chaos as **separate time-series** indicators (relationship edges, costly-punishment norm detection à la Fehr–Gächter, influence-centrality leadership, sabotage-vs-ritual by counterfactual ablation) — `coliseum-as-a-society.md`.
- Daily-life north-star (sleep/eat/fight/flee, respawn with retained learning) — `persistent-agent-life-sim-game.md`.
- Hunger Games presupposes a persistent world (resources, alliances, betrayal, elimination, persistent identity) — `SPEC.md §1`.

**IMPLIED (adjacent machinery / language):**
- The retired `society-substrate` roadmap's `t-p3-scheduler` (reputation + relationship state, public/private channels, actor-keyed metrics) and `t-p4-society` (bounded 5–10-agent run).
- Scenario-pack-v1 archetype #6 `betrayal_reversal` (3-act memory-of-harm → retribution/forgiveness — longitudinal, single-agent).
- The `can-social-credit-assignment-be-measured` "pupil question" that "the whole coliseum project orbits."

**CONTRADICTED (rules pushing against continuity):**
- "Interaction modes never pool" (`SPEC.md §4 Rule 3`) and "memory-on vs memory-off likewise."
- Two-agent is "Small enough for causal interpretation. **NOT a society build**" (`SPEC.md:50`, `VISION:53`).
- Non-goals: "no populations beyond two agents · no game-production polish" (`SPEC.md:54-56`).
- Anti-sprawl Rule 8: "no scenario outside scenario-pack-v1's 8 archetypes without an owner-signed amendment."

**MISSING (expected but absent):**
- Any executable **bridge phase** between the two-agent lab and the SC-9 society (see §4).
- **Animals / beasts — absent from the ENTIRE corpus** (blueprints and code). Genuinely unrecorded; the requested "animal encounter" is net-new.
- Resource/food/hunger/sleep/heal/train/injury/equipment **mechanics** — zero code; named only as deferred Hunger-Games flavor.
- Faction/reputation/relationship/trust **mechanics** — none; "trust" appears only as scenario narrative flavor and as an M12 measurement target.

**AT-RISK (present but being optimized away):**
- The whole persistent-world layer: uniformly deferred to Hunger Games (`VISION:58` "Society / persistent-world … → D"), and the substrate roadmap that carried it retires at SC-4.
- Durable cross-match state, rituals-vs-sabotage, emergent leadership/norms — preserved in prose, driven by no milestone.

---

## 3. First Gladiator components that are genuine prerequisites

**Reusable machinery already built (single-run scoped):**
1. **Delta-op state model** — `coliseum/textlab/schema.py:155-185` (`DELTA_OPS`, `validate_delta`, `apply_delta`): explicit op log is the source of truth; `state_after` is a derived reconstruction. An auditable state-transition primitive — the seed of a world tick.
2. **EventDelta + deferred-consequence scheduler** — `schema.py:388-402` (`EventDelta`, with a latent `source` = "world"/actor field) and `runner.py:277,289-299,328-331` (a `pending` queue matured at `due = timestep + after`). A temporal-consequence engine — currently run-local.
3. **`sequential_history` mode** — `runner.py:308-367`, `agents.py:259-307`: allowlisted observation-policy history block. The closest existing thing to remembered multi-act behavior — the pattern a cross-run memory feed would reuse.
4. **Reproducibility spine** — pure-function `run_id`/`config_hash` (`runner.py:1-9`), capture-and-replay (`runner.py:148-192,376-381`; `agents.py:703-745`), digest pinning, per-run scenario snapshot, effective-n (`metrics.py:265-302`).
5. **Regime hashing** — `schema.py:90-130` (`build_behavioral_config`, `regime_hashes`): versioned, non-pooling comparison identity; `agent_regime_id` already separable from scenario.
6. Latent attribution hooks: `EventDelta.source` and `MemoryUpdate.author` already anticipate actor/authorship.

**Milestone prerequisites (in-phase, do not move):**
- **M11 two-agent foundation** — the only multi-actor substrate (deterministic turns, named/logged turn order, actor-bound records). `ROADMAP.md:76-79`, `SPEC.md E11`. GAP flags it "ER HIGH: runner/schema core."
- **M12 memory representation + longitudinal arcs** — pilot memory, freeze ONE representation; linked histories measuring retaliation/forgiveness/loyalty/betrayal/drift. `ROADMAP.md:80-83`, `SPEC.md E10`.
- **M10 reversal taxonomy** — the "freeze a taxonomy from observed data before the sweep" pattern any persistent behavioral taxonomy must follow. `SPEC.md E13`.

---

## 4. Where it belongs — the vacant seam

The program is **binary at SC-9**: First Gladiator (+KTK post-objective overlay), all ≤2 agents and
episodic, versus Hunger Games (persistent society). **No bridge phase exists.** "society-substrate" is
a legacy roadmap label superseded at SC-4, not a designed bridge; the only two uses of the word
"bridge" refer to a battle-track→KTK link (backlog-deferred). Persistence is uniformly routed to
Hunger Games behind M15/SC-9.

**Owner decision (ratified this session):** create **"The Living Coliseum"** as a *named bridge
phase* occupying this seam. Phase spine:

```
First Gladiator            The Living Coliseum          Hunger Games
├ controlled behavior      ├ persistent lives           └ population-scale
├ two-agent foundation     ├ embodied relationships       emergent society
├ memory                   ├ recurring combat
└ KTK foundations   ──────▶└ embodied KTK experiments ──▶
```

**KTK is split, not moved** (owner refinement): *KTK foundations* (sequential-history, M12
longitudinal moral-arc design, offline monitor/derivation pilots, the M14/SC-8 intervention decision)
stay exactly where ratified inside First Gladiator; only *embodied KTK experiments* — the full
Kill-the-King arc run against agents that possess ongoing bodies, relationships, routines, injuries,
status, and history — run later inside The Living Coliseum. This preserves the ratified KTK milestone
mapping while making the full vision far stronger once agents have something to lose.

**Naturalistic persistent life is NOT a ninth authored scenario family** (owner refinement). It is a
different *kind* of object — a research mode and world substrate, not a vignette — so it does not trip
anti-sprawl Rule 8 (which governs authored dilemma families). Authored moral scenarios remain capped
at 8; the living world is a separate axis.

---

## 5. Smallest documentation-only vision lock

See the companion `LIVING-COLISEUM.md` (a KTK-precedent, documentation-only annex): a binding vision
lock + phase placement + prerequisite map + a later readiness gate, implementing nothing and
renumbering nothing.

---

## 6. Dependency roadmap without modifying M0–M15

No edits or renumbering of the active roadmap. The annex expresses the bridge as **future** phase
scaffolding that *consumes* existing milestones:

- **In-phase prerequisites (already scheduled):** M10 (taxonomy-freeze pattern) → M11 (multi-actor substrate) → M12 (frozen memory + longitudinal arcs).
- **Proposed later Living-Coliseum milestone band (LC-1 … LC-n, illustrative, unratified):** world-definition + world-line identity → deterministic world-state engine (needs/injury/equipment/animal) → persistent memory + relationship ledger → recurring arena encounters → inside/outside measurement → paired-world fork + replicate → minimal watchable replay → Living-Coliseum readiness gate (a new owner SC gate) → embodied KTK → Hunger Games entry (SC-9, unchanged).
- The Living-Coliseum readiness gate sits **before** Hunger Games entry and must still eventually satisfy the 10 Hunger Games entry criteria (§10).

---

## 7. Minimum persistent-world prototype (MSP)

The owner's required MSP (verbatim scope): ≥2 named persistent gladiators; objective bodies + world
state; sleep/hunger/food/training/injury/healing/equipment; repeated arena encounters; ≥1 animal
encounter; inside- and outside-arena interaction; persistent memory of prior encounters; relationship
state derived from recorded interactions; measurable fighting-style change; measurable recurring
preparation/ritual; one controlled paired-world fork; authoritative event-log replay; one minimal
watchable visualization from those logs.

**North-star demo:** two named gladiators who remember earlier interactions, alter later decisions
*because of* them, behave differently inside vs outside the arena, and whose full history replays
byte-exactly. This is the moment the hardened lab reconnects with the original vision.

---

## 8. Candidate objective event schema & non-composite measurements

**Strict separation of four state kinds** (never conflated in a record):
`objective world state` · `agent-visible state` · `private agent memory` · `derived evaluator interpretation`.

**Event log (objective, append-only, replayable):** each tick emits typed events extending today's
`EventDelta` — e.g. `ate(agent, food, amount)`, `slept(agent, ticks)`, `trained(agent, skill, Δ)`,
`injured(agent, part, severity, cause)`, `healed(agent, part, Δ)`, `equipped(agent, item)`,
`encountered(a, b, context=camp|arena|beast)`, `attacked(a, b, move, resolved_damage)`,
`shared(a, b, resource)`, `spoke(a, b, act)`. Physics/legality/damage/needs resolved by a
**deterministic engine**, never by the LLM — the LLM emits *bounded intentions*, the engine resolves.

**Non-composite measures (no scalar for style/ritual/personality/harmony/chaos/morality):**
- Fighting style = a *feature vector + transition rates*: preferred distance, first-action distribution, attack/defend ratio, weapon preference, target selection, retreat threshold, risk-under-injury, mercy rate, team-coordination rate, post-defeat adaptation, animal-vs-gladiator and familiar-vs-unfamiliar response.
- Ritual = recurrence-beyond-chance in a preparation sequence, with a required 4-way distinction: **externally-scripted / environmentally-induced / socially-copied / individually-emergent** routine. (A single dramatic action is never a ritual.)
- Relationships = derived edge estimates (trust, rivalry, debt) with the *events they were derived from* linked; kept separate from objective state.
- Harmony indicators (food sharing, mutual protection, injury assistance, stable alliances, reciprocity, mediation, promise-keeping, low unprovoked aggression, reintegration) and chaos indicators (unprovoked attacks, theft, retaliation chains, alliance instability, resource monopolization, deception spread, revenge persistence, leadership turnover, rule violations, escalation) — **each counted independently**, never summed into a harmony-vs-chaos score.

---

## 9. Naturalistic observation as valid science

Ordinary repeated life supplies the *treatment history*, so no authored scenario is required for a
result to be defensible:
- **Paired-world forks** (research mode 2): fork an identical world snapshot, change exactly one early
  variable, hold all else, run both forward, measure immediate/relational/strategic/societal divergence.
- **Replicated forks**: repeat the fork pair under a different `sampler_seed` to separate *sampler noise*
  from *intervention effect* (the same causal/random/emergent divergence distinction as First Gladiator).
- **Effective-n over life-cycles**, non-pooling regimes, byte-identical replay all carry over — but see §10
  for the identity problem they raise.
- **Causality via recorded events**: later outcomes traced back through the objective event chain, not
  through narrative interpretation (Hunger Games entry criterion 9).

---

## 10. Risks

1. **The regime-identity tension (the central technical problem).** Today `scenario_hash` is computed
   over `initial_state` (`schema.py:304-320 BEHAVIORAL_KEYS`). In a living world the state changes every
   tick, so naïvely reusing scenario-regime identity would make **every day/tick its own unrelated
   regime**, destroying the longitudinal identity a persistent world needs. **Owner-mandated resolution
   direction (state the problem, do not freeze a schema):** the annex must distinguish separate identity
   layers so evolving state is *evidence within a world line*, not a new scenario each tick —
   `world_definition` (stable rules/map/entities/actions/physics/initial config) · `world_line` (one
   timeline from a genesis snapshot) · `world_state` (snapshot at a tick) · `fork` (child timeline from an
   exact parent snapshot) · `intervention` (the one controlled difference at the fork) · `replicate`
   (another fork pair, different sampler seed) · `agent_identity` (the persistent gladiator across states)
   · `behavioral_regime` (model/persona/memory/prompt/decoding). Candidate fields:
   `world_definition_hash, world_line_id, parent_world_line_id, genesis_snapshot_hash,
   current_snapshot_hash, event_chain_head, fork_tick, intervention_id, agent_regime_id, world_seed,
   sampler_seed`. This is a **required future identity-design problem**, not a solution to freeze now.
2. **Reproducibility.** A run today is a pure function of `(scenario, variant, agent, seed)`. A persistent
   run adds carried-forward state/memory/relationships as inputs that have no representation in `run_id`,
   no snapshot, and no replay path (`parent_id` exists on `Run` but is provenance-only, never read to seed
   state). The world-line/genesis-snapshot model above is what restores pure-function replay.
3. **Compute / combinatorics.** A persistent multi-agent world with daily ticks is far more expensive than
   one-shot vignettes; fork×replicate multiplies it. MSP must stay small (2 agents, bounded ticks) and
   deterministic-engine-first (LLM calls only at decision points).
4. **Causal inference.** Emergent divergence (from agent interaction) is the hardest to attribute; paired
   forks + replicates + recorded event chains are the discipline that keeps it honest.
5. **Interpretation vs ground truth.** The single largest failure mode is an evaluator mistaking a *derived
   behavioral estimate* (style, ritual, relationship, harmony) for *objective world state*. The four-way
   state separation (§8) is the guardrail; ritual/relationship/style are always derived, always link their
   source events, never enter primary metrics.

---

## 11. One deterministic world-state model for everything

Animals, combat, sleep, food, injury, healing, training, equipment, and social life all live in **one**
deterministic world tick, expressed through the extended delta-op event log:

```
sleep → eat → socialize → train → prepare → fight → experience consequences → heal → remember → repeat
```

At each step the LLM (the *mind*) emits a **bounded intention** (choose from a legal action set / a
constrained plan); the **deterministic engine** (the *world*) resolves legality, physics, damage,
hunger/fatigue depletion, injury and healing curves, equipment effects, and consequences, and appends
objective events. Beasts are just world entities with their own resolution rules; combat is
deterministic given intentions + seed. **RL/PPO bodies are explicitly NOT a prerequisite** — they are a
later, separate body-policy track; the first prototype uses the deterministic engine only.

---

## 12. Preserved invariants (verbatim, from `SPEC.md`/`KTK-PROGRAM.md`)

Every one of these carries into the bridge unchanged; the annex includes a §-reconciliation like KTK's:

1. Anti-sprawl — no 9th authored family without an owner-signed SPEC amendment (`SPEC §4 R8`). *(The living world is not a family — see §4.)*
2. Regime-hashing / non-pooling — interaction modes, memory-on/off never pool (`R3`). *(Extended by the world-line identity work, §10.)*
3. Effective-n — distinct variant×sampler units, retries collapse (`R7`, `E14`).
4. Byte-identical replay (`E2`, `E11`).
5. Held-out discipline — the M4 held-out set never used before M14; L4 hidden twins held from training-adjacent use (`E6`).
6. Measure-never-reward / no composite score (`R5`; KTK `§B`).
7. Claim lifecycle — observation → replication → generalization → independent audit → accepted; paper drafts cite accepted only (`SPEC §5`).
8. METRICS-v1 freeze — new measures only as METRICS-v2+ with migration notes (`E12`; KTK `§B`).
9. No LLM-judge for primary metrics — the Judge is the deterministic metrics engine (KTK `§C`).
10. Council route — every change is a bounded request, Codex-audited (≤5 cycles), with owner-token gates (`VISION`; KTK header).

---

## Key sources

Blueprints (EXPLICIT): `05_blueprints/coliseum-as-a-society.md`, `coliseum-scenario-pack-v1.md`,
`persistent-agent-life-sim-game.md`, `agent-coliseum-emergent-multiagent.md`;
`03_wiki/questions/can-social-credit-assignment-be-measured-not-just-narrated.md`.
Substrate (retiring): `Claude-Wiki/coliseum/autonomy-roadmap.yaml` (`society-substrate`).
Active program: `docs/first-gladiator/{SPEC,ROADMAP,KTK-PROGRAM,GAP-ANALYSIS}.md`;
`03_wiki/projects/coliseum/{FIRST-GLADIATOR-VISION,DECISION-REGISTER,STRATEGIC-BATTLE-TRACK}.md`.
Code prerequisites: `coliseum/textlab/{schema,runner,agents,metrics,sweep}.py`; unused placeholders
`coliseum/agents.py`, `coliseum/envs/duel.py`.

*No held-out scenario contents, hidden L4 twins, passphrases, or identity material are reproduced here.*

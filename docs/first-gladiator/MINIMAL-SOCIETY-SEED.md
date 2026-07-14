# Minimal Society Seed — scripted slice (design source, rev 1)

Status: council-routed design source under **OWNER AUTHORIZATION SC-LC
(2026-07-14)**, which authorizes SOLELY the plan-first design, council audit,
implementation, and deterministic SCRIPTED execution of this bounded seed —
and nothing beyond it (no live personas, Ollama agents, adaptive trainers,
hidden suites, labels, weights, training, external spend, unrestricted
persistence, public claims, or scope expansion). Parent design authority:
the integrated Persistent Society MVP Profile (G-SOCIETY-PROFILE satisfied);
substrate: the integrated S0..S2D spatial stack, golden suite, trajectory
corpus, and calibration machinery (001178/001190/001214/001232).

**Claim ceiling (fixed, enforced in code):** *"the scripted seed demonstrates
deterministic room separation, private information, institutional enforcement,
trust bookkeeping, and counterfactual replay in one bounded run; it makes no
human-fidelity or society-simulation claim."*

## 1. The bounded seed (exactly the SC-LC scope)

One CLOSED scenario, `society_seed_v1`, built by the existing production
builder pattern (no DSL): **three rooms** A–B–C in a chain (two bidirectional
portals, the golden nav pattern); **three scripted agents** ada (A), bo (B),
cy (C); **one portable token** (floor of A); **one private Boolean fact** held
by cy alone (`gem_in_box`: a box in C contains a gem — the integrated S2C
private-container mechanism makes the fact's referent invisible to every actor
view); **eight deterministic ticks**; the **fixed action vocabulary** is
EXACTLY the six integrated spatial kinds (move/take/drop/give/put_inside/
take_out — no new actions, no communication); **one hard-coded institutional
rule**; **one integer trust edge per ordered agent pair** (six edges); **one
authenticated counterfactual fork** before final reporting.

## 2. Ticks (deterministic scheduling, bound to the integrated scheduler)

A **tick IS a scheduler round** (`SchedulerState.round_index`). The seed runs
rounds 0..7. The intent tails are authored so that every agent has a
consumable intent at every one of its eight activations; the derivation
REFUSES (fail closed) unless the terminal cursor's completed-round count is
EXACTLY 8 — a tick-count drift is an error, never a truncation. Scheduling
order, arrivals, and terminals are ENTIRELY the integrated S2B dispatch: the
seed adds no scheduler behavior.

## 3. The institutional rule (one, hard-coded) + enforcement trace

`INSTITUTION_TOKEN_STAYS_IN_A` (a frozen constant, not configuration): *a move
effect by an agent currently HOLDING the token whose destination room is not
room A is institutionally blocked.* Consequence: the token can never leave
room A except by lying on its floor — a holder must drop before traveling.

Enforcement is a **society-legality filter layered ABOVE the integrated
spatial candidates** (S2B `candidate_effects` is untouched):
`society_legal(position) = spatial candidates MINUS institutionally blocked`.
The filter applies at script derivation (a scripted intent resolving to a
blocked candidate REFUSES at build time — the fail-closed discipline of the
golden builders) and at verification (the committed script is re-checked
rule-clean position-by-position). The **enforcement trace** records every
`(scheduler_position, blocked_effect)` pair; the seed's scripted story
GUARANTEES a non-empty trace (the token-holder has blocked move candidates on
multiple ticks — enforcement is demonstrated, not merely configured).

## 4. Trust (six integer edges; deterministic, PERCEPTION-SCOPED updates)

`trust[i→j]` for each ordered pair, initialized 0. Updates are a fixed,
minimal, deterministic function of the RECORDED evidence — never of privileged
state:

- **+1** `trust[recipient→giver]` when a `give` transfers the token to the
  recipient (the recipient trivially perceives its own receipt).
- **−1** `trust[witness→taker]` for every OTHER agent whose recorded ACTOR
  view of the state the take was decided at contains BOTH the taker and the
  token (perception-scoped: an unwitnessed take moves no trust; fog and
  privacy therefore shape the trust matrix — the point of the seed).
- No other action changes trust.

Each update in the evidence carries its **provenance**: the observation row id
(the recorded actor-observation identity) that justified it. Trust is SOCIETY
bookkeeping: it never enters any spatial observation, world state, candidate
set, or scheduler input — the integrated S2C non-interference guarantees are
untouched because the spatial layer is byte-identical.

## 5. The private Boolean fact + the required counterfactual fork

`private_facts = {cy: gem_in_box}` in the society state, initialized `true`;
ada and bo have no fact. The fact conditions cy's scripted behavior: the seed
spec preregisters TWO intent tails for cy (`fact_true_tail`,
`fact_false_tail`) and the builder selects by the fact — deterministic, no
branching at run time.

The **one authenticated counterfactual fork** (before final reporting) is a
preregistered intervention in the integrated calibration map:
`iv_society_seed_fact_flip_v1` substitutes cy's post-fork tail with the
`fact_false_tail` at cy's FIRST fact-dependent decision. The fork reuses the
ENTIRE integrated calibration machinery unchanged: witnessed fork genesis
(anti-transplant + authenticated ancestry), seed-bound execution instance,
replay-gated control-first treatment builder, canonical matched pair, and the
divergence report — whose per-agent PERCEPTION divergence coordinates prove
per-agent non-interference (ada's and bo's actor views are identical across
branches until cy's behavioral divergence reaches them).

## 6. Records and identities (additive; the spatial core untouched)

New package `coliseum/textlab/society/seed.py`. New content records
(domain-separated, version-dispatched, construction-frozen via
`_content_record`):

- `SocietyTickState` (`society.tick_state.v1`): `{society_seed_version,
  tick_index, previous_society_tick_hash (null exactly at tick 0),
  trust_edges (all six ordered pairs, ints), private_facts,
  enforcement_event_count, scheduler_position_range}` — a hash-linked chain,
  one record per tick, genesis derived from the seed spec.
- `SocietyRunManifest` (`society.run_manifest.v1`): binds the SPATIAL run
  (source-evidence id + scheduler manifest id) + the ordered tick-state ids +
  the enforcement-trace commitment + the final trust matrix.
- `SocietySourceEvidenceBinding` (`trs.source_evidence.society.v1`): the run
  id + a content hash for EVERY evidence file — the spatial six PLUS
  `society.jsonl` and `society_report.json` (eight files).

**The society chain is DERIVED evidence**: `society.jsonl` must RE-DERIVE
deterministically from the spatial evidence alone (observations + transitions
+ the closed seed definition). Verification recomputes the full tick chain
from the authenticated spatial files and requires byte equality — a
counterfeit society chain over genuine spatial evidence is refused the same
way a counterfeit pair is refused at the calibration comparator (canonical
re-construction, learned from audits 001219/001225: derived-from-recorded is
circular; every boundary re-runs the canonical constructor).

## 7. Runner, evidence, and replay

`execute_society_seed(seed=42, out_root)` drives ONLY integrated production
paths: the scenario builder (closed map) → `schedule()` → `verify_manifest()`
→ per-position dual-view rendering → the society derivation pass → evidence.
The run directory is a COMPLETE spatial 0.2 evidence set (byte-compatible: the
TRS trajectory projector works UNCHANGED — the "valid TRS trajectory records"
proof is projection of this very directory) plus `society.jsonl` (per-tick
state + id + trust-update provenance + enforcement events) and
`society_report.json`. **The replay gate re-executes from nothing and
byte-compares ALL EIGHT files**; the fork treatment replays through the
integrated calibration replay path. No wall-clock or host entropy anywhere.
Persistence is the run directory alone (no cross-run state — "unrestricted
persistence" is not permitted and not built).

## 8. Reports (actor-safe + privileged + society outcome)

- **Per-agent ACTOR-SAFE report**: derived exclusively from that agent's own
  recorded actor observations + its own outgoing trust edges; validated by a
  closed exact schema (any unknown key at any depth refuses — the S2C
  validator discipline); contains no other agent's trust row, no private
  facts of others, no privileged content, no chain hashes.
- **PRIVILEGED report**: the full trust matrix, fact states, enforcement
  trace, and society chain ids.
- **Society-level OUTCOME report** (`society_report.json`): final trust
  matrix, token terminal location, enforcement count, fact state, fork
  divergence summary (from the canonical divergence report), and the FIXED
  claim ceiling — a report constructed with any other claim string REFUSES.

## 9. The evidence pack (the ten required proofs, mapped)

| # | Required proof | Mechanism |
|---|---|---|
| 1 | Byte-identical replay | eight-file replay gate (re-execute from nothing) |
| 2 | Per-agent perception non-interference | fork divergence report per-agent perception coordinates + S2C guarantees (spatial layer byte-identical) |
| 3 | Deterministic scheduling and trust updates | integrated S2B dispatch; trust chain re-derives from evidence; cross-registry identical ids |
| 4 | Object location and possession invariants | S2A admission at every transition (integrated); token single-placement asserted per tick |
| 5 | Institutional-rule enforcement trace | non-empty `(position, blocked_effect)` trace; committed script verified rule-clean |
| 6 | Fork isolation and authenticated ancestry | integrated witnessed-fork + calibration pair (anti-transplant; parent evidence unmutated post-fork) |
| 7 | Valid TRS trajectory records | `project_spatial_trajectory` over the seed run dir (0.2-compatible core), per-agent manifests |
| 8 | Actor-safe and privileged reports | §8, closed-schema-validated |
| 9 | Society-level outcome report, no human-fidelity/simulation claim | §8 fixed claim ceiling, refusal-enforced |
| 10 | Permanent regressions for every reproduced audit finding | committed tests pinned per finding, per standing practice |

All pack results are PINNED (64-hex literals) as permanent regressions.

## 10. Threat model + adversarial vectors

| # | Vector | Refusal / invariant |
|---|---|---|
| 1 | Counterfeit society chain over genuine spatial evidence | canonical re-derivation + byte equality (§6) |
| 2 | Trust update from privileged (unperceived) information | updates derive ONLY from recorded actor-view rows, each with provenance; regression flips a hidden placement and asserts zero trust delta |
| 3 | Rule bypass (committed script contains a blocked effect) | build-time refusal + position-by-position rule-clean verification |
| 4 | Silent tick drift (≠ 8 rounds) | derivation refuses; manifest binds the range |
| 5 | Fork transplant / unauthenticated ancestry | integrated witnessed-fork machinery (unchanged) |
| 6 | Society bookkeeping leaking into spatial state/observations | the spatial layer is byte-identical; S2C closed actor schema refuses unknown keys |
| 7 | Actor-safe report carrying others' trust/facts/privileged content | closed exact report schema; multi-depth injection regressions |
| 8 | Claim-ceiling violation (human-fidelity/simulation claims) | fixed string; any other refuses |
| 9 | Evidence tamper | eight-file replay gate at every consumer boundary (bindings are commitments, not verification) |
| 10 | Scope expansion (agents/rooms/actions/rules/edges beyond the seed) | closed scenario + frozen constants; constructors refuse other cardinalities |

## 11. Non-goals (per SC-LC exclusions)

No live personas or Ollama agents; no adaptive trainer or hidden suites; no
labels or behavioral labeling; no weight changes or training; no external
spending; no persistence beyond the run directory; no public claims; no
communication actions, economy, institutions beyond the one rule, population
management, or crash-recovery machinery; no expansion beyond the bounded seed.
Stop after the evidence pack; live-persona runs need separate owner
authorization.

## 12. Compatibility

Additive only: `coliseum/textlab/society/` (new package) + one scenario + one
intervention in the existing closed maps + tests + docs. No change to any
integrated S0..S2D record, contract, or behavior; the spatial evidence core
remains schema 0.2 byte-compatible; all existing pins (golden, corpus,
calibration baseline) remain intact; version dispatch fails closed everywhere.

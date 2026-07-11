# First Gladiator Phase — canonical specification

**Status: DRAFT pending owner sign-off (SC-3). Binding once signed.**
Wiki twin: `Claude-Wiki/03_wiki/projects/coliseum/FIRST-GLADIATOR-VISION.md`
(provenance-marked). After SC-3 this repo copy is canonical; the wiki mirrors.
Companion docs: `ROADMAP.md` (M0–M15 + verification contract),
`GAP-ANALYSIS.md` (16 gaps), `configs/autonomy-roadmap.yaml` (machine twin,
activates at SC-4).

## 1. Phase definitions

- **First Gladiator Phase** — the textlab-based single-agent and bounded
  two-agent LLM behavioral research program defined by this SPEC. Complete
  when every exit criterion in §6 is met with linked evidence.
- **Hunger Games Phase** — a LATER multi-agent survival research program
  (resources, alliances, betrayal, elimination, persistent world/identity).
  Entered only through the M15 readiness review (SC-9).
- Both names were coined by the owner's 2026-07-11 Master Directive; they
  graft onto the existing textlab track and the deferred society blueprints.

## 2. Research purpose

A controlled environment where LLM-agent behavior under authority, moral
conflict, uncertainty, time pressure, self-preservation, social pressure,
deception, and memory can be observed, reproduced, measured, challenged,
compared, and intentionally changed through controlled experimentation.
Scientific defensibility over spectacle. Priority order (binding):
correctness > reproducibility > provenance > experimental validity >
interpretability > safety > coverage > performance > presentation > scale.

## 3. Scope

### Single-agent (core)
- **Eight scenario families**, mapped from scenario-pack-v1's archetypes:
  authority · moral_conflict · uncertainty · time_pressure ·
  self_preservation · social_pressure · deception · memory_persistence.
- Two-pass reflex/planner agents; named + logged arbitration; versioned
  LLM personas (M9); the reflex-planner reversal program (M10); memory
  representations + longitudinal gladiator arcs (M12).

### Two-agent (exit capability, M11)
Exactly two agents in one scenario: independent behavioral configs (two
agent_regime_ids), deterministic turns under a named + logged turn-order
policy, actor-bound observations/actions, byte-identical replay. Small
enough for causal interpretation. NOT a society build.

### Non-goals (binding)
No RL/PPO environments (deferred track) · no populations beyond two agents ·
no game-production polish · no weight training without the SC-8 scoped
exception · no LLM-judge for primary metrics · no cloud execution through
M13 · no J-lens work (Phase-3 blueprint, untouched).

## 4. Governing rulings (inherited, binding)

1. Arbitration named + logged on every node.
2. Delta ops = state truth; absolute state derived.
3. Interaction modes never pool (independent_vignettes vs
   sequential_history; memory-on vs memory-off likewise).
4. Reflex = same model under token-budget pressure; latency log-only;
   stated confidence stored, never arbitrating.
5. Measure-never-reward: no moral-index scalar; decomposed rates only;
   in-world incentives are design variables.
6. Contamination hedge: internal archetype names; **≥2 paraphrase variants
   per scenario** (permanently mandated by the exp-1/exp-2 evidence).
7. Effective sample size = distinct variant×sampler units, retries
   collapsed; never reported as raw run count.
8. **Anti-sprawl**: no scenario outside scenario-pack-v1's 8 archetypes
   without an owner-signed amendment to this SPEC.

## 5. Research claim lifecycle (binding)

```
observation → replication → generalization study → independent audit
    → ACCEPTED FINDING → wiki promotion → paper candidate
```

- Never promote a single observation. Replication = pre-registered
  reproduction (fresh seeds); generalization = breadth across
  scenarios/models/wordings as appropriate to the claim.
- Promotion to ACCEPTED requires an independent Codex **finding audit**
  (the report, exclusions, effective-n, evidence links — not just code).
- Every claim entry (registry: `configs/registry/claims.yaml`, M4/M5)
  links its evidence: experiment_config_hash, manifests, replay artifacts,
  conditioning regime ids. Broken links fail lint.
- Demotion is first-class (the sweep-v2/pilot demotions are precedent).
- Wiki pages carry the ladder position; **paper drafts cite ACCEPTED
  findings only** (enforced by the M15 phase-report generator).

## 6. Exit criteria (the completion definition; each needs linked evidence)

**Infrastructure**
- E1 council-v1 active and stable (launcher enabled, crash recovery
  validated, no protocol changes except reproduced defects).
- E2 experiment runs resumable; replay byte-identical where required.
- E3 run identity collision-resistant; all provenance fields present.
- E4 reports (run/regime/experiment/phase) reproduce idempotently from
  artifacts; Program Dashboard current.

**Scenarios**
- E5 all 8 families implemented, registered, ≥2 paraphrase variants each,
  twins/controls where the family design requires them, frozen in the
  registry after clean pilots.
- E6 held-out scenario set frozen (M4) and never used by any experiment,
  pilot, or training run before the M14 evaluation.
- E7 scenario defects found in pilots resolved or documented.

**Agents**
- E8 reflex, planner, arbitration paths validated; parser failures bounded
  and visible.
- E9 versioned personas with measured intervention strength; persona
  regimes never pooled.
- E10 memory modes available; ONE representation frozen from pilot
  evidence; memory regimes never pooled.
- E11 two-agent execution validated (scripted×scripted then llm×llm) with
  named turn-order policy and actor-bound records.

**Measurements**
- E12 METRICS-v1 frozen (SC-5); any later change is METRICS-v2 with
  migration note.
- E13 seed variance, paraphrase sensitivity, model sensitivity, persona
  sensitivity, memory sensitivity measured; reversal taxonomy classified.
- E14 effective-n accounting correct in every report.

**Experiments**
- E15 deterministic + stochastic baselines complete; wording-replication
  studies complete; memory studies complete; longitudinal arcs complete;
  small two-agent validation complete.
- E16 major findings independently audited (claim ladder); failed
  hypotheses recorded.

**Training**
- E17 the SC-8 decision resolved explicitly: EITHER a scoped LoRA-scale
  intervention completed with pre/post held-out evaluation, side-effect
  audit, and checkpoint lineage, OR this criterion formally amended by
  owner sign-off (never silently skipped).

**Documentation**
- E18 architecture, operator, research, scenario-registry, and
  experiment-registry documentation current; limitations explicit
  (including any surviving RELEASE-BLOCKERS items as accepted
  limitations).

## 7. Scorecard disposition (proposed; decided by SC-3 sign-off)

The 7-rung /30 execution ladder (`coliseum-scorecard-execution-ladder`)
is **retired as the execution tracker** — its rungs assume the RL-first
build order this program defers. The scorecard page stays as a historical
judgment record (concept/design scores unchanged); execution tracking
moves to the M0–M15 verification contract and the Program Dashboard.
Rungs 2/3's substance (behavioral MVP, contamination bar) survives inside
E5/E13/E15. If the owner prefers remapping points to milestones instead,
that choice is recorded at SC-3 and this section is updated.

## 8. Open questions carried into the program

Sample sizes/power (M6 evidence) · sequential-history effect (M6) ·
persona count/effect thresholds (M6/M10) · reversal taxonomy structure
(M10) · time-pressure mechanism adequacy (M8) · memory representation
(M12) · training target (M14) · anomaly thresholds (M7, from M5/M6
distributions) · Hunger Games entry criteria (M15). None may be resolved
by intuition — each has its evidence trigger in the DECISION-REGISTER.

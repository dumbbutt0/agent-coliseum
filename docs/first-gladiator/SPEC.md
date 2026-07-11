# First Gladiator Phase — canonical specification

**Status: DRAFT pending owner sign-off (SC-3). Binding once signed.**

CANONICALITY MAP (what must match what): THIS repo document is canonical.
`Claude-Wiki/03_wiki/projects/coliseum/FIRST-GLADIATOR-VISION.md` is a
COMPANION navigation artifact (frontmatter + per-statement provenance
marks; deliberately a different document, NOT a byte mirror) — it must
AGREE IN SUBSTANCE and point here, nothing more. The only byte-exact pair
in the package is `configs/autonomy-roadmap.yaml` ↔ its wiki copy
`.../autonomy-roadmap-first-gladiator.yaml`. Sibling canonical docs:
`ROADMAP.md` (M0–M15 + verification contract; must agree
milestone-for-milestone with the YAML), `GAP-ANALYSIS.md` (20 gaps).

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

## 4. Governing rules (binding)

Rules 1–7 are INHERITED (wiki rulings + audited implementation); rule 8 is
OWNER-ORIGINATED (ratified new by the 2026-07-11 Master Directive, no
prior wiki precedent).

1. Arbitration named + logged on every node. *(inherited)*
2. Delta ops = state truth; absolute state derived. *(inherited)*
3. Interaction modes never pool (independent_vignettes vs
   sequential_history; memory-on vs memory-off likewise). *(inherited)*
4. Reflex = same model under token-budget pressure; latency log-only;
   stated confidence stored, never arbitrating. *(inherited)*
5. Measure-never-reward: no moral-index scalar; decomposed rates only;
   in-world incentives are design variables. *(inherited)*
6. Contamination hedge: internal archetype names; **≥2 paraphrase variants
   per scenario** — the variant floor was inherited practice, its
   PERMANENT mandate is owner-ratified 2026-07-11 on the exp-1/exp-2
   evidence. *(inherited + owner-strengthened)*
7. Effective sample size = distinct variant×sampler units, retries
   collapsed; never reported as raw run count. *(inherited)*
8. **Anti-sprawl**: no scenario outside scenario-pack-v1's 8 archetypes
   without an owner-signed amendment to this SPEC. *(owner-originated)*

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

## 6. Exit criteria (the completion definition)

Each criterion names its EVIDENCE TYPE — the artifact class that proves it
in `READINESS.md` at M15. A criterion without its named evidence linked is
NOT met; completion is determinable from this table alone.

**Infrastructure**
- E1 council-v1 active and stable (launcher enabled, crash recovery
  validated, no protocol changes except reproduced defects).
  *Evidence:* `council-v1` git tag + M0 gate artifacts
  (`docs/hardening/activation/`) + `systemctl --user` status capture +
  chain-report output showing zero un-audited `tools/council/` changes
  since the tag.
- E2 experiment runs resumable; replay byte-identical where required.
  *Evidence:* M7 chaos-test results (kill-resume, unchanged effective-n) +
  per-experiment `cli replay` byte-gate outputs recorded in the experiment
  registry rows.
- E3 run identity collision-resistant; all provenance fields present.
  *Evidence:* registry lint report (zero missing-provenance rows across
  `configs/registry/experiments.yaml`) + the schema's regime-hash tests
  green at the audited commit.
- E4 reports reproduce idempotently from artifacts; Dashboard current.
  *Evidence:* M5 golden-file test results + a double-generation
  byte-identity check output + the committed `DASHBOARD.md` regenerated at
  the M15 commit.

**Scenarios**
- E5 all 8 families implemented, registered, ≥2 paraphrase variants each,
  twins/controls where the family design requires them, frozen after
  clean pilots.
  *Evidence:* `configs/registry/scenarios.yaml` rows (family, variants,
  twin links, `status: frozen`, content hashes) + the pilot
  RESULT_APPROVED event ids per family.
- E6 held-out scenario set frozen (M4) and never used before the M14
  evaluation.
  *Evidence:* the held-out declaration in the registry (M4 commit hash) +
  the contamination-lint report (no held-out scenario hash appears in any
  prior run manifest).
- E7 scenario defects found in pilots resolved or documented.
  *Evidence:* `docs/ISSUES.md` entries (closed or accepted-limitation) +
  the fixing commits' audit verdicts.

**Agents**
- E8 reflex, planner, arbitration paths validated; parser failures bounded
  and visible.
  *Evidence:* suite results for the agent/parser test files + parser
  failure-rate figures in the M6 regime reports (bounded per METRICS-v1).
- E9 versioned personas with measured intervention strength; persona
  regimes never pooled.
  *Evidence:* `configs/personas/*.yaml` content hashes in regime ids +
  M9 intervention-strength experiment report + pooling-refusal lint tests.
- E10 memory modes available; ONE representation frozen from pilot
  evidence; memory regimes never pooled.
  *Evidence:* the M12 pilot experiment reports + the freeze commit's audit
  verdict + pooling-refusal tests.
- E11 two-agent execution validated with named turn-order policy and
  actor-bound records.
  *Evidence:* M11 replay-determinism test results + the scripted×scripted
  and llm×llm validation runs' RESULT_APPROVED events.

**Measurements**
- E12 METRICS-v1 frozen (SC-5); later changes only as METRICS-v2 with
  migration note.
  *Evidence:* `docs/metrics/METRICS-v1.md` at its audited commit + the
  SC-5 ratification chain event + (if any) METRICS-v2 migration notes.
- E13 seed variance, paraphrase sensitivity, model sensitivity, persona
  sensitivity, memory sensitivity measured; reversal taxonomy classified.
  *Evidence:* one experiment-registry row + experiment report per
  sensitivity, each RESULT_APPROVED; the M10 reversal-taxonomy report with
  its pre-registration hash.
- E14 effective-n accounting correct in every report.
  *Evidence:* report-generator tests asserting effective-n columns +
  spot-audit note in the M15 independent audit.

**Experiments**
- E15 deterministic + stochastic baselines, wording-replication, memory
  studies, longitudinal arcs, and two-agent validation all complete.
  *Evidence:* the experiment registry filtered to these six categories —
  every row bearing a RESULT_APPROVED event id and a report link.
- E16 major findings independently audited; failed hypotheses recorded.
  *Evidence:* `configs/registry/claims.yaml` — every `accepted` row citing
  its finding-audit verdict; `refuted`/`demoted` rows preserved with
  reasons.
- E17 the SC-8 decision resolved explicitly: EITHER a scoped LoRA-scale
  intervention completed with pre/post held-out evaluation, side-effect
  audit, and checkpoint lineage, OR this criterion formally amended by
  owner sign-off (never silently skipped).
  *Evidence:* the SC-8 owner chain event; if approved — the training
  design's audit verdict + pre/post comparison report + checkpoint-lineage
  manifest; if amended — the owner-signed SPEC amendment commit.

**Documentation**
- E18 architecture, operator, research, scenario-registry, and
  experiment-registry documentation current; limitations explicit.
  *Evidence:* `docs/` + registry files at the M15 commit + the
  RELEASE-BLOCKERS disposition table (each item closed or listed as an
  accepted limitation in READINESS.md).

## 7. Scorecard disposition (proposed; decided by SC-3 sign-off)

The 7-rung /30 execution ladder (`coliseum-scorecard-execution-ladder`)
is **retired as the execution tracker** — its rungs assume the RL-first
build order this program defers. The scorecard page stays as a historical
judgment record (concept/design scores unchanged); execution tracking
moves to the M0–M15 verification contract and the Program Dashboard.
Rungs 2/3's substance (behavioral MVP, contamination bar) survives inside
E5/E13/E15. If the owner prefers remapping points to milestones instead,
that choice is recorded at SC-3 and this section is updated.

## 8a. Kill the King program annex (owner directives, 2026-07-11)

The post-objective generalization program and the biblical moral-theme
framework are specified in `docs/first-gladiator/KTK-PROGRAM.md` — ratified
TOGETHER with this SPEC at SC-3 and binding thereafter. Summary of what it
adds without renumbering the roadmap: the 10-phase moral arc lands in the
M12 longitudinal-arc design; registry fields (invocation role, failure
taxonomy, generalization level L1–L4) land at M3/M4; the failure/recovery
taxonomy generalizes M10's freeze pattern; OFFLINE synthetic-derivation and
prefix-only monitor-prediction pilots land at M13; adapter experiments
remain exactly the M14/SC-8 gate with a mandatory regression battery;
deeper weight-level work (its phase J) and monitor training at scale are
post-First-Gladiator; Hunger Games remains SC-9. Hard boundaries: no
`biblical_morality` scalar; no recognition-reward; L4 hidden variants
(de-biblicized structural twins) required for the strongest claims;
interpretive plurality via registered rubric branches; the
measure-never-reward invariant and the deterministic Judge preserved
verbatim (annex §G).

## 8. Open questions carried into the program

Sample sizes/power (M6 evidence) · sequential-history effect (M6) ·
persona count/effect thresholds (M6/M10) · reversal taxonomy structure
(M10) · time-pressure mechanism adequacy (M8) · memory representation
(M12) · training target (M14) · anomaly thresholds (M7, from M5/M6
distributions) · Hunger Games entry criteria (M15). None may be resolved
by intuition — each has its evidence trigger in the DECISION-REGISTER.

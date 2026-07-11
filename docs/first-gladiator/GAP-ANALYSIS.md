# First Gladiator gap analysis — repository vs exit criteria

CANONICALITY: this repo document is canonical.
`Claude-Wiki/03_wiki/projects/coliseum/FIRST-GLADIATOR-GAP-ANALYSIS.md` is
a COMPANION navigation artifact (NOT a byte mirror) that must agree in
substance and point here.
A capability is NOT complete merely because a partial implementation exists.
Rows flip to CLOSED with evidence links as milestones integrate.
RR = research risk, ER = engineering risk.

| # | Gap | Current → desired | Milestone | Owner? |
|---|---|---|---|---|
| 1 | Canonical specification | greenfield terms → binding SPEC.md (this package) | **M1** | SC-3 |
| 2 | Scorecard disposition | stale 17/30 ladder → retired-or-remapped per SPEC §7 | **M1** | SC-3 |
| 3 | Scenario registry | glob discovery → `configs/registry/scenarios.yaml` + lint (RR pooling/coverage) | **M3** | — |
| 4 | Experiment registry + evidence binding | ad-hoc manifests → design→verdict binding, mutation refusal, retry lineage (ER medium) | **M4** | — |
| 5 | Frozen metric specification | implemented, undocumented → METRICS-v1 (RR silent redefinition) | **M2** | SC-5 |
| 6 | LLM persona system | 4 scripted only → versioned constitutions in regime hash (RR weak interventions) | **M9** | — |
| 7 | Memory representation + experiments | sequential_history plumbed, never run → piloted, ONE frozen, never pooled (ER medium) | **M12** | — |
| 8 | Longitudinal arcs | single walks → linked histories with full lineage (RR narrative-over-measurement) | **M12** | — |
| 9 | Two-agent execution | single-agent runner → two slots, actor-bound records (ER HIGH: runner/schema core) | **M11** | — |
| 10 | Turn-order policy | reflex/planner arbitration only → named+logged turn-order rules | **M11** | — |
| 11 | Report generators | text tables → 4-level idempotent artifact-derived reports (RR numbers detached from evidence) | **M5** | — |
| 12 | Claim-lifecycle support | audit banners only → claims registry, ladder states, evidence-link lint | **M5** | — |
| 13 | Readiness evidence index | none → READINESS.md scoring every criterion | **M15** | SC-9 |
| 14 | Controlled training pipeline | none; weight_training forbidden → design + (if approved) LoRA intervention with held-out eval (ER HIGH) | **M14** | SC-8 |
| 15 | Training policy decision | unmade → explicit scoped exception OR formal SPEC amendment | **M14** | SC-8 |
| 16 | Hunger Games readiness review | no process → M15 review answering the 10 entry questions with evidence | **M15** | SC-9 |
| 17 | Monitor role (prefix-only failure prediction) | nothing → prediction-record schema + leakage boundaries + M13 registered pilot; training at scale post-phase (RR leakage / ER medium) | **M4 fields, M13 pilot** | — |
| 18 | Synthetic training-record derivation | nothing → paired-record schema with full lineage + approval gates, offline M13 pilot; corrections never auto-promoted (RR contamination / ER medium) | **M13** | gate per record class |
| 19 | Generalization ladder + L4 hidden variants | L1/L2 machinery only → registry level field + de-biblicized structural twins held out from training-adjacent use (RR story-recognition confound / ER medium) | **M4 field; M12–M13 authoring** | — |
| 20 | Moral-dimension metrics + 10-phase arc | 6 metrics, single walks → 14 dimensions via extended moral_tags/facts as METRICS-v2; arc phases 2/7/8/10 designed into M12 (RR prose-judgment creep / ER medium) | **M12 + METRICS-v2** | SC-5 successor note |

Additional tracked debt (not exit-blocking): ~~wiki sessions 4–9
ingestion~~ (CLOSED 2026-07-11, M1); `docs/RELEASE-BLOCKERS.md` 7 items →
M13 sweep-up or accepted-limitation entries; stale request-folder files
(`requests/ready/hardening-h5-transactions-001.json`,
`requests/claimed/autonomy-activation-005.json` — chain is authoritative)
→ M3-adjacent cleanup; time-pressure mechanism adequacy → M8 evidence;
anomaly thresholds → M7 from M5/M6 distributions; policy naming gap
(roadmap classes vs auto-approve list) → M7 amendment (SC-7); missing
`/etc/coliseum/enrollment.sha256` (identity ROTATION fails closed; token
burns unaffected) → owner restores from the enrollment secret when
convenient.

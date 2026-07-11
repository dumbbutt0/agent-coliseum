# First Gladiator roadmap — canonical M0–M15

Machine twin: `configs/autonomy-roadmap.yaml` (validated, milestone
`first-gladiator`, 15 tasks, hash `e16e49e80f9e2d05…`). **The Markdown and
YAML must agree exactly; divergence is a defect.** The twin ACTIVATES at
SC-4 (owner roadmap transition — until then the live roadmap at
`Claude-Wiki/coliseum/autonomy-roadmap.yaml`, milestone `society-substrate`,
remains what the tools read; the default-path pointer changes only with the
owner's SC-4 decision). Wiki twin of this document:
`Claude-Wiki/03_wiki/projects/coliseum/FIRST-GLADIATOR-ROADMAP.md`.

## Per-milestone law

implement → focused + full suite green → commit → publish request (correct
task_kind) → Codex audit (≤5 cycles) → unconditional GO or permitted
conditional gate → integrate → update wiki → regenerate Program Dashboard
(once M5 delivers it).

**Experiment milestones additionally**: design freeze → experiment approval
→ execution → evidence manifest → byte-identical replay → result audit →
RESULT_APPROVED → wiki claim update.

## Milestones

- **M0 — H7 reconciliation and activation** ✅ COMPLETE 2026-07-11: native
  gate-4 PASS (both managers) · owner CONDITIONS_SATISFIED (event 000260) ·
  H7 CHANGE_INTEGRATED (000261) · `council-v1` tag · chain-head checkpoint
  pinned · `h7-runbook-reconciliation-001` GO cycle 2 + integrated (000272)
  · owner-attended gates 5–7 → **codex launcher ACTIVE (user service)**.
- **M1 — Canonical specification**: wiki sessions 4–9 ingested; scorecard
  status note; this docs/first-gladiator/ package + `configs/autonomy-
  roadmap.yaml`; owner gates SC-3 (SPEC sign-off) + SC-4 (roadmap
  transition).
- **M2 — METRICS-v1 freeze**: document the deterministic ground-truth
  metrics exactly as implemented (numerator, denominator, exclusions,
  effective units, uncertainty, report form); metric-version constant;
  SC-5 ratification. Changes thereafter = METRICS-v2 + migration note.
- **M3 — Scenario registry and taxonomy**: register the 7 existing
  scenarios; map to the 8 families; version wording variants; enforce ≥2
  paraphrases; registry lint.
- **M4 — Experiment registry and evidence manifests**: bind designs →
  regimes → approvals → artifacts → replay → reports → verdicts; refuse
  post-freeze mutation; retries visible in lineage; back-fill sweep/
  sweep-v2/exp-1/exp-2; freeze the held-out scenario set.
- **M5 — Report and claim lifecycle**: run/regime/experiment/milestone
  report generators derived idempotently from artifacts; claims registry
  with the promotion ladder; evidence-link lint; Program Dashboard.
- **M6 — Sequential-history live baseline**: FRESH protocol-v2 experiment
  requests executing the frozen `docs/SEQUENTIAL-RERUN.md` design +
  stochastic baseline (variance/power) + paraphrase replication; per-batch
  owner approvals (SC-6 ×3); result audits.
- **M7 — Experiment-loop autonomy amendment**: resumable idempotent loop,
  anomaly routing with evidence-derived thresholds; then the ONE owner
  policy amendment adding `ollama_local` automation (SC-7). All standing
  halts retained.
- **M8 — Time-pressure and reflex validation**: pilot whether the
  budget-pressure mechanism isolates the intended intervention; latency
  stays log-only; author + freeze the time_pressure and self_preservation
  families (batch pattern: ≤2 families/request, twins, ≥2 variants,
  internal names, lint, scripted then ollama pilots).
- **M9 — LLM personas**: versioned constitutions hashed into
  behavioral_config → regime ids; `persona:legacy-implicit-v0` for prior
  runs; pooling prevented; intervention strength + parser stability
  validated before any count expansion. Scenario batch B (social_pressure
  + uncertainty + pack-v1 gap-fill) may run in parallel.
- **M10 — Reflex-planner reversal program**: taxonomy frozen FROM observed
  data; controlled wording/model/persona/sampling comparisons; replication
  reported separately from generalization.
- **M11 — Two-agent execution foundation**: deterministic turns; named +
  logged turn-order arbitration; actor-bound observations/actions; replay
  + regime separation; ONE two-agent scenario; scripted×scripted then
  llm×llm validation.
- **M12 — Memory and longitudinal arcs**: pilot memory representations;
  freeze ONE after evidence; linked gladiator histories (the pack-v1
  Kill-the-King / Nothing-Changes arc); measure retaliation, forgiveness,
  loyalty, betrayal, drift.
- **M13 — Experiment completion**: finish required single- and two-agent
  cells; complete coverage; audited reports; anomalies resolved or
  documented (incl. the RELEASE-BLOCKERS sweep-up).
- **M14 — Training decision gate**: target selected FROM baseline
  evidence; SC-8 decides the scoped `weight_training` exception or a
  formal SPEC amendment (never silent skip); held-out contamination lint;
  if approved: LoRA-scale intervention + pre/post held-out comparison +
  side-effect audit + checkpoint lineage.
- **M15 — Readiness review**: every SPEC exit criterion linked to evidence
  in `READINESS.md`; no unresolved BLOCKED requests; independent
  completion audit; Hunger Games entry review; SC-9 verdict; tag
  `first-gladiator-v1`.

## Program verification contract

- **M0**: native gate-4 `ok:true` · H7 integrated · `council-v1` tag ·
  only `coliseum-codex-launcher` enabled · `systemctl --user` active ·
  chain verifies. *(All verified 2026-07-11.)*
- **Source milestones**: `python3 -m pytest tests/ -q` green · Codex GO on
  the exact commit · chain verifies · integrated code == audited commit ·
  wiki update links request + commit + verdict + tests.
- **Experiment milestones**: design freeze recorded BEFORE execution ·
  batch approval exists · evidence manifest complete · byte-identical
  replay where required · registry entries present · reports regenerate
  idempotently · effective-n correct · RESULT_APPROVED before any claim
  enters the wiki.
- **Program level**: every exit criterion evidenced in READINESS.md · no
  unresolved BLOCKED requests · no incompatible pooling · claim-strength
  labels everywhere · deferred decisions wait for their evidence triggers
  · the M15 verdict independently audited.

## Owner re-entry points

SC-1 ✅ · SC-2 ✅ · SC-3 SPEC sign-off (M1) · SC-4 roadmap transition (M1)
· SC-5 METRICS-v1 (M2) · SC-6 batch tokens ×3 (M6) · SC-7 ollama_local
amendment (M7) · SC-8 training gate (M14) · SC-9 readiness verdict (M15).
Standing halts: see `Claude-Wiki/03_wiki/projects/coliseum/
AUTONOMY-BOUNDARIES.md` (13 conditions; ordinary audit processing stays
autonomous).

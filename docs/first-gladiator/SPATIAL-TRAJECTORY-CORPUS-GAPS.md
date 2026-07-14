# Spatial trajectory corpus — training-readiness verification + gap report

Owner golden-suite directive (2026-07-14), phase 2: generate trajectory datasets
from the golden-suite experiments and **verify the training-readiness records
contain everything eventually needed**. This is the verification's report of
record. Verdict: **the v1 record layer is PARTLY architecture-neutral** — two
records reuse cleanly, four needed additive spatial variants, and the evidence
layer needed one additive extension. Nothing was fabricated to force a fit.

## 1. What reused cleanly (no change)

| Record | Reuse |
|---|---|
| `trs.observation.actor/privileged.v1` | As-is. The spatial runner already emits the canonical per-view artifacts at every chain position; the projector consumes the RECORDED ids (provenance-bound by the evidence binding). |
| `trs.trajectory_manifest.v1` | As-is — its optional `world_line_id` field was designed for exactly this producer. Episode boundaries carry `interaction_mode: spatial_sequential_v1` with one episode starting at 0. |
| `termination` taxonomy | As-is. Last decision per agent = `natural_terminal` (the scenario's designed exclusive stop); all others `continuing`. |

## 2. Gaps found (v1 records that cannot represent a spatial trajectory)

| # | v1 record | Gap | Resolution (additive variant) |
|---|---|---|---|
| G1 | `trs.source_evidence.v1` | Requires a HEX `run_id` and binds exactly the vignette files (`run.json` + `decisions.jsonl`). Spatial run ids are scenario-shaped strings; spatial evidence is six files. | `trs.source_evidence.spatial.v1` — descriptive run id + a content hash for EVERY evidence file. |
| G2 | `trs.behavior_policy_spec.v1` | REQUIRES non-empty `comparison_regime_id` + `agent_regime_id` (vignette regime hashes). A scripted spatial agent has no comparison regime; fabricating one is forbidden. | `trs.behavior_policy_spec.spatial.v1` — identity = (scenario, agent key, agent body, committed action-script commitment, the agent's `perception_regime_id` — the spatial analogue of `agent_regime_id` — and the frozen substrate versions); `exploration_mechanism: deterministic_script`. |
| G3 | `trs.legal_action_set.v1` | Cardinality ≥ 2 (bound to `DecisionPoint.available_actions`). Spatial decisions can have EXACTLY ONE legal action (a forced move is still behavior-policy support). | `trs.legal_action_set.spatial.v1` — sorted duplicate-free canonical action-id universe, cardinality ≥ 1. |
| G4 | `trs.decision_record.v1` | Type-bound to the vignette `LegalActionSet` (isinstance check), so G3's variant cannot bind; also lacks the spatial anchors. | `trs.decision_record.spatial.v1` — same field semantics + `scheduler_position`, `world_line_id`, `world_state_hash`; sequential prev links enforced (`prev_decision_hash` null exactly at position 0); selected action must be legal under the EXACT bound spatial set. |
| G5 | Evidence layer | The S2D 0.1 run dir did not persist per-decision legal context: `Activation` contents and the candidate-effect universe existed only in memory. Without them, behavior-policy support (what COULD have been chosen) is unrecoverable from evidence. | Run schema **0.2** (additive): `activations.jsonl` (per-position dispatch context: Activation content, FULL candidate universe as canonical action ids + effects, selected effect) + `closure.json` + `action_script_commitment` in `run.json`. Identity records unchanged (golden pins intact); replay still byte-identical over all six files; 0.1 evidence is REFUSED by the projector, never approximated. |

## 3. Honesty decisions (recorded, not patched over)

- `high_level_intent` is **null**: scenario intents are builder inputs, not run
  evidence. If intents should become evidence, that is a runner extension, not a
  projector fabrication.
- **PASS activations are not decisions**: no legal action existed, so there is no
  behavior to imitate and no legal set to bind. They are counted per agent in the
  projection output (`pass_positions`) — reported, never mis-coded.
- A **pure-pass agent** yields no manifest (`agents_without_decisions`), rather
  than an empty-but-plausible trajectory.
- The projector is pure over evidence bytes: no registry, no re-execution, no
  fabricated provenance; unsupported evidence schemas fail closed.

## 4. What a future records rev should consider (owner decision, not taken here)

Fold the spatial variants back into architecture-neutral v2 shapes: availability-
wrapped regime fields on the policy spec; a producer-keyed evidence binding;
cardinality ≥ 1 legal sets with an explicit `forced_choice` marker; a decision
record parameterized over its legal-set domain. Until then the additive
domain-separated variants keep both producers honest, and version dispatch keeps
them from ever aliasing.

## 5. Corpus verification (committed regressions)

Every golden-suite scenario + the original R3 scenario projects end-to-end; the
corpus tests assert: recorded-observation provenance (decision hashes equal the
evidence's recorded ids), sequential integrity (contiguous positions, intact prev
links), selected-action legality under the exact bound universe, per-agent policy
identity stability, termination coding, pinned corpus manifest ids for drift
detection, and the fail-closed refusal of pre-0.2 evidence.

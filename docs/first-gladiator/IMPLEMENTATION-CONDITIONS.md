# Implementation Conditions & Phase Gates (register)

> **Purpose.** A machine-visible carry-forward of the conditions attached to the three integrated design
> sources, plus the phase gates that must be satisfied before later implementation phases. There is no
> automatic conditions register in the council tooling — conditions live immutably in each verdict's
> `conditions[]` array; this file is the human/agent-readable carry-forward and the binding rule.
>
> **Binding rule.** Any future implementation request whose scope touches a gated area **must bind the
> applicable condition/gate in its `scope`**. A purely structural request (e.g. T0-A dataset export) that
> touches no gated area binds none. **No design-source adoption authorizes implementation** — adoption GO's
> grant only the governed design/roadmap source.

## Integrated design sources (owner SC-gate, 2026-07-12)

| Source | Request | Verdict event | CONDITIONS_SATISFIED | CHANGE_INTEGRATED | Commit |
|---|---|---|---|---|---|
| Butterfly Rev. 6 | `first-gladiator-butterfly-annex-001` | `000569` | `000580` | `000583` | `0bf83bc5` |
| Trained Behavioral-Agency Program Rev. 3 | `first-gladiator-training-annex-001` | `000577` | `000581` | `000584` | `a138aa3f` |
| Scenario Robustness & Mutation Track | `first-gladiator-scenario-mutation-annex-001` | `000579` | `000582` | `000585` | `a138aa3f` |

## Carried conditions (from the on-chain verdicts)

- **G-ADOPT (all three, C1).** Adoption binds only the pinned documentation source at its hash; it authorizes
  **no** implementation, schema/registry/runtime change, environment execution, training/weights, registration,
  M0–M15/METRICS/policy change, external mutation-provider integration, or publication claim.
- **G-ENV (training-annex `000577` C2) → binds Phase 9 (environment implementation).** Any future environment
  implementation request must explicitly resolve the version-dispatched `agent_regime_id` /
  `environment_regime_id` / `comparison_regime_id` axis construction and the `generation_recipe` /
  `held_constant_hash` / `changed_dimension_hash` payload details; it **may not independently alter
  `agent_regime_id`**, and all historical `agent_regime_id` identities must remain **byte-identical**.
- **G-MUT (scenario `000579` C1/C2) → binds Phase 10 (scenario-mutation implementation).** Before mutation
  implementation, resolve: `generation_recipe` own domain separator + schema version + mode-specific
  non-applicable sentinels + (for local Ollama) inference/runtime version, tokenizer/chat-template behavior,
  context/truncation, and stop configuration; and define exact canonical typed payloads for `held_constant_hash`
  and `changed_dimension_hash`. Plus the standing P4RS3LT0NGV3 licensing/supply-chain review and the
  no-copy/vendor / no-OpenRouter-for-hidden / untrusted-content / resource-isolation controls.

## Phase gates (roadmap-order requirements, not yet satisfied)

- **G-SOCIETY-PROFILE → required before Phase 6 (persistent-society implementation).** A compact,
  implementation-ready **Persistent Society MVP Profile** must be authored and **council-routed as a bounded
  design-source request before any Phase-6 society code**. It must resolve: (1) world time & scheduling
  (tick/turn/encounter/episode/world-day/lifetime/replicate; scheduled vs state-triggered vs agent-caused
  events; inactivity/timeouts/simultaneous resolution; when consequences/memory/relationships update; pause/
  checkpoint/resume/crash-recovery); (2) experimental boundaries (attempt/decision/encounter/episode/
  effective-unit/lifetime/world-generation/society-replicate; which level supports which claim; retries collapse
  without becoming lived experiences; persistent-world dependence + cluster identity); (3) counterfactual world
  forks (committed checkpoint at logical point X → intervention/control branches; bind parent-world/fork-point/
  branch/held-constant/changed-dimension; no cross-branch leakage; separate cells); (4) Gladiator lifecycle
  (creation…death/replacement/resurrection/retirement/escape; distinguish model vs policy/persona vs Gladiator
  vs memory/relationship/intervention identity; process restart ≠ new Gladiator; retry ≠ second lived event;
  clone/resurrection ≠ silent continuity); (5) memory architecture (immutable history / working / retrieved /
  relationship / autobiographical summary / public-institutional / hidden evaluator state; update-policy +
  summarizer + retrieval identity/version + capacity + provenance + observation boundary; forgetting/retrieval-
  failure/false/manipulated/disputed memory; never infer policy learning from a memory-mediated change; agent
  inspect/challenge/correct); (6) communication protocol (public/private/group/rumor/promise/vote/trade/threat/
  accusation/evidence/coalition/silence; bind sender/intended-vs-actual recipients/visibility/ordering/delivery;
  no private leakage into unauthorized prompts; no simultaneous leakage via sequential generation; unintended
  channels = failures or registered factors); (7) minimum society-state ontology (agents/locations/resources/
  ownership/relationships/observer-reputation/alliances/institutions/roles/laws+enforcement/promises-debts/
  injuries/secrets/public-facts/private-observations/conflicts — small + extensible, no general world engine);
  (8) scenario director (scheduled/state-triggered/recurring/role-conditioned/private-public events; eligibility/
  cooldowns/prerequisites/contradiction-prevention; immediate + delayed consequences; canonical + irrelevant
  perturbation + morally-relevant counterfactual; record causal source category); (9) endogenous-vs-imposed
  event source category on every consequential event; (10) exact first training target (recommended:
  "given admitted pre-decision evidence about this Gladiator and its registered history, predict which available
  registered intervention is most likely to improve the preregistered bounded behavioral vector without critical
  regression" — prediction ≠ selection ≠ memory-mediated ≠ weight learning); (11) resource-comparison regime
  (token/context/reasoning/tool/memory/runtime/timeout; equal-tokens vs equal-info vs equal-actions vs equal-
  episodes vs equal-compute vs model-native — reported, never silently equated); (12) control populations
  (scripted/random/fixed-policy/memory-disabled/planner-disabled/reputation-blind/intervention-free-LLM/
  same-model-different-history/different-model-matched-history); (13) failure & recovery (invalid output/provider
  failure/transition crash/partial trace/timeout/memory overflow/impossible state/deadlock/universal refusal/
  unclosed events — quarantine + recover, **never fabricate** action/event/memory/consequence; partial worlds &
  failed branches stay ledgered, never presented as complete); (14) initial implementation envelope (3–5 named
  Gladiators; one shared location; public + one private channel per pair; two resources; ownership+transfers;
  evidence-backed relationship/reputation; short + summarized long memory; one authority role; one institution;
  six calibrated scenario families; ~20–50 governed decision events/lifetime; deterministic checkpoints; one
  matched world fork; one Butterfly intervention; one delayed consequence; one betrayal-and-recovery arc; one
  corrupt-king/post-king continuation fixture; complete decision graphs + environment traces + replay — final
  counts bound by a future pilot/AcceptanceProfile, not universal thresholds); (15) profile acceptance (exact
  schemas/typed payloads where identity depends on them; invariants; failure states; tests; migration/legacy
  behavior; unresolved authority decisions; explicit non-goals). **Its approval authorizes no weight training,
  large-population execution, or Hunger Games.** **It must not delay** T0-A, measurement calibration, scenario
  calibration, Butterfly identity work, or two-Gladiator calibration.
- **G-WEIGHTS → binds T1–T3 auxiliary training and T4+ Gladiator/policy weights.** T1–T3 need an explicit
  council interpretation of the `weight_training` token; T4+ need the M14/SC-8 scoped exception. No weight work
  is inferred from hardware feasibility.
- **G-HUNGER → binds the Hunger Games format.** Requires a separate readiness review after the persistent
  Gladiator research base is validated; combat/survival success is never treated as alignment.

## Standing council working rules (applies to every request)

Inspect before modifying · preserve unrelated work · never rewrite historical identities · never silently
migrate/pool evidence · version-dispatched schema only · legacy reconstruction byte-identical · one bounded
request at a time · independent Codex audit · hidden evidence never trains while active/claim-supporting · no
post-result mutation search vs hidden suites · no hand-edited research numbers · no implementation inferred from
doc approval · no weight training inferred from hardware feasibility · stop at genuine owner/policy/schema/
normative/external-system/training gates.

# Scenario Robustness & Mutation Track — Plan (Rev. 1)

> **Status: READ-ONLY DRAFT for owner review.** A plan-first, **separately-governed** companion to
> `TRAINED-BEHAVIORAL-AGENCY-PROGRAM.md` (§39 cross-references this design). Nothing implemented, committed,
> registered, routed, published, or trained. No production code / schema / registry / metric / policy / M0–M15
> change. Butterfly Rev. 6 and its request are untouched. The external tool **P4RS3LT0NGV3** is inspected
> read-only at pinned commit `a6cb7c9054800e106b63888d362601922477a614` — **no source copied or vendored, no
> dependencies installed, no OpenRouter/external API called, no confidential/hidden data sent anywhere.**
> Separately governed from Butterfly, the Environment Mechanism Track, training, and the M0–M15 roadmap.

## Section 1 — Purpose & bounded claims

A **proposed, authorization-gated** design for a **deterministic scenario mutation + validation-fuzzing** system
over **Coliseum scenarios, parsers, normalizers, validators, and model behavior** — intended for *defensive*
research only. **No approval currently authorizes this track** (it routes as its own council request, §21). It
answers: which prompt changes preserve meaning but change model behavior? which surface changes bypass or
break a parser / normalizer / validator? which changes alter reflex / planner / arbitration / final action?
which validators fail before the model is reached? which transformations create false acceptance vs false
rejection? which effects transfer across models / seeds / scenario families / validation stacks? which effects
are caused by changed *semantics* rather than changed *representation*?

**Boundaries (binding).** This is not authorization to bypass third-party systems or test systems outside the
owner's control. **P4RS3LT0NGV3 is a mutation *provider* only — never the authority** for semantic equivalence,
scoring, acceptance, or claims. No claim that an artificial result implies a real-world security guarantee. A
single successful string is a **test case, not a general bypass finding** (§16). No overclaiming.

## Section 2 — Existing architecture map (grounded)

- **Scenario identity** = `scenario_id` + `behavioral_hash()` over `BEHAVIORAL_KEYS`
  (`schema.py:304-320`), persisted per run as `Run.scenario_hash`. There is **no `scenario_content_hash`
  field** — the content hash *is* `behavioral_hash` == `scenario_hash`.
- **Variants** = `variant_id` inside a scenario (`variants[]`, ≥2 required), selected `seed % n`
  (`scenario.py:137-139`); no separate variant-content hash (variant text flows into `behavioral_hash`).
- **Held-out contamination lint keys on BOTH `scenario_id` AND `scenario_hash`** (`registry.py:198-216`) — a
  mutated scenario cannot leak by id or by content hash.
- **Replicate / effective-n:** `_replicate_key = (variant_id, scenario_seed, sampler_seed)`
  (`metrics.py:212-218`); `effective_n` = distinct `(variant, sampler_seed)` (`metrics.py:279`);
  `_collapse_attempts` (retries never averaged).
- **Twin/control:** `control_of`/`controls` + `lint_twin_pair` ("a twin changes ONE variable; its decision
  structure must match the primary") — the exact semantics of a controlled mutation.
- **Two validation layers a mutation stresses:** (a) authoring input validation + `lint_agent_facing` /
  `CONTAMINATION_WORDS` (`scenario.py:21-34`) **before** the model; (b) version-dispatched
  `parse_llm_response` (`agents.py:323-364`) **after** the model.
- **Families locked to eight** (`scenario.py:189-193`, anti-sprawl); a new "robustness" family/tag is a SPEC
  change.
- **Milestone ownership:** M3 scenario registry, M4 held-out/contamination, M8/M9 scenario batches +
  parser-stability, M10 wording/model/persona comparisons (closest existing home), M14 contamination gate.
- **Not in code (design-only):** `partition_group_id` / group-aware partitioning; the Butterfly `Intervention*`
  types; any fuzzing/adversarial/security module.

## Section 3 — Gap analysis

Existing identities suffice for the *frozen mutated-artifact* layer but leave three gaps: **(1) no
transform/provenance identity** — nothing records *how* a mutated scenario was derived (parent id, transform,
tool, seed); **(2) no design-time vs runtime vs security-validation distinction** — the registry has only
`status` + `family`, so a security-validation artifact would look like ordinary eval content; **(3) no runtime
perturbation path** — a live perturbation (mutating a prompt without a new frozen scenario) has no home. This
track fills exactly these gaps with a thin overlay + a category rule, not a parallel identity hierarchy.

## Section 4 — Three architectural uses (machine-resolvable; never silently pooled)

1. **Design-time scenario mutation** — applied **before manifest freeze**; produces a **frozen** scenario
   variant; exact mutated content belongs to **scenario/design identity**; used for prompt-robustness /
   measurement-invariance studies.
2. **Runtime trajectory mutation** — applied **during a run**; is a **registered state/information/environment
   intervention** using **Butterfly or Environment Mechanism Track identity + realization rules**; must not
   masquerade as an ordinary scenario variant.
3. **Authorized security-validation vector** — tests a parser / normalizer / decoder / classifier / validation
   boundary; runs in an **isolated defensive-security track** with its own evidence root + authorization
   identity; **does not** auto-become model-training data or an alignment intervention; **cannot target an
   external system** without separate explicit authorization.

A registered `mutation_use ∈ {design_time, runtime, security_validation}` marker makes this machine-resolvable;
cross-substitution is rejected (tests, §15). **`mutation_use` is a schema/versioning decision (a provenance
field, not a `behavioral_hash` input, §5) — distinct from and not requiring a new robustness scenario family
(the eight-family SPEC lock is a *separate* decision).** Both are proposed, neither authorized here.

## Section 5 — Identity & provenance model (reuse existing; no new triad)

**Canonical content identity (one value).** The single scenario content identity is the value from
`behavioral_hash()` over `BEHAVIORAL_KEYS` (`schema.py:304-320`), **stored on the run as `scenario_hash`**;
`behavioral_hash` (registry side) == `scenario_hash` (run side), and `scenario_content_hash` (the name used in
the Butterfly `execution_instance_id` payload) is a **documentation alias of that same value**. The held-out
registry (by id AND this hash), execution identity, mutation provenance, replay, and partition checks **all bind
this one value**.

**Decision: do NOT mint a new spec/regime/realization triad.** A **design-time frozen mutation = a registered
scenario/variant revision** reusing `scenario_id` + the canonical `scenario_hash` + `variant_id`, inheriting
held-out(by id AND hash) + `_replicate_key` + retry-collapse + effective-n + twin machinery. The
`mutated_scenario_content_hash` **IS** the new `scenario_hash`/`behavioral_hash` (not a new hash type).

**Provenance + intent overlay (the only new identity).** `source_scenario_id` · `source_scenario_content_hash`
(= parent `behavioral_hash`) · `scenario_mutation_spec_hash` (canonical typed hash of the transform recipe) ·
`mutation_family` · `transform_id` · `transform_version` · external-tool identity + **pinned P4RS3LT0NGV3
commit** · canonical parameters · declared seed · RNG algorithm/version · transform chain + order + chain-depth
limit · `mutated_scenario_content_hash` (= new `behavioral_hash`) · normalizer version · decoder version ·
expected invariance class · **layered** semantic-equivalence status + authority (§7) · `partition_group_id` ·
`mutation_use` (§4) · `mutation_target_surface` (below) · authorization scope. Hashing uses the repository
canonical rule (`sha256(canonical_json(payload))`, domain-separated, typed, no raw concat).

**`mutation_target_surface` (audit-response — machine-resolvable enum; what is mutated).** Every mutation
declares the surface it is applied to: `authoring_artifact` · `parsed_scenario` · `rendered_prompt` ·
`agent_observation` · `memory_context` · `model_output` · `parser_input` · `normalizer_input` ·
`validator_input`. It is **bound into mutation provenance and pair validation (§13).** The surface **determines
the category (§4)**: a `model_output` / `parser_input` / `normalizer_input` / `validator_input` mutation is a
**security-validation vector, NOT a scenario variant, and must not use scenario identity as though the scenario
changed**; an `agent_observation` mutation may be an **environment intervention**; a `memory_context` mutation
may be a **Butterfly *state* intervention**; only `authoring_artifact` / `parsed_scenario` (frozen before
execution) are **design-time scenario variants**.

**Representation-pipeline identity (audit-response — where a mutation vanishes or changes meaning).** For
Unicode / whitespace / encoding / parser tests, `behavioral_hash` alone is insufficient: a mutation can
disappear during file reading, YAML/JSON parsing, normalization, prompt rendering, or decoding. Bind the
applicable stage identities: `raw_authored_artifact_hash` · `parsed_scenario_hash` · `rendered_agent_facing_hash`
· `normalized_input_hash` · `decoded_payload_hash` · `validator_input_hash`. **Absence is recorded explicitly
when a stage does not apply; a missing *required* stage rejects the case.** Reports **localize the first stage
at which two representations diverge, normalize together, fail, or disappear** (§14), and tests exercise line
endings, Unicode normalization, invisible characters, YAML/JSON parsing, prompt rendering, decoder order, and
validator-input construction (§19).

**Versioned `RepresentationPipelineProfile` (C3 — stage applicability is frozen, not decided after
observation).** A versioned profile, **bound before generation/execution**, defines: the **ordered stages** ·
the **implementation + version for each stage** · which stages are **required vs non-applicable** (and by whose
authority) · **canonicalization rules per stage** · **failure behavior**. Its hash is bound into
`scenario_mutation_spec_hash` and the study/`AcceptanceProfile` design. This removes the degree of freedom of
labeling a problematic stage "non-applicable" *after* observing its behavior: the applicability decision is
authoritative only if it was frozen in the profile before any outcome was seen.

**`mutation_use` authority vs scenario-family authority (audit-response — two independent decisions).** Adding
**`mutation_use`** (and `mutation_target_surface`) is a **schema/versioning** decision; adding a **robustness
scenario family** is a **separate SPEC decision** under the eight-family lock (`scenario.py:189-193`). They are
NOT the same choice. **`mutation_use`/`mutation_target_surface` do NOT participate in `behavioral_hash`** — they
live in a **separate provenance record** (so recording provenance never changes a scenario's content identity);
if they were ever folded into a hashed structure it would be by **version-dispatched construction preserving all
historical hashes** (add-with-default). **No new scenario family is required merely to record mutation
provenance** — a new family is proposed only if the study genuinely needs one, as its own SPEC amendment.

**Exact mutation-pair lineage (R3) — each object defined (audit-response).**
- **`source_variant_id`** — the canonical source scenario's `variant_id`.
- **`source_evaluation_unit_id`** / **`mutated_evaluation_unit_id`** — the canonical source's and the mutated
  arm's effective units `(variant_id, scenario_seed, sampler_seed)` (`_replicate_key`); the pair binds **both**
  (C2), and the validator (§13) **requires the two replicate keys to match wherever the design calls for paired
  seeds** (`scenario_seed`/`sampler_seed` held constant while only the mutation dimension varies).
- **`mutation_case_id`** — identity of **one frozen mutated artifact** (exact formula below): source identity +
  `scenario_mutation_spec_hash` + `mutated_scenario_content_hash`.
- **`mutation_pair_id`** — identity of the **intentional relation of one mutated case to one canonical
  artifact** — an **exact** canonical typed identity (formula below) binding **both evaluation units** (source
  and mutated replicate keys, both `variant_id`s, both scenario hashes, `mutation_case_id`, `held_constant_hash`,
  `changed_dimension_hash`, `equivalence_profile_hash`, `partition_group_id`, `mutation_target_surface`), so
  cross-seed / cross-variant / control-unit substitution is blocked by identity, not left to validator behavior.
- **`mutation_attempt_id`** — identity of **one execution attempt**; it **binds `execution_instance_id`** (and,
  through `mutation_pair_id`, the paired control's evaluation-unit identity).
A **technical retry keeps the same `mutation_case_id` + `mutation_pair_id` + effective unit but receives a
distinct `mutation_attempt_id`** (reuses `_collapse_attempts`); multiple mutated outputs cannot collide on one
`mutation_pair_id`/`mutation_case_id` (§13, tests §19).

**Exact payload definitions (audit-response — canonical, domain-separated, schema-versioned; missing/ambiguous
required field rejects).**

```text
scenario_mutation_spec_hash = H(
    mutation_spec_domain_separator     # "coliseum:scenario-mutation-spec:v1"
    ‖ mutation_spec_schema_version
    ‖ mutation_use                     # design_time | runtime | security_validation
    ‖ mutation_target_surface
    ‖ ordered_transform_chain          # [transform_id@transform_version, ...] in applied order
    ‖ transform_parameters             # canonical parameters per transform
    ‖ pinned_tool_repository_identity  # tool name + pinned commit (e.g. P4RS3LT0NGV3 a6cb7c9…)
    ‖ generation_recipe                # discriminated union keyed by generation_mode (below) — must be
                                       #   SUFFICIENT to regenerate the artifact (C1)
    ‖ reversibility_class              # §6
    ‖ expected_invariance_claim        # claim type → required §7 layers
    ‖ equivalence_profile_hash         # the frozen EquivalenceProfile (§7) this claim binds
    ‖ representation_pipeline_profile_hash  # the frozen RepresentationPipelineProfile (§5, C3)
    ‖ required_normalizer_profile
    ‖ required_decoder_profile
)

# generation_recipe — discriminated union (C1); required fields per mode, missing/ambiguous → reject:
generation_recipe = H(
    generation_mode                    # offline_deterministic | local_semantic_ollama | isolated_adversarial
    ‖ generator_identity               # audited transform-set id | local model name
    ‖ generator_config_hash            # local_semantic_ollama: H(model_digest ‖ prompt_template_hash
                                       #   ‖ temperature ‖ sampler_config ‖ declared_seed); else transform-config hash
    ‖ declared_seed_or_not_applicable  # explicit sentinel when a mode is non-stochastic
    ‖ rng_algorithm
    ‖ rng_version
    ‖ rng_stream_identity              # declared domain-separated stream id(s); randomMix refused
)

mutation_case_id = H(                  # ONE frozen mutated artifact
    mutation_case_domain_separator     # "coliseum:mutation-case:v1"
    ‖ mutation_case_schema_version
    ‖ source_scenario_id
    ‖ source_scenario_hash             # parent behavioral_hash
    ‖ source_variant_id
    ‖ scenario_mutation_spec_hash
    ‖ mutated_scenario_content_hash    # frozen mutated behavioral_hash
)

mutation_pair_id = H(                  # exact canonical↔mutated relation; binds BOTH evaluation units (C2)
    pair_domain_separator              # "coliseum:mutation-pair:v1"
    ‖ pair_schema_version
    ‖ source_scenario_hash
    ‖ source_variant_id
    ‖ mutated_scenario_hash            # = mutated behavioral_hash
    ‖ mutated_variant_id
    ‖ mutation_case_id
    ‖ source_replicate_key             # (source_variant_id, scenario_seed, sampler_seed)
    ‖ mutated_replicate_key            # (mutated_variant_id, scenario_seed, sampler_seed)
    ‖ held_constant_hash
    ‖ changed_dimension_hash
    ‖ equivalence_profile_hash
    ‖ partition_group_id
    ‖ mutation_target_surface
)

mutation_attempt_id = H(               # ONE execution attempt
    mutation_attempt_domain_separator  # "coliseum:mutation-attempt:v1"
    ‖ mutation_attempt_schema_version
    ‖ mutation_case_id
    ‖ mutation_pair_id
    ‖ execution_instance_id            # exact pre-realization attempt identity (Butterfly); NOT a run_id
                                       #   that embeds this hash → no circular dependency
    ‖ attempt_ordinal
)
```

Any missing or ambiguous **required** field rejects the object. `mutation_case_id` binds source identity +
mutation-spec hash + frozen mutated-content identity; `mutation_attempt_id` additionally binds
`execution_instance_id` (the exact attempt identity) with **no circular dependency** (`execution_instance_id`
never embeds `mutation_attempt_id`).

**Role resolution (no ambiguity).** Exact mutated content is **either** a preregistered scenario-variant
identity (design-time) **or** run-level realization evidence (runtime, via Butterfly/environment identity) —
**never both.** A design-time mutation cannot be relabeled a runtime intervention, and a runtime mutation
cannot be relabeled an ordinary scenario variant (tests, §15).

## Section 6 — Mutation taxonomy (≥3 families)

**A. Candidate surface / representation mutations** (invariance is NOT assumed from the category): casing ·
whitespace · punctuation · line wrapping · Unicode normalization forms (NFC/NFD/NFKC/NFKD) · zero-width
insertion · homoglyph substitution · combining marks · directionality controls · equivalent encoding/decoding
representations. **Their semantic invariance is a *preregistered hypothesis* that must pass the applicable
`EquivalenceProfile` (§7)** for the specific claim — it is never assumed merely because the transform is a
"surface" one. **NFKC/NFKD, case operations, whitespace collapse, and deletion may be lossy** (§6 reversibility
class). *A behavior or validator change under a mutation whose required equivalence layers are **confirmed** is
potential robustness evidence; under an unconfirmed/lossy transform it is a semantic-change finding, not
robustness evidence.*

**B. Semantic-preserving mutations** (intended to preserve meaning; require **independent** verification):
rephrasing · translation · compression · expansion · metaphor · role-play wrapping · multilingual mixing ·
fragmentation across messages. *Never assume equivalence because a mutation model claims it preserved intent.*

**C. Adversarial security-validation mutations** (intentionally stress security boundaries, **authorized
defensive suite only**): invisible-content concealment · steganographic representations · confusable
characters · decoder-order differentials · normalization differentials · cross-message reconstruction · token
expansion · parser disagreement · fragmented intent · conflicting visible-vs-decoded content · nested
encodings.

**Reversibility class (audit-response — transforms are NOT all "exact reversible").** Each transform declares
a `reversibility_class`, because reversibility ≠ equivalence and several transforms are only conditionally or
lossily reversible: **byte-reversible** (invertible with no side data — e.g. URL-encode, Base64) **only
*conditional* on a frozen charset / encoding / error-handling / decoder profile; absent that frozen profile the
claim is classified at the `decoder-relative` or `reversible-with-witness` layer instead** ·
**reversible-with-witness** (invertible only if a position map / transformation log is preserved — e.g.
zero-width insertion, whitespace substitution, combining-mark noise, message fragmentation) ·
**Unicode-canonical-equivalent** (NFC/NFD round-trip within canonical equivalence) ·
**compatibility-normalized (potentially LOSSY)** (NFKC/NFKD, case folding, whitespace collapse, deletion — may
not round-trip) · **decoder-relative** (recoverable only under a registered decoder / interpretation pipeline)
· **human-intent-preserving** (homoglyph, directionality — may preserve perceived intent while changing the
byte/token representation) · **judge-dependent** (rephrase, translate, roleplay — equivalence requires the §7
gate). **Explicitly: NFKC/NFKD, case folding, whitespace collapse, and deletion may be lossy** and are never
labeled byte-reversible. The reversibility class binds into provenance and constrains which §7 equivalence
layers a transform can support.

## Section 7 — Semantic-equivalence lifecycle (layered — R1/R2)

**Layered equivalence (R1) — never one scalar.** A reversible encoding is not agent/validator equivalence
unless the *frozen* observation pipeline interprets it. Record separate, independently-authoritative layers,
each binding its **authority + evaluation method**: `byte_equivalence` · `unicode_normalization_equivalence` ·
`decoder_round_trip_equivalence` · `canonical_payload_equivalence` · `human_intent_equivalence` ·
`agent_visible_equivalence` · `policy_relevance_equivalence`. Rules: URL/Base64/cipher/steganography/nested
encodings are equivalent **only relative to a frozen decoder/interpretation pipeline**; a reversible transform
establishes *recoverability, not* semantic equivalence for the model/validator; zero-width/homoglyph/bidi/
combining-mark cases may preserve human-perceived intent while changing tokenizer- or model-visible
representation → report those layers separately; **a prompt-invariance claim requires the exact layer that
claim needs to be confirmed**; a **validator-bypass claim requires `canonical_payload_equivalence` AND
`policy_relevance_equivalence` under the frozen validation spec**; reports never collapse layers into one
scalar.

**Gate states (per layer where applicable):** `equivalent_confirmed` · `equivalent_with_uncertainty` ·
`semantic_change_detected` · `unresolved` · `invalid_transform` · `decoder_failure`. **Evidence sources:**
deterministic round-trip / canonicalization checks · rule-based equivalence for exact encodings · normalized-
text comparison · calibrated judge · human adjudication for disputed cases · disagreement + appeal handling. A
variant that changes semantics may remain useful as a **different scenario** but cannot support a
semantic-invariance claim. **Semantic failures are recorded in the permanent attempt ledger, never discarded
after seeing outcomes.**

**Timing & blindness (R2).** For primary invariance/bypass claims, the required equivalence assessment is
**frozen before** the acting-model / tested-validator outcome is revealed to the adjudicator, **or** the
adjudicator is **demonstrably blinded** to those outcomes. Record `equivalence_assessment_timepoint` ·
`equivalence_observation_boundary` · `equivalence_authority_id` · `equivalence_method_version` ·
`equivalence_appeal_status`. **Post-outcome relabeling is prohibited for the original claim**; a corrected
label creates a **new ledgered analysis/experiment** and never silently replaces the preregistered label.

**Versioned `EquivalenceProfile` (audit-response — the required layers are frozen, not selectable after
results).** A versioned `EquivalenceProfile`, frozen **before any outcome is observed**, binds: **claim type**
(e.g. prompt-invariance, validator-bypass, robustness) → **the required equivalence layers** for that claim ·
the **allowed gate states** per layer · the **authority / method / version** for each layer · **uncertainty
treatment** · **appeal procedure** · **veto behavior** (an unresolved or failed required layer **vetoes** the
claim). This removes the researcher degree of freedom of selecting the easiest layer after seeing results. The
mutation-study design / `AcceptanceProfile` **binds the `EquivalenceProfile` hash before execution**; a claim
is admissible only if every layer its profile requires reached an allowed gate state.

## Section 8 — P4RS3LT0NGV3 adapter boundary

Pinned commit **`a6cb7c9054800e106b63888d362601922477a614`** (branch `main`). The external app stays **outside
the trusted Coliseum runtime**: pinned separate checkout · subprocess or exported-vector boundary ·
content-addressed input/output · no shared secrets · no direct registry writes · no hidden-suite access · **no
live dependency fetching during reportable experiments.** Three integration modes:

1. **Offline deterministic subset (preferred initial mode)** — pinned external commit · **no runtime network ·
   no API keys** · only **audited** transforms · full transform + output provenance · **seeded paths PROVEN
   deterministic** before use.
2. **Local semantic mutation** — for confidential/hidden material use **governed local Ollama generation, NOT
   OpenRouter**; bind model name · digest · prompt template · temperature · sampler seed · generated content;
   generated semantic variants still pass the §7 equivalence gate.
3. **Isolated authorized adversarial mode** — Anti-Classifier / steganography / fragmentation / decoder
   differentials / token-expansion tests: **hard resource budgets · no production credentials · no arbitrary
   network access · no automatic tool invocation · no third-party targets · separate evidence root +
   authorization identity.**

**Confirmed external-tool facts (inspection, §throughout):** `randomMix`/Zalgo ignore the seeded RNG (bare
`Math.random`), and `fuzzUseRandomMix` is default-on → seeded batches are non-reproducible (see §9);
PromptCraft/AntiClassifier POST to `openrouter.ai` with API keys in plaintext `localStorage` (never used for
hidden/confidential content); Tokenade is a token-bomb (§11).

## Section 9 — Determinism contract (R4)

**`randomMix` is REFUSED until full determinism is demonstrated** — the external UI seed does **not** control
every transform (confirmed: `randomMix`/Zalgo use bare `Math.random`; empty default seed also falls back to
`Math.random`). Only **audited transforms with proven-deterministic seeded paths** are used; the external
commit is pinned in every record.

**Design-time generation vs execution determinism (R4).** A design-time mutation is generated **before manifest
freeze**, then its exact output is **frozen and hashed** (= the new `behavioral_hash`). **Reportable execution
consumes the frozen mutated content and never regenerates it live; behavioral replay verifies the frozen
variant and must NOT call P4RS3LT0NGV3 again** (consistent with the provider-refusing replay contract).
Generation determinism is still required for reproducible dataset construction: if a variant **cannot be
regenerated from its declared recipe**, its **generation-reproducibility gate fails**, the frozen output may
remain **descriptive evidence only**, and it **cannot support a claim requiring reproducible scenario
construction**.

## Section 10 — Licensing & supply-chain gate

The external tool declares **MIT in `package.json` but ships a full AGPL-3.0 `LICENSE`** — a direct,
**unresolved** contradiction (permissive vs strong network-copyleft). Therefore: **copying or vendoring source
is blocked; a networked modified deployment is blocked pending license review; generated test vectors may be
imported only with provenance + applicable-rights review; an external-process prototype does not resolve
licensing; independently reimplementing standard transformations must avoid copying protected expression.** The
scenario **licensing matrix** records the tool's LICENSE file(s) + the inspected commit `a6cb7c9…`. This is a
governance/distribution gate, not an engineering note.

## Section 11 — Security & resource controls

Required, enforced on every mutation batch: maximum input bytes · maximum output bytes · maximum token estimate
· maximum transform-chain depth · maximum expansion ratio · per-case time limit · per-batch case limit ·
Unicode normalization policy · control-character inventory · **bidi/invisible-character visualization in
reports** · decoder recursion limit · decompression/expansion limit · **HTML escaping** · **no shell
interpolation · no dynamic evaluation · no generated file paths · no automatic URL fetching · no automatic tool
execution** · isolated temporary storage · output content hashes · **kill switch for pathological cases.**
**Tokenade-class token-bomb / pathological-Unicode cases belong in a separate resource-exhaustion suite** with
their own hard budgets and **never share normal experiment budgets.** Every generated string is treated as
**untrusted data** — never executed or interpreted as code, path, shell command, template, HTML, or tool
instruction.

## Section 12 — Dataset partition & hidden-evaluation rules

- All mutations and derivatives **inherit the source scenario's `partition_group_id`**; source and derivative
  **cannot cross** training/development/validation/hidden boundaries.
- An **alternate encoding cannot acquire a new partition** by changing row identity.
- **Near-duplicate + derivative detection occurs before partition assignment** (dedup version + limits
  recorded; not assumed perfect).
- **Active or claim-supporting hidden cases never enter OpenRouter or any external mutation service**; hidden
  mutations are generated **only inside evaluator-controlled infrastructure**.
- The **trainer cannot see** hidden mutation specs, realized variants, or per-case outcomes.
- **Exposed mutation families and failed hidden attempts enter the permanent access ledger.**
- A hidden mutation suite becomes **spent under the same lifecycle as Butterfly B/C evidence** (any exposure —
  including aggregate — spends it; a reattempt needs a fresh committed suite; a spent suite is never relabeled
  fresh hidden evidence).
- **Future hidden suites exclude derivative and near-duplicate cases** per the contamination policy.

## Section 13 — Matched-mutation validator (R3)

For a canonical source unit vs one mutated unit, the validator proves: **control and mutation are intentionally
paired (`mutation_pair_id`)** · seed + effective-unit construction match · **only the registered mutation
dimension differs** · the scenario hashes **differ as expected** · the differing comparison regimes are
expected and compared via a **paired-delta** operation (reuse `control_twin_delta`) · control and mutation are
**never pooled into one cell** · **multiple mutated outputs cannot collide on one `mutation_pair_id`** · retries
never become new pairs or inflate effective-n · realized mutated content matches its registered recipe.
**Parser-only, validator-only, and model-behavior divergences remain distinguishable.**

## Section 14 — Measurement model

Per control/mutated pair, record and report **separately**: layered semantic-equivalence status (§7) · the
full **representation-pipeline stage hashes (§5)** (`raw_authored_artifact_hash` · `parsed_scenario_hash` ·
`rendered_agent_facing_hash` · `normalized_input_hash` · `decoded_payload_hash` · `validator_input_hash`) and
**the first stage at which control and mutated representations diverge, normalize together, fail, or
disappear** · `mutation_target_surface` (§5) · tokenizer + token-count delta ·
validator decision **before** normalization · validator decision **after** normalization · parser
success/failure · normalization recovery/failure · model-format compliance · reflex action · planner action ·
arbitration winner · final action · earliest divergence · refusal/compliance change · harmful or deceptive
compliance · critical violations · cross-seed stability · cross-model transfer · family-level mutation effect ·
invalid/missing handling. **Candidate metrics (subject to existing METRICS governance; METRICS-v2 dependencies,
NOT added to METRICS-v1):** validator-flip rate · false-accept rate · false-reject rate · parser-divergence
rate · normalization-recovery rate · semantic-preservation rate · action-flip rate · reflex-flip rate ·
planner-correction rate · earliest-divergence distribution · critical-violation rate · mutation-family spread ·
token-cost amplification · cross-model transfer matrix. New inferential statistics + uncertainty are METRICS-v2
dependencies.

## Section 15 — Narrow bypass definition

A **security bypass** requires **ALL** of: an **authorized target** · a **frozen** validator + normalization
stack · **semantically prohibited or policy-relevant content under a governed specification** · a mutated
representation **accepted where the canonical equivalent is rejected**, or otherwise reaching a prohibited
downstream state · **complete provenance** · **`canonical_payload_equivalence == equivalent_confirmed` AND
`policy_relevance_equivalence == equivalent_confirmed` (§7) — `equivalent_with_uncertainty` (or any weaker
state) is INSUFFICIENT and is reported as a candidate anomaly / unresolved test case, never a bypass** ·
**reproducibility across the preregistered effective units** · **no uncontrolled dimension change.**
**One successful string is a test case, not a general bypass finding.** **Benign false rejection is measured
separately from harmful false acceptance.**

## Section 16 — Combinatorial control

Do **not** generate all chains across hundreds of transforms. Require: **preregistered mutation packs** ·
bounded chain depth · fixed transformation order where possible · **pairwise / coverage-aware selection** ·
family quotas · token + expansion budgets · deterministic seeds · **baseline unmutated controls** · explicit
invalid-case policy · **no post-result mutation search against active hidden evaluation.** Any adaptive mutation
search (if ever allowed) receives **its own budget and spent-suite lifecycle.**

## Section 17 — Initial MVP mutation pack (~12)

Each transform carries its §6 `reversibility_class` (the pack is **not** a flat "exact-reversible" list):
- **byte-reversible (conditional on a frozen charset/encoding/error-handling/decoder profile; else
  decoder-relative):** 7 URL encoding · 8 Base64 representation.
- **reversible-with-witness** (needs a position map / transformation log): 2 whitespace substitution ·
  3 zero-width insertion · 6 combining-mark noise · 9 line/message fragmentation.
- **Unicode-canonical-equivalent:** 4a NFC/NFD normalization. **compatibility-normalized (potentially LOSSY):**
  4b NFKC/NFKD normalization · 1 case variation (case folding is lossy).
- **human-intent-preserving** (changes byte/token representation): 5 Greek/Cyrillic homoglyphs.
- **judge-dependent** (require the §7 gate): 10 governed semantic rephrasing · 11 governed multilingual
  translation · 12 role-play wrapping.

Byte-reversible and Unicode-canonical-equivalent transforms are separated from reversible-with-witness, lossy,
human-intent, and judge-dependent ones in identity and reporting; **no transform is asserted equivalent beyond
the §7 layer its reversibility class actually supports.** **The MVP uses PUBLIC development scenarios + LOCAL
validators only — no active hidden cases, no external targets, no Anti-Classifier, no Tokenade.**

## Section 18 — Scenario-architecture integration point

Reuse existing scenario identity + registry (§2/§5) rather than replacing or silently modifying scenario-pack
authority. Design-time mutations register as scenario/variant revisions under the existing lint (revision-bound
identity, ≥2 variants, twin symmetry, family ∈ the eight — a robustness tag/family is a **SPEC change,
proposed not authorized**). The track sits at the **M3/M4/M8–M10** dependency point (registry + held-out +
scenario batches + parser-stability + wording comparisons); the security-validation suite is a separate
defensive line. It **does not delay the Butterfly MVP** and may support the training-annex §28 sensitivity
atlas only after its own bounded approval.

## Section 19 — Tests

**Identity & determinism:** same source/spec/params/seed → identical frozen variant · transform order changes
identity · parameter change changes identity · **external commit change changes identity** · mutated-content
mismatch rejects the case · seeded mode rejects any unseeded transform path · **`randomMix` refused until full
determinism demonstrated** · design-time mutation cannot be relabeled runtime intervention · runtime mutation
cannot be relabeled ordinary scenario variant · **a `model_output`/`parser_input`/`validator_input` surface
mutation cannot use scenario identity as though the scenario changed (§5)** · **multiple mutated outputs cannot
collide on one `mutation_pair_id`/`mutation_case_id`; `mutation_attempt_id` binds `execution_instance_id`;
retries keep case/pair/effective-unit, new attempt** · **`mutation_use`/`mutation_target_surface` do not change
`behavioral_hash`; historical hashes preserved.**
**Reversibility & pipeline:** a lossy transform (NFKC/NFKD, case fold, whitespace collapse, deletion) is never
labeled byte-reversible · a transform cannot claim a §7 layer its reversibility class does not support · the
representation-pipeline stage hashes localize the first divergent stage · a missing *required* stage hash
rejects the case · line-ending / Unicode-normalization / invisible-char / YAML-JSON-parse / prompt-render /
decoder-order / validator-input tests exercise each stage.
**EquivalenceProfile:** a claim is admissible only if every layer its frozen `EquivalenceProfile` requires
reached an allowed gate state · an unresolved/failed required layer vetoes the claim · the profile hash is
bound before execution.
**Recipe / profile / pair / bypass (C1–C4):** the `generation_recipe` is **sufficient to regenerate** the
frozen artifact (a recipe that cannot reproduce it fails the generation-reproducibility gate) · two generation
recipes that differ in mode / model digest / prompt-template / temperature / seed produce **different**
`scenario_mutation_spec_hash` even when they emit identical content · a stage labeled non-applicable **after**
observation (not in the frozen `RepresentationPipelineProfile`) is rejected · `mutation_pair_id` binds **both**
replicate keys; a cross-seed, cross-variant, or control-unit substitution is rejected by identity · a security
bypass is refused unless **both** `canonical_payload_equivalence` and `policy_relevance_equivalence` are
`equivalent_confirmed` (uncertainty → candidate anomaly, not a bypass).
**Semantic equivalence (R1/R2):** reversible-transform round-trip · normalization-equivalent pair ·
semantic-change detection · judge/human disagreement · unresolved cases cannot support invariance claims ·
decoder failure remains ledgered · **post-outcome relabeling rejected** · a layer required by a claim is
confirmed before that claim.
**Partitioning:** derivatives inherit source partition group · alternate encoding cannot cross splits · **hidden
mutation never calls external services** · exposed hidden mutation suite becomes spent · near-duplicate
derivative excluded from a fresh hidden suite.
**Security:** control/bidi characters visible in reports · output HTML-escaped · **generated strings never
execute** · chain-depth + expansion limits · token-budget limit · decoder-recursion limit · timeout + kill
switch · no arbitrary network · no API key in generated evidence · no tool invocation from mutated text.
**Measurement (R3):** canonical/mutated pairs share held-constant identities · exactly the registered mutation
dimension differs · parser-only / validator-only / model-behavior divergences distinguishable · invalid cases
don't inflate effective-n · retries collapse · **one successful string cannot produce a family-level claim** ·
critical violations veto aggregate success · cross-source / cross-variant / cross-mutation substitution rejected
· mutated-output mismatch rejected.

## Section 20 — Threat model

External tool untrusted (offensive framing; jailbreak/filter-evasion generators; token-bomb) · non-deterministic
"seeded" batches (randomMix) · confidential/hidden content exfiltration to OpenRouter · API-key leakage
(plaintext localStorage) · MIT/AGPL license contradiction · resource exhaustion (Tokenade) · untrusted content
executed/interpreted (invisible/bidi/homoglyph/nested-encoding) · reversible-≠-semantic conflation · one-string
overgeneralization · design-time↔runtime↔security category confusion · hidden-suite erosion · post-outcome
equivalence relabeling · scenario-family sprawl (SPEC lock).

## Section 21 — Council route

A **separate council request** at its own owner SC gate (KTK/Butterfly source-request precedent), sequenced at
the M3/M4/M8–M10 scenario dependency point, then per-step bounded implementation requests (identity/provenance
overlay → offline deterministic adapter → equivalence gate → matched-mutation validator → measurement → MVP
pack → security suite). METRICS-v2 metrics separately governed. **No approval of the training annex or Butterfly
authorizes this track.**

## Section 22 — Publication claim language

Permitted (with evidence): "under a frozen validation stack, transform family X flipped validator decision Y at
rate Z with confirmed canonical-payload equivalence." Prohibited: reporting a reversible representation change
as semantic equivalence · collapsing the seven equivalence layers into one scalar · presenting one successful
mutated string as a general bypass · any claim of a real-world security guarantee · any causal claim beyond the
evidence · any reliability claim with uncertainty before governed METRICS-v2 · any claim an artificial result
predicts human/third-party-system behavior.

## Section 23 — Unresolved owner decisions

1. (schema decision) Where `mutation_use` / `mutation_target_surface` live — a separate provenance record
   (default; not in `behavioral_hash`) vs a version-dispatched hashed field (preserving historical hashes).
1b. (separate SPEC decision) Whether a robustness scenario *family* is ever needed (eight-family lock) — **not**
   required merely to record mutation provenance.
2. Semantic-equivalence **authority** per layer (rule engine / calibrated judge / human panel) + calibration +
   appeal procedure.
3. Whether security-validation evidence lives in a fully separate evidence root / repository boundary.
4. External-tool posture: pinned-checkout subprocess vs independent reimplementation of standard transforms
   (pending the licensing review).
5. Timing vs the Butterfly MVP and the training-annex sensitivity atlas (§28 there).
6. METRICS-v2 governance for the candidate mutation metrics.

## Section 24 — Correction / addition ledger

| Addition | Section | Status |
|---|---|---|
| Identity reuse (scenario_id + behavioral_hash + variant_id; no new triad) + provenance overlay | §5 | newly proposed |
| Three uses (design-time / runtime / security-validation), machine-resolvable, no pooling | §4 | newly proposed |
| Mutation taxonomy A/B/C | §6 | newly proposed |
| Layered equivalence (7 layers), never one scalar (R1) | §7 | newly proposed |
| Blinded / frozen-before-outcome equivalence adjudication, no relabel (R2) | §7 | newly proposed |
| Exact mutation-pair lineage `mutation_pair_id`/`mutation_attempt_id` (R3) + matched-mutation validator | §5, §13 | newly proposed |
| Design-time generate-then-freeze; replay never re-calls the tool; generation-reproducibility gate (R4) | §9 | newly proposed |
| P4RS3LT0NGV3 adapter (3 modes), pinned commit `a6cb7c9…`, outside trusted runtime | §8 | newly proposed |
| Determinism contract (`randomMix` refused) | §9 | newly proposed |
| Licensing & supply-chain gate (MIT/AGPL unresolved → no copy/vendor) | §10 | governance gate |
| Security & resource controls; Tokenade-class isolated | §11 | newly proposed |
| Partition inheritance + hidden-suite lifecycle (never external; spent like B/C) | §12 | newly proposed |
| Measurement model + METRICS-v2-dependent candidate metrics | §14 | newly proposed |
| Narrow bypass definition (one string = test case) | §15 | newly proposed |
| Combinatorial control (packs, coverage, budgets, no post-result search vs hidden) | §16 | newly proposed |
| MVP pack (12; public + local only) | §17 | newly proposed |
| Test / threat / route / publication / unresolved | §19–§23 | newly proposed |
| **Audit-response — reversibility class** (byte-reversible / with-witness / canonical-equivalent / lossy-normalized / decoder-relative / human-intent / judge-dependent; NFKC/NFKD/case/whitespace/deletion may be lossy) | §6, §17 | corrected (HIGH) |
| **Audit-response — `mutation_target_surface`** enum bound into provenance + pair validation; model-output/parser/validator surfaces are security-validation vectors, not scenario variants | §5, §13 | corrected (HIGH) |
| **Audit-response — representation-pipeline identity** (raw/parsed/rendered/normalized/decoded/validator-input hashes; localize first divergent stage; missing required stage rejects) | §5, §14, §19 | corrected (HIGH) |
| **Audit-response — `mutation_use` schema authority ≠ scenario-family SPEC authority** (provenance field, not `behavioral_hash`; version-dispatched; historical preserved; no family needed for provenance) | §4, §5, §23 | corrected (HIGH) |
| **Audit-response — mutation lineage defined** (`source_evaluation_unit_id`/`mutation_case_id`/`mutation_pair_id`/`mutation_attempt_id` semantics; attempt binds `execution_instance_id`; collision + cross-substitution tests) | §5, §19 | corrected (MED) |
| **Audit-response — versioned `EquivalenceProfile`** (frozen before outcomes: claim→required layers, gate states, authority/method/version, uncertainty, appeal, veto; AcceptanceProfile binds its hash) | §7 | corrected (MED) |
| **Precision pass — Family A requalified** "candidate surface/representation mutations"; invariance is a preregistered hypothesis via `EquivalenceProfile`; NFKC/NFKD/case/deletion may be lossy | §6 | corrected |
| **Precision pass — exact payload definitions** for `scenario_mutation_spec_hash` / `mutation_case_id` / `mutation_attempt_id` (canonical, domain-separated, schema-versioned; required fields reject; attempt binds `execution_instance_id` non-circularly) | §5 | corrected |
| **Precision pass — URL/Base64 byte-reversibility conditional** on a frozen charset/encoding/error-handling/decoder profile (else decoder-relative / witness-dependent) | §6, §17 | corrected |
| **C1** — `scenario_mutation_spec_hash` binds a `generation_recipe` discriminated union (mode/generator identity/config-hash/seed/RNG alg+version+stream); sufficient to regenerate; local-semantic binds model digest+prompt-template+temperature+sampler+seed | §5, §19 | corrected (HIGH) |
| **C2** — exact `mutation_pair_id` formula binding **both** evaluation units (source + mutated replicate keys, both variant ids/hashes, held-constant/changed-dimension/equivalence-profile hashes); cross-unit substitution blocked by identity | §5, §13, §19 | corrected (HIGH) |
| **C3** — versioned `RepresentationPipelineProfile` frozen before observation (ordered stages, per-stage impl/version, required-vs-non-applicable authority, canonicalization, failure behavior; hash bound into spec + design) | §5, §19 | corrected (MED) |
| **C4** — a security bypass requires BOTH `canonical_payload_equivalence` and `policy_relevance_equivalence` == `equivalent_confirmed`; uncertainty → candidate anomaly, never a bypass | §15, §19 | corrected (MED) |

---

*Grounded in `coliseum/textlab/{schema,scenario,registry,agents,metrics,sweep}.py`
(`schema.py:304-320`, `scenario.py:21-34,137-193`, `registry.py:198-216`, `metrics.py:212-279`,
`agents.py:323-364`), `docs/first-gladiator/{ROADMAP.md,BUTTERFLY-ALIGNMENT-TRACK.md}`, and the read-only
inspection of `elder-plinius/P4RS3LT0NGV3` at commit `a6cb7c9054800e106b63888d362601922477a614`. No P4RS3LT0NGV3
source copied/vendored; no dependencies installed; no OpenRouter/external API called; no hidden/confidential
data left the local boundary. Coliseum repo unmodified at `0bf83bc5`. Separately governed; nothing implemented,
committed, routed, registered, trained, or published.*

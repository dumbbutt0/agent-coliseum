# Spatial S2C — Perception rendering + non-interference (design source, rev 3)

Status: council-routed design source for the third perception-track slice (S2C), per the
owner's binding perception-track directive (2026-07-13) and the master runnable-experiments
directive (R3). Consumes the integrated S2A contract (`SPATIAL-S2A-MUTABLE-LOCATION-STATE.md`,
rev 6) and the integrated S2B contract (`SPATIAL-S2B-DETERMINISTIC-SCHEDULER.md`, rev 11), and
the integrated training-readiness observation authority (`coliseum/textlab/training/observation.py`,
TRS Appendix A). This slice is INERT: pure rendering functions + reuse of existing record
domains. No runner, no live agent, no belief/memory store, no society surface.

## 1. Purpose and boundary

Perception is the deterministic subset of world truth available to a particular observing
agent body at a particular logical step (profile §2/§10). S2C defines the **perception
renderer**: a pure function of `(authenticated world state, observer body, authenticated
topology closure, perception regime, schema + renderer versions)` that emits the canonical
per-view `ObservationArtifact` pair — the **actor** view (the projection an agent may later
consume) and the **privileged** view (world truth for analysis). A future agent loop consumes
ONLY the actor projection, never the authoritative state.

In scope: the visibility policy v0 (room-scoped), the canonical observation content shape,
the actor/privileged construction paths, the non-interference invariants, and the adversarial
test classes. Out of scope (deferred): persistent beliefs/memory, audibility (adjacent-room
hearing is OFF in v0), per-body regime overrides, portal mutable state, container open/close
state, reveal conditions, multi-room lines of sight, S2D runner/CLI.

## 2. Records and identities (REUSE ONLY — no new observation domain)

S2C introduces **zero new observation record domains**. Both views use the single canonical
TRS Appendix A shape via the integrated factory `observation_artifact(view_kind, content)`:

- `trs.observation.actor.v1` / `trs.observation.privileged.v1` —
  `{schema_version, view_kind, content}`, self-excluded, `view_kind` inside the literal
  domain so the actor and privileged artifacts of the same emission can never alias.
- For a spatial producer, `content` is the canonical 7-key dict (profile §10):
  `{observer_identity, world_line_id, logical_step, perception_regime,
  visible_room_identity, visible_entity_identities, observable_state_projection}`.
  Both views use the SAME 7-key shape; only the populated payload differs (§4, §5).
- `RENDERER_VERSION = "0.1"` (frozen constant in `spatial/perception.py`) with a
  fail-closed `SUPPORTED_RENDERER_VERSIONS` dispatch: a `PerceptionRegime` whose
  `renderer_version` is not supported is REFUSED (never silently approximated).
  Renaming/removing/retyping any content field bumps `RENDERER_VERSION`.

Privileged carriers registered: the spatial privileged view introduces the field names
`authoritative_placements`, `authoritative_lifecycle`, and
`closure_visible_state_commitment` inside its `observable_state_projection`. These names
are ADDED to `observation.PRIVILEGED_FIELD_NAMES` (an additive, backstop-strengthening
edit: it only widens what `assert_no_privileged_leak` refuses in ACTOR content; no existing
actor content uses these names). No other edit to the integrated training module is
permitted.

**Two frozen per-view inner schemas for `observable_state_projection`.** The 7 outer
content keys are frozen for both views; the inner `observable_state_projection` schema is
per-view, each frozen under `RENDERER_VERSION` (adding/renaming/removing ANY inner key in
either view bumps the version):

*ACTOR inner schema* — a dict with EXACTLY two keys:

- `"entities"` — a list of `{entity_id, entity_kind, location}` rows (exactly those three
  keys per row), sorted by `entity_id`, one row per §4-visible entity.
- `"portals"` — a list of `{portal_instance_id, to_room_instance_id}` rows (exactly those
  two keys per row), sorted by `(portal_instance_id, to_room_instance_id)`: the closure
  attachment rows departing the observer's current room (§4). Empty (`[]`) for an
  in-transit observer and whenever the observer's room has no departing attachment rows.
  Portals are topology, not entities — they never appear in `"entities"`.

*PRIVILEGED inner schema* — a dict with EXACTLY three keys:
`{"authoritative_placements", "authoritative_lifecycle", "closure_visible_state_commitment"}`
(§5). The privileged view does NOT use the actor two-key container; each view has exactly
one inner schema and they share no keys.

**Closed exact actor-schema validation (the leak-enforcement mechanism).** The
implementation MUST provide and call an exact actor-content validator at the actor
construction path: the actor `content` must have EXACTLY the 7 outer keys; its
`observable_state_projection` EXACTLY the actor two-key container; every `"entities"` row
EXACTLY `{entity_id, entity_kind, location}` with `location` an exact S2A tagged shape
permitted by §4; every `"portals"` row EXACTLY `{portal_instance_id, to_room_instance_id}`.
ANY additional or unknown key at ANY depth is REFUSED (`ContentRecordError`). This
closed-schema rule — not name enumeration — is what excludes every smuggled carrier
(world-state/transition/manifest/cursor hashes under any field name whatsoever). The
generic `assert_no_privileged_leak` name backstop remains as defense-in-depth, and the
three privileged inner-schema keys are registered names, but the semantic guarantee is
carried by the closed schema.

Insertion order, registry order, and host/dict order never affect any list; the canonical
byte content of both views (and hence both observation ids) is pinned by the sort rules
for directed AND bidirectional closures alike.

## 3. Renderer inputs, authentication posture, and refusals

`render_observation_pair(state, observer_body_id, closure, registry)` — pure; NO registry
registration, NO state mutation, NO randomness, NO wall-clock.

Trust posture mirrors S2B's turn engine: the CLOSURE argument is the authenticated closure
produced at the run boundary (`_authenticate_run` / `validate_world_line_genesis`); the
renderer does not re-authenticate the genesis (that would force materialization side
effects), but it MUST fail closed on every locally checkable inconsistency:

1. `observer_body_id ∈ closure["bodies"]` — an out-of-closure observer is REFUSED
   (perception is a closure capability, not a registry capability).
2. The observer's registered instance `world_line_id` equals `state.world_line_id`
   (cross-world refusal), and the state is a registered `spatial.world_state.v1`.
3. **Render-time admission revalidation (MANDATORY)**: the renderer calls
   `admit_world_state(state, registry)` at entry. Registration does NOT persist admission
   status (`SpatialSpecRegistry.register` never runs S2A admission), so a merely-registered
   but registry-invalid state — including one with malformed cross-world references
   anywhere in its placements — MUST be refused here. `admit_world_state` is pure and
   locally checkable (unlike genesis materialization), so this preserves render purity.
4. The observer's lifecycle status in `state` is `present` and it has exactly one placement
   (S2A admission guarantees this; the renderer re-checks presence and refuses otherwise).
5. **Complete fail-closed regime dispatch**: the integrated `PerceptionRegime` accepts
   arbitrary non-empty strings for every policy field, so version dispatch MUST bind every
   field. v0 supports EXACTLY one regime value tuple:
   `renderer_version ∈ SUPPORTED_RENDERER_VERSIONS = ("0.1",)`,
   `visibility_policy ∈ ("room_v0",)`, `audibility_policy ∈ ("off_v0",)`,
   `observation_policy_version ∈ ("1",)`, and a supported `spatial_schema_version`.
   Each field is checked INDEPENDENTLY; any non-conforming value refuses rendering
   (`ContentRecordError`) — a regime is never silently approximated as v0, and the regime
   id is therefore never semantically misleading. Unknown `visibility_behavior` values on
   any object spec encountered during rendering are likewise REFUSED (fail closed, never
   "assume hidden" or "assume visible").

Regime resolution v0: the observer body's `AgentBodySpec.default_perception_regime_id`
(per-body overrides deferred; the regime instance must be registered).

## 4. Visibility policy v0 (normative; the actor projection)

All rendering operates on the **closure-visible restriction** of the state (S2B
`_closure_visible`): placements + lifecycle filtered to `closure["bodies"] ∪
closure["objects"]`. This is the S2B lesson made structural: an admitted same-world
instance OUTSIDE the authenticated closure is perception-invisible in BOTH views and can
never change any observation id.

Observer placed `in_room` R:

- `visible_room_identity` = R (the room instance id; topology identities are spec-level
  knowledge and carry no location information about other entities).
- **Bodies**: every present closure body placed `in_room` R (including the observer itself).
- **Objects**: every present closure object placed `in_room` R whose spec
  `visibility_behavior == "visible"`; every object `held_by` a body that is itself visible
  (co-located), again only if `visibility_behavior == "visible"`. Objects with
  `visibility_behavior == "hidden"` are EXCLUDED (no reveal conditions in v0).
- **Container contents**: objects placed `inside` a container are NEVER visible in v0
  (no open/close state exists yet) — this is the private-object mechanism the S2D scenario
  `spatial_two_agent_private_object_v1` relies on. The observer does NOT see its own held
  containers' contents either (uniform rule; revisit with container state, versioned).
- **Portals**: every closure attachment row with `from_room_instance_id == R`, projected as
  `{portal_instance_id, to_room_instance_id}` into the `"portals"` list of the §2 container
  (matching S2B legal-move orientation: a directed portal's reverse row does not exist and
  is not shown; a bidirectional portal contributes exactly the rows departing R). No
  mutable portal state exists in v0.
- **Nothing else**: no entity in any other room, in transit, or inside any container; no
  counts, no hashes, no lifecycle records of non-visible entities, no negative facts
  ("X is absent" is not represented).

Observer placed `in_transit`: `visible_room_identity = null`; visible entities = the
observer itself + objects it holds (its inventory travels with it, same visibility rule);
the `"entities"` rows include the observer's own full transit descriptor (an agent always
perceives its own placement exactly) and its held objects; `"portals"` is `[]`. No room,
portal, or other-entity visibility.

`visible_entity_identities` is the SORTED list of visible entity instance ids.
`observable_state_projection` uses the §2 ACTOR two-key container: its `"entities"` rows are
`{entity_id, entity_kind, location}` where `location` is the S2A tagged location as visible
to the observer: `in_room` rows verbatim; `held_by` rows verbatim (the holder is visible by
construction); the observer's own placement verbatim (including `in_transit`). No other
location tags can appear in an actor projection in v0. Its `"portals"` rows are the §2
portal projection.

The actor content is **positively constructed** from this policy — visible facts are added
one by one. It is NEVER derived from privileged content by deleting known-secret fields
(copy-minus-secrets is forbidden), and `observation_artifact("actor", ...)` re-runs
`assert_no_privileged_leak` as the structural backstop.

## 5. The privileged view (world truth, same shape)

Same 7-key content shape. `visible_room_identity` = the observer's room (or `null` in
transit); `visible_entity_identities` = ALL closure entities present in the state (sorted);
`observable_state_projection` = `{authoritative_placements, authoritative_lifecycle,
closure_visible_state_commitment}` — the closure-visible placements and lifecycle verbatim
plus the **closure-projected state commitment**:

> `closure_visible_state_commitment` = the `spatial.world_state.v1` content id of the
> canonically CONSTRUCTED WorldState over the closure-visible restriction — same
> `world_line_id` and `logical_step`, placements + lifecycle filtered to
> `closure["bodies"] ∪ closure["objects"]` in their S2A-canonical order. It is a DERIVED
> commitment computed via content addressing only — the projected state is NOT registered
> (render purity) and the commitment does NOT assert that a state with this id is on any
> chain. For every canonical chain state (where `_closure_visible` is the identity) it
> EQUALS the registered state id; for a state carrying admitted out-of-closure content it
> commits to the closure-visible truth only, so an out-of-closure addition changes
> NEITHER view's observation id — this is what makes invariant 5 hold for BOTH views,
> which the registered full-state id could never satisfy (it content-addresses every
> placement by construction).

This three-key dict is EXACTLY the §2 privileged inner schema (the actor two-key container
never appears in a privileged projection and vice versa). The privileged artifact is the
analysis-side ground truth for leak-differential testing and later matched-twin comparison.
The three carrier field names are registered privileged names (§2), so their appearance in
ANY actor content fails closed — and the §2 closed actor schema refuses them (and every
other unknown key) structurally. MANDATORY regression: pin the COMPLETE privileged content
and observation id for a directed and a bidirectional closure case — closure placements,
lifecycle, and the closure-projected commitment — so only this exact inner schema can pass.

## 6. Non-interference invariants (the heart of S2C; all adversarially tested)

1. **Render purity**: rendering registers nothing, mutates nothing, draws nothing. A
   scheduler run with observation renders interleaved after every consume produces a
   byte-identical `SchedulerManifest` (and identical chain state ids) to the same run
   without any rendering. Perception is evidence ABOUT the run, never an input TO it.
2. **Hidden non-interference**: two admitted states differing ONLY in privileged-invisible
   content (a hidden object's placement; contents of a container; any entity in another
   room) render BYTE-IDENTICAL actor artifacts (equal `observation_id`s) for an observer
   whose visible scope excludes that content. The actor id is a function of visible facts
   only.
3. **View non-escalation**: the actor id is recomputable with privileged data physically
   absent; mutating any privileged-only field changes the privileged id but NEVER the actor
   id; the actor and privileged ids of one emission can never be equal (domain-separated).
4. **No hash smuggling**: no commitment to privileged truth (world-state hash, transition
   hash, manifest/cursor hash) may appear in actor content — a full-state hash inside an
   actor observation would bind hidden content into the actor id and silently violate (2).
   Actor content references only: instance identities visible under §4, the room identity,
   the logical step, the regime id. ENFORCEMENT: the §2 closed exact actor-schema
   validator (any unknown key at any depth refused — carrier-name-independent), with the
   registered privileged names as defense-in-depth. MANDATORY regression: each forbidden
   carrier (e.g. a field carrying a state/transition/manifest/cursor commitment) injected
   at MULTIPLE actor-content depths must raise `ContentRecordError` at the validator
   boundary, and a valid actor artifact must be pinned to show visible identities remain
   allowed.
5. **Closure-visibility**: an admitted same-world instance outside the authenticated
   closure changes NEITHER view's artifact id — in the observer's room, holding objects, or
   in transit (every enumeration in §4/§5 ranges over the closure-visible restriction, and
   the privileged commitment is the §5 closure-projected commitment, never the registered
   full-state id, which would re-import out-of-closure content into the privileged id).
   MANDATORY regression: two admitted same-world states differing ONLY by an
   out-of-closure entity must yield EXACTLY the closure-only state's actor id AND
   privileged id (exact-id assertions for both views, not merely "unchanged").
6. **Observer-boundedness (differential)**: for observers A and B in different rooms, a
   change visible only to B never changes A's actor artifact.
7. **Determinism/replay**: same (state id, observer, closure, regime, versions) across
   independent registries and insertion orders ⇒ byte-identical artifact ids. No host
   ordering, dict order, or registration order enters any observation preimage.

## 7. Non-goals / deferred

Beliefs/memory/relationship state; audibility + adjacent-room hearing; reveal conditions
and searchable containers; portal mutable state + perception through portals; per-body
regime overrides; observation streaming into run-dir traces (S2D emits the artifacts into
evidence; S2C only defines + returns them); any LLM/live-agent consumption; any change to
frozen METRICS-v1, run-record schemas, or `tools/council/`.

## 8. Threat model + required adversarial vectors

| # | Vector | Required refusal / invariant |
|---|--------|------------------------------|
| 1 | Privileged field name at any depth in actor content | `ContentRecordError` (backstop) |
| 2 | Actor derived by copy-minus-secrets | forbidden path; positive construction only (review + leak differential) |
| 3 | Hidden object moved/added/removed outside visible scope | actor id UNCHANGED (invariant 2) |
| 4 | Container contents change | non-holder AND holder actor ids unchanged in v0 |
| 5 | Other-room entity relocated | observer's actor id unchanged (invariant 6) |
| 6 | Any privileged-truth commitment in actor content, under ANY field name, at ANY depth | refused by the §2 closed exact actor-schema validator (unknown key ⇒ `ContentRecordError`); multi-depth regressions + pinned valid artifact (invariant 4) |
| 7 | Out-of-closure observer | refused (§3.1) |
| 8 | Out-of-closure same-world instance co-located with observer | BOTH view ids EXACTLY equal the closure-only ids (invariant 5 mandatory regression) |
| 9 | Cross-world observer/state or unregistered state | refused (§3.2) |
| 10 | Absent/removed observer, or observer without placement | refused (§3.4) |
| 11 | Unsupported `renderer_version` / non-conforming `visibility_policy`, `audibility_policy`, or `observation_policy_version` (each mutated INDEPENDENTLY) / unknown `visibility_behavior` | refused fail-closed (§3.5); per-field regressions |
| 12 | Render-time registration or mutation side effect | render purity differential (invariant 1) |
| 13 | Registry insertion-order / host-order dependence | byte-identical ids across registries (invariant 7) |
| 14 | Actor/privileged id aliasing | impossible by domain separation; asserted |
| 15 | In-transit observer sees room content | refused by policy (§4); regression |
| 16 | Registered but NON-ADMITTED state (structurally valid, registry-invalid) | refused by mandatory render-time `admit_world_state` (§3.3) |
| 17 | Portal projection ambiguity / ordering drift | pinned actor content + observation ids for a directed AND a bidirectional closure, incl. attachment insertion-order permutations (§2 container sort rules) |
| 18 | Privileged inner-schema drift (wrong keys / actor container in privileged view / extra keys) | pinned COMPLETE privileged content + observation id (§5 mandatory regression); per-view inner schemas share no keys |

Audit probes follow the owner's audit probe-reroute policy: committed regressions,
malformed-fixture negative tests, invariant + replay differentials, abstract adversarial
descriptions — acceptance criteria unchanged.

## 9. Compatibility

Additive only: new `coliseum/textlab/spatial/perception.py` + tests + additive
`spatial/__init__.py` exports + the §2 additive extension of `PRIVILEGED_FIELD_NAMES`.
No S0/S1/S2A/S2B record or contract mutation; no scheduler behavior change; no new
council event types; historical evidence untouched. The renderer consumes registered
S2A states and S2B closures as-is. Version dispatch is fail-closed everywhere
(`SPATIAL_SCHEMA_VERSION`, `RENDERER_VERSION`, `OBSERVATION_SCHEMA_VERSION`); legacy
records are never reinterpreted.

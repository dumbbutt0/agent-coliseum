# Agent Coliseum visualization architecture — source 001, revision 1

Status: **design source; not implemented; not integrated**. This document is the
architecture contract for `first-gladiator-visualization-architecture-001`.
It is based on code commit
`fe35d943ef7599e7b6aca2dcb46951f92053ed29`, after the result-handoff claim
ceiling was integrated. The visualization is an additive, read-only workstream.

## 1. Decision

Build the first viewer as a loopback Python service with browser-native HTML,
CSS, JavaScript, and SVG. It consumes existing spatial evidence through a new
strict loader and emits purpose-built, perspective-safe view models. The browser
never reads a run directory, raw JSONL, the council tree, or a simulation object.

The architecture is:

```text
allowlisted run root
  -> path and file-size boundary
  -> canonical evidence validation
  -> optional provider-free byte replay
  -> perspective projection (privileged OR one actor)
  -> immutable replay index
  -> derived presentation model
  -> JSON API
  -> SVG renderer, timeline, inspector, and controls
```

The simulation remains authoritative. The viewer does not schedule, infer,
transition, correct, admit, approve, or write experiment evidence.

The first runtime theme is a neutral geometric research view. The original Roman
tactical-diorama theme is a later, separately audited presentation source. SVG is
the runtime asset format. Blender, if later justified, is offline and optional.

## 2. Reconnaissance findings

### 2.1 Existing executable surfaces

- `coliseum/textlab/cli.py` exposes `spatial-run`, `spatial-replay`, and
  `spatial-inspect`.
- `coliseum/textlab/spatial/run.py:execute_spatial_run` writes schema-0.2
  control evidence and schema-0.3 treatment evidence.
- `coliseum/textlab/spatial/run.py:replay_spatial_run` regenerates a run without
  a provider and byte-compares the six spatial evidence files.
- `coliseum/textlab/spatial/run.py:inspect_spatial_run` selects actor or
  privileged observation content for terminal inspection. It is not a web
  security boundary and does not validate a complete replay view model.
- `coliseum/textlab/training/spatial_trajectory_projection.py` strictly consumes
  schema 0.2/0.3 and binds hashes for all six spatial evidence files. It is a
  training-record projector, not a visualizer.
- `coliseum/textlab/society/run.py:actor_safe_report` and
  `privileged_report` are society-specific report projections. They are useful
  evidence of the split-view pattern but are not a generic spatial API.
- `scripts/dashboard.py` emits a derived Markdown program dashboard. There is no
  current browser frontend, HTTP server, JavaScript package, database, or game
  engine.

The repository's runtime dependencies are Python, PyYAML, and NumPy; a standard
library service avoids adding a mandatory web framework for this slice.

### 2.2 Canonical spatial evidence available now

The required spatial evidence set is:

| File | Authoritative facts usable by the viewer |
|---|---|
| `run.json` | run/scenario/seed identities, versions, world-line and genesis identities, manifest identity, chain bounds, observers, logical instance mapping |
| `chain.jsonl` | ordered scheduler positions, scheduler-state identities, world-state identities, logical round position, outcome and transition reference |
| `transitions.jsonl` | applied effect, acting body, prior/result state identities, transition identity |
| `observations.jsonl` | actor and privileged observation artifacts for every observer at every position |
| `activations.jsonl` | full candidate universe, activation, selected effect/action, applied transition reference |
| `closure.json` | authenticated room, body, object, and directed portal-attachment identity sets |

The evidence records logical topology and state, not screen geometry. There are
no canonical x/y coordinates, continuous cells, terrain, mutable portal state,
room restrictions, ownership, institution geometry, schedules, relationship
graphs, or memory ledgers in the spatial 0.2/0.3 format.

Current state supports rooms, directed portal attachments, bodies, objects, and
the canonical location tags `in_room`, `held_by`, `inside`, and `in_transit`.
Those are enough for a useful room-and-portal replay. Decorative terrain and
architecture are not simulation facts.

### 2.3 The raw observation file is privileged

Every raw `observations.jsonl` row co-locates `actor_content` and
`privileged_content`. Therefore:

- a static site must not load that file for an actor view;
- the service must positively construct the actor response before delivery;
- a client-side visibility toggle is forbidden;
- caches must be keyed by perspective and actor and must never reuse a
  privileged value in an actor response;
- raw-file endpoints and generic static serving of the run root are forbidden.

The integrated perception contract in
`docs/first-gladiator/SPATIAL-S2C-PERCEPTION-NON-INTERFERENCE.md` makes actor
artifacts safe by positive construction and exact-schema validation. The viewer
must preserve that artifact as its trust boundary rather than re-filtering a
privileged projection.

### 2.4 Provenance layers are independent

A spatial manifest/replay success authenticates deterministic execution. It does
not prove result approval, scientific claim acceptance, training admission, or
license permission. Conversely, a syntactically valid run may be incomplete or
diagnostic and still be useful to inspect.

The live-persona pack currently demonstrates this distinction: its spatial chain
is replayable, while `live_report.json` records the exact result ceiling
`complete: false`, `behavioral_departure_claimable: false`, and
`status: "incomplete"`. The run directory does not itself carry a universal
council approval or correction-lineage record.

The viewer must expose separate typed fields:

| Field | Values | Authority |
|---|---|---|
| artifact validation | `valid`, `refused` | visualization loader |
| replay verification | `verified`, `unverified`, `failed` | provider-free replay result |
| completion | `complete`, `incomplete`, `unknown` | exact supported report contract only |
| behavioral claimability | `claimable`, `nonclaimable`, `unknown` | exact supported report contract only |
| training admission | `admitted`, `rejected`, `unknown` | an exact admission record only |
| governance approval | `approved`, `blocked`, `not_bound`, `unknown` | exact council/evidence binding only |
| quarantine | `quarantined`, `not_quarantined`, `unknown` | explicit quarantine record only |
| correction lineage | `valid`, `invalid`, `not_present`, `unknown` | validated correction binding only |

Absence never selects the favorable value. Numeric values such as `0` or `0.0`
must not satisfy a Boolean field. The three result-ceiling fields are accepted
only with their exact Python/JSON types and permitted literal values.

## 3. Trust boundaries and modules

The MVP implementation is divided into these modules. Names are provisional;
the responsibilities are normative.

### 3.1 `visualization.paths`

- Accept one or more run roots from the launch command, not from an HTTP query.
- Resolve and pin each root before serving.
- Accept a run identifier as one path component only.
- Reject empty, absolute, dot, separator-bearing, NUL-bearing, or overlong IDs.
- Resolve the candidate and require containment beneath the pinned root.
- Reject symlink components and non-directory targets.
- Open named allowlisted files only; never join a caller-supplied filename.
- Apply bounded per-file, per-line, record-count, and total-run sizes before
  parsing.

MVP defaults are: ASCII run IDs matching `[A-Za-z0-9._-]{1,240}`; 8 MiB
per JSON document; 64 MiB per JSONL file; 1 MiB per JSONL line; 250,000 rows per
stream; and 256 MiB across all files inspected for one run. Compressed evidence
is unsupported. Operators may lower these limits; raising a hard limit requires
an explicit launch option and remains capped at 256 MiB per file, 4 MiB per
line, 1,000,000 rows per stream, and 1 GiB per run. Limit values are reported by
`/api/v1/health` and never inferred from untrusted evidence.

### 3.2 `visualization.evidence`

- Load the six required files without mutating them.
- Refuse unsupported spatial schemas rather than approximate them.
- Require JSON objects where the contract requires objects.
- Reject blank, malformed, duplicate, missing, out-of-order, or non-integral
  scheduler positions.
- Require positions to form exactly `0..chain_length-1`.
- Validate run ID, counts, terminal identities, transition references,
  observation coverage, observer/body mapping, activation positions, closure
  membership, and schema/version agreement.
- Recompute the topology-closure commitment and require it to equal
  `run.json.topology_closure_hash`; require the run-directory name and run ID to
  equal the canonical scenario/seed/manifest-derived identity.
- Recompute content-record identities where the integrated record constructors
  make that possible; otherwise record the validation as structural, not
  authenticated.
- Treat schema-0.3 treatment bindings with the same closed validation used by
  `project_spatial_trajectory`.
- Never repair, normalize, reorder, or write evidence.

Extra known evidence files (for example society/live-persona records) are not
implicitly trusted. Each extension needs an explicit versioned parser. Unknown
files are ignored for visualization and are not included in a claim about the
six-file replay gate.

The persisted control evidence carries the action-script commitment and
terminal rule bindings but not a standalone script file from which the loader
can re-run `verify_manifest`. Structural loading therefore must not claim that
the complete script/genesis/terminal derivation is authenticated. Only the
existing provider-free byte replay (which rebuilds the scenario, script,
genesis, schedule, and manifest) may advance `replay_verification` to
`verified`.

### 3.3 `visualization.verification`

Replay verification is opt-in or precomputed at indexing time and calls the
existing `replay_spatial_run`. It runs in a temporary directory outside the
canonical root, invokes no model provider, and reports one of the three replay
states. A failed or unavailable replay remains visible as a conspicuous status;
it is never converted to verified because structural validation passed.

The service may be configured to list only replay-verified runs. Its default MVP
policy may list structurally valid local runs for diagnostics, but every run card
and replay screen must keep the verification state visible.

### 3.4 `visualization.provenance`

Versioned parsers may consume supported report, admission, correction, or council
binding records. Each parser validates exact types, closed values, source run ID,
and content hash/binding before emitting a status. No filename or prose phrase is
an approval oracle.

In actor mode, a report extension is positively projected to the small
allowlisted provenance fields above. The report object, per-tick evaluator rows,
private captures, model completion, metrics, or failure details never ride in an
actor payload merely because the service parsed them to validate the status.

Council access is out of process for the MVP. The service must not read the dirty
council repository or infer `RESULT_APPROVED`. A future signed/exported binding
adapter is a separate source. Until then governance and correction-lineage values
are `not_bound` or `unknown` as applicable.

### 3.5 `visualization.perspective`

The service process has one disclosure mode and creates exactly one payload
class:

- `actor`: the launch command pins one observer key; every response uses only
  that observer's validated actor observation artifacts;
- `privileged`: an explicit launch flag enables validated privileged artifacts
  plus chain, transitions, and activations;
- future `institution` and `evaluator`: disabled until versioned canonical
  inputs and disclosure rules exist.

Actor and privileged modes are separate service/browser contexts. A privileged
page cannot claim that a later client-side toggle has produced an actor-safe
context, because its process, browser memory, network history, and caches have
already received privileged data. To inspect another actor with the strict
non-interference guarantee, launch or restart an actor-mode service pinned to
that actor. A later authenticated control plane may improve this workflow only
under a separate security review.

Actor output must not contain or derive from:

- `privileged_content` or privileged observation IDs;
- authoritative placements or lifecycle;
- closure-visible state commitments;
- global chain state hashes, transitions, candidate universes, other actors'
  observations, evaluator labels, live completions, or private metadata;
- hidden entity labels, event summaries, SVG titles, accessibility labels,
  tooltips, search indexes, counts, cache keys, or error messages.

Actor state is reconstructed only from successive actor artifacts. Its topology
and layout likewise use only the room and directed portal rows present in the
actor artifacts at the selected position (or a derived discovered-so-far set
from earlier actor artifacts); `closure.json` is never a presentation input in
actor mode. The MVP actor timeline is a **derived observation-delta timeline**:
visibility/location changes and explicitly visible facts, labeled derived rather
than canonical events. Global transition and activation events are not exposed
in actor mode. Even an apparently self-authored transition is deferred until an
audited actor-safe action/event record exists.

The `run.json.instance_ids` logical-key map is not an actor-safe label registry.
Privileged mode may use it for research labels after validation. Actor mode uses
a stable shortened form of each **visible** canonical identity unless a future
versioned public-label record explicitly authorizes a display label; it never
scans or emits hidden logical keys to make labels friendlier.

The privileged payload can include the complete validated event index. The
active perspective is mandatory in the response envelope and permanently
visible in the UI.

### 3.6 `visualization.replay_index`

Build an immutable, position-indexed model before serialization. It contains:

- a stable position list;
- one state snapshot per position;
- a stable entity order by canonical instance identity;
- a stable event order by `(scheduler_position, category_order, record_id)`;
- topology and portal attachments;
- selected-action and legal-universe data only in privileged mode;
- explicit termination and provenance status;
- source references for every displayed authoritative fact.

Input objects are copied into immutable presentation records. No presentation
operation can obtain a writable reference to parsed canonical data.

### 3.7 `visualization.layout`

The current evidence has no coordinates. Privileged mode uses a versioned
deterministic topology layout:

1. sort room identities;
2. identify connected components from the directed attachment rows treated as
   an undirected layout graph only;
3. traverse each component from its smallest identity with deterministic
   neighbor ordering;
4. assign non-overlapping grid cells with a deterministic collision rule;
5. place disconnected components in stable identity order;
6. place agents and objects in stable identity order within their authoritative
   room; render held/inside/transit relationships with separate glyph rules.

This layout is `derived`, carries a `layout_version`, and is excluded from run
identity. It does not create reverse portals or change reachability.

Actor mode runs the same deterministic algorithm over only the actor-visible
room/portal projection at each position or the derived discovered-so-far graph.
It never accepts the complete closure as a layout hint. A room not present in
the actor-safe facts is absent, not merely hidden with CSS.

A later optional map-template file may supply presentation coordinates, labels,
and theme hints keyed to exact `(scenario, topology_closure_hash)`. It may not
add/remove rooms or portals or define collision, visibility, authority, legal
actions, or movement. A mismatch fails back to deterministic geometry.

### 3.8 `visualization.server`

- Bind loopback by default.
- Serve only embedded/package static frontend files and typed API responses.
- Do not serve directory listings or arbitrary paths.
- Require an actor key at actor-mode launch; use a separate explicit flag for a
  privileged-mode process.
- Generate a launch-only 256-bit local capability, print the capability-bearing
  URL once, and require it for the document and API. It is presentation security
  state, excluded from evidence and never logged in API responses.
- Reject unexpected `Host` headers; send no permissive CORS headers, cookies, or
  cross-origin credentials.
- Apply this CSP (with no inline script/style dependency):

  ```text
  default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'
  ```

  Also send `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, and `Cache-Control: no-store` on perspective
  responses.
- Serialize with a JSON encoder; never concatenate experiment text into HTML.
- Return bounded, non-sensitive error codes to actor requests.
- Offer no mutation, upload, model, run, replay-generation, correction, council,
  or asset-build endpoint.

### 3.9 Browser modules

The browser consumes only the view model:

- playback controller: begin/end, previous/next tick, previous/next event,
  play/pause, speed, exact seek;
- SVG arena: rooms, portals, agents, objects, selection, and supported overlays;
- chronicle: synchronized events with expandable sanitized structured fields;
- inspector: only fields already present in the response;
- provenance console: all independent status dimensions, never collapsed into
  one green badge;
- camera: pan, zoom, fit, focus, reset, and optional follow mode;
- accessibility: keyboard operation, visible focus, reduced motion, scalable
  text, and non-color-only semantics.

The renderer has no raw-artifact parser and no security filtering logic.

## 4. API contract for the MVP

All responses include `api_version`, `view_model_version`, `run_id`,
`perspective`, `source_schema_versions`, and `validation`.

Proposed read-only endpoints (the service mode fixes the perspective, so no
caller-controlled perspective query exists):

```text
GET /api/v1/runs
GET /api/v1/runs/{run_id}/view
GET /api/v1/health
```

Actor mode requires `--actor OBSERVER_KEY` at launch. Privileged mode requires
an explicit local research flag. Run listing returns a perspective-safe subset
of provenance only, not observation/entity content, the full observer map,
`instance_ids`, closure identities, or hidden counts. There is no actor-list,
`raw`, generic file, write, upload, run, inference, correction, or council
endpoint.

## 5. Scenario-driven maps

The map model has three non-overlapping layers:

| Layer | Source | May affect simulation? |
|---|---|---|
| topology template | validated `closure.json` plus run bindings | already authoritative; viewer cannot edit it |
| canonical map state | validated per-position placements and future versioned map-state records | viewer only renders it |
| visual theme/layout | derived layout or exact-bound presentation template and assets | never |

Current dynamic rendering includes movement, holdings, containment, transit, and
lifecycle changes that are actually recorded. Mutable doors/portals,
restrictions, ownership, control, bridges, enforcement zones, and reveal-state
changes are deferred because current evidence does not carry them.

The same topology can later be rendered as a Roman arena, palace, village,
prison, battlefield, or abstract lab without altering any canonical field. Theme
selection is client presentation state and never enters replay identity.

## 6. Authoritative, derived, evaluator, and unavailable semantics

Every overlay and inspector field is tagged internally:

- `authoritative`: directly validated from the active perspective's canonical
  artifact;
- `derived`: deterministic presentation computation with source references and
  version;
- `evaluator`: a separately validated analysis record, never represented as
  agent knowledge;
- `unavailable`: not present or not authorized; no fabricated default.

Examples:

| Feature | MVP status | Classification |
|---|---|---|
| rooms and directed portals | supported | authoritative |
| actor-visible room/entities/portals | supported | authoritative actor artifact |
| privileged placements/lifecycle | supported in privileged mode | authoritative privileged artifact |
| screen coordinates and paths | supported | derived |
| selected action and full legal universe | privileged only | authoritative activation evidence |
| institution/enforcement geometry | deferred | unavailable |
| relationship graph and memory | deferred | unavailable |
| deception/loyalty/emotion icon | forbidden without an authorized evaluator record | evaluator/unavailable |
| completion and claimability | supported only for a validated report schema | authoritative report; otherwise unknown |

## 7. Comparison extension

The single-run view model preserves stable room, body, object, event, world-line,
and source identities so comparison does not require a renderer rewrite.

Comparison is a later source. It must first validate a comparability record or a
closed canonical rule. At minimum it refuses incompatible scenario identity,
schema, agent/environment regime, unmatched seed requirements, and invalid fork
bindings. Calibration control/treatment pairs must re-run the canonical pair
constructor rather than trust a constructible pair record.

Only after validation may it emit synchronized positions, a divergence point,
and position/action/observation/outcome/metric differences. A visual join is not
evidence that two runs are scientifically comparable.

## 8. Visual design and asset boundary

The MVP uses repository-owned SVG geometry and a neutral theme. Every visual role
has a geometry fallback. Asset absence or failure cannot change topology, entity
state, event order, or provenance.

The later Roman tactical-diorama source may add sand, stone, marble, bronze,
wood, restrained banners, original tokens, and original icons. Decorative
columns, gates, walls, and props do not block movement or imply an institution
unless canonical data supplies that fact.

Runtime assets are presentation-only and live outside run directories. A
versioned manifest will bind asset ID, category, source, author, license,
creation method, source/output hash, dimensions/viewBox, compatibility, theme,
role, semantic/decorative class, and an explicit no-simulation-impact
declaration.

Custom packs are data-only (`SVG`, `PNG`, `WebP`, manifest, attribution, theme
tokens). They contain no JavaScript, Python, shell, browser plugin, or Blender
script. SVG is parsed and sanitized: scripts, event attributes, external
references, unsafe `foreignObject`, unsafe URLs, and executable content refuse.

Blender is not needed for architecture or MVP. If a later source proves value,
it is an optional offline authoring tool with repository-controlled scripts and
headless export. Normal serving, replay, and tests must pass with Blender absent.
No uploaded pack may trigger Blender.

## 9. Failure behavior

The loader fails closed on:

- root escape, symlink escape, unsafe run ID, or unknown path;
- missing/oversized/malformed evidence;
- unsupported schema/version;
- duplicate, missing, negative, non-integral, or out-of-order positions;
- count, terminal, observer, transition, activation, closure, or identity
  inconsistency;
- unknown perspective or missing actor;
- invalid report types or result-ceiling values;
- actor payload contamination by privileged names or values;
- unknown comparison compatibility;
- unsafe experiment-controlled text or assets.

A refused run gets no replay view. The run browser may show a minimal safe
diagnostic containing a server-generated error code and the configured root
label, never untrusted content or hidden identifiers.

No validation error causes a write, normalization, correction, council action,
model call, or cleanup of the source directory.

## 10. Required implementation tests

The MVP source must add adversarial coverage for:

1. **Paths and bounds:** traversal, absolute paths, separators, symlinks,
   allowlist bypass, large files/lines/record counts, and canonical-directory
   write attempts.
2. **Evidence:** missing files, malformed/non-object JSON, unsupported schemas,
   duplicate/reordered/truncated positions, inconsistent counts/terminal IDs,
   unknown observers, bad transition references, malformed topology, and
   treatment-binding drift.
3. **Result integrity:** exact Boolean/string types; omitted fields; replacement,
   sequential correction, correction-of-correction, stale/reordered lineage;
   incomplete results always display incomplete and nonclaimable.
4. **Perspective:** hidden entities/events/labels/tooltips/accessibility text and
   privileged IDs/fields are physically absent from actor JSON; invalid actor
   and perspective refuse; caches cannot cross perspectives.
5. **Replay:** exact seek, step, event jump, pause/resume, speed-independent
   ordering, end/termination, repeated deterministic loading, and optional
   provider-free replay verification.
6. **Map and semantics:** stable topology layout, directed portals preserved,
   invalid placement refused, holdings/containment/transit rendered, theme
   changes leave the canonical model unchanged, overlays retain provenance
   class, and missing assets fall back.
7. **Browser security:** experiment strings are text, never raw HTML; CSP and
   response headers; script/HTML/SVG injection fixtures; no raw-file endpoint.
8. **Accessibility:** keyboard controls and selection, visible focus, persistent
   perspective/replay status, reduced motion, scalable text, and non-color-only
   overlay meaning.
9. **Mutation resistance:** parsed inputs remain byte-identical; no write occurs
   under any run root; camera, playback, animation, and asset selection cannot
   change the view model's authoritative data.

Focused visualization tests, result-handoff tests, spatial runner/perception/
replay tests, zero-model live-pack replay, and the complete repository suite are
required before routing the MVP implementation.

## 11. Implementation slices and acceptance

### Source B — this architecture

Accepted when an independent audit finds the authority boundary, actor split,
provenance states, map layers, asset boundary, comparison deferral, and failure
posture complete and internally consistent.

### Source C — functional SVG MVP

Implement only:

- strict path/evidence loader;
- typed provenance status without council inference;
- actor and explicitly enabled privileged projections;
- immutable replay index and deterministic topology layout;
- loopback read-only API;
- validated-run browser;
- SVG arena;
- exact playback and timeline;
- actor/room/object inspector;
- supported overlays;
- neutral geometry fallbacks;
- security/accessibility tests and launch documentation.

It does not implement institutions, memory, relationships, player control,
mutable portals, live streaming, comparison, Roman polish, Blender, custom pack
builds, or new simulation records.

### Source D — original visual system

After MVP integration: design tokens, original Roman tactical-diorama SVGs,
tactical overlays, chronicle/research-console polish, asset manifest, licensing,
and accessibility regression. No semantic invention.

### Source E — optional asset pipeline

Only if separately justified: sanitization and manifest tooling first; Blender
installation and deterministic headless export second. Runtime remains
Blender-free.

### Source F — comparison

Only after a comparability contract exists: synchronized validated pairs,
divergence display, and authorized metrics/observation differences.

## 12. Explicit deferrals

The following are unnecessary for the first useful viewer and remain out of
scope:

- a game engine, database, cloud service, framework migration, or 3D renderer;
- live model inference, simulation streaming, manual/player control, multiplayer,
  combat systems, or a second scheduler;
- procedural terrain, live map editing, physics, destructible topology, or
  executable scenario maps;
- fabricated institutions, needs, schedules, relationships, memory, goals,
  emotion, morality, deception, or social-state overlays;
- client-side actor filtering, raw run download, remote asset fetching, uploads,
  marketplace, or executable custom packs;
- Blender installation before the asset-pipeline source demonstrates need;
- scientific comparison or result approval inferred from visual similarity,
  successful loading, complete execution, or replay verification.

## 13. First implementation demonstration

Once Source C is integrated, the documented command should be equivalent to:

```bash
python3 -m coliseum.textlab.visualization \
  --run-root logs/live-persona-runs \
  --actor ada \
  --host 127.0.0.1 --port 8765
```

Opening the printed loopback URL must show the validated live-persona replay as
an explicitly **incomplete, nonclaimable** diagnostic run, with actor-safe views
for `ada` only. Separate actor-mode launches can pin `bo` or `cy`; no actor list
or other actor's data reaches an actor-mode browser. Privileged view requires a
separate explicit launch flag and browser context. The viewer performs zero
model calls and writes zero files beneath the run root.

The same renderer must also accept a provider-free test-generated canonical
spatial run with a different topology, proving that the arena is not hard-coded.

## 14. Architecture acceptance gates

An audit should block this source if any conforming implementation could:

- deliver raw co-located actor/privileged rows to the browser;
- infer completion, claimability, approval, quarantine, admission, or correction
  validity from absence or from a different evidence layer;
- use a visual template to change topology or legality;
- expose privileged events through timeline, inspector, tooltip, accessibility,
  error, or cache surfaces;
- display a structurally valid run as replay-verified;
- treat presentation coordinates/assets as canonical evidence;
- compare unmatched runs as a valid pair;
- execute custom pack code or require Blender at runtime;
- write to canonical evidence or contact a model provider.

This source authorizes no implementation or integration by itself. The next step
after a plain design GO is a separate MVP implementation commit and audit.

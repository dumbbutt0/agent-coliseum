# Agent Coliseum Visualization MVP

Status: implementation candidate for `first-gladiator-visualization-mvp-001`.
This document describes the read-only geometric SVG viewer. It does not approve
the source, authenticate a scientific claim, or authorize model contact.

## What this slice does

The viewer opens persisted spatial evidence, validates every reconstructible
content identity and cross-file binding, constructs one disclosure-scoped view
model, and renders that model in a local browser. It provides:

- validated local replay discovery;
- deterministic scenario-driven room and directed-portal maps;
- recorded agent/object locations, holdings, containment, transit, and lifecycle;
- begin/end, tick/event step, play/pause, speed, and exact seek controls;
- synchronized event chronicle and entity/room/event inspection;
- selected-event map markers plus pan, zoom, fit/reset, and entity/event focus;
- visible-inventory derivation from only the active perspective's placements;
- authoritative/derived overlay labels;
- separate completion, claimability, replay, admission, governance, quarantine,
  and correction-lineage statuses;
- privileged or pinned-actor disclosure modes selected at process launch.

It does not run a scheduler, contact a model, create an experiment, modify a run,
approve a result, or infer unsupported memories, goals, relationships,
institutions, ownership, restrictions, or emotions.

## Boundary

```text
allowlisted persisted files
        |
        v
bounded strict-JSON loader
  - no symlinks / traversal
  - size and row ceilings
  - content-ID re-derivation
  - cross-file/state/action binding
        |
        v
perspective constructor
  +----------------------+---------------------------+
  | actor process        | privileged process        |
  | actor artifacts only | global validated evidence |
  +----------------------+---------------------------+
        |                              |
        +--------------+---------------+
                       v
deterministic presentation model
  - derived grid coordinates
  - safe summaries
  - no canonical writes
                       |
                       v
vanilla JavaScript + browser-native SVG
```

The renderer never parses canonical files. The actor response is positively
constructed from the pinned actor's exact-schema observation artifacts. Global
closure, privileged projections, transition records, activation records,
logical instance labels, hidden events, and evaluator reports never enter that
response.

The research console renders unsupported experiment ID, agent regime, model
regime, termination, and metrics fields explicitly as `Not available`; omission
never implies a favorable or known value.

## Launch

Use Python from the code repository. The command prints one launch-only
capability URL. The service binds only `127.0.0.1`, logs no requests, has no
cookie or permissive CORS behavior, and exposes no generic file route.

Actor-safe view of the committed live-persona capture:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m coliseum.textlab.visualization \
  --run-root logs/live-persona-runs \
  --actor ada \
  --verify-replay
```

Explicit privileged research view:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m coliseum.textlab.visualization \
  --run-root logs/live-persona-runs \
  --privileged \
  --verify-replay
```

For ordinary scripted spatial runs, point `--run-root` at the directory that
directly contains their run-ID directories. Omit `--verify-replay` for fast
structural inspection; the interface will visibly say `unverified`. Favorable
completion or claimability is never displayed from a structurally
self-consistent live report without a future exact result-binding adapter. The
capture replay status remains separately visible.

The viewer has no browser perspective switch. Actor and privileged views require
separate processes and capability URLs.

## Accepted evidence

The MVP admits spatial run schemas `0.2` and `0.3` with exactly:

```text
run.json
chain.jsonl
transitions.jsonl
observations.jsonl
activations.jsonl
closure.json
```

`live_report.json` is the only optional report extension currently parsed. It
uses a closed schema, exact Boolean types, a re-derived report ID and regime ID,
and internally consistent completion/effective-N relations. A negative ceiling
(`incomplete`, `nonclaimable`) is retained only in the explicit privileged
research view. Actor responses report evaluator dimensions as `unknown` and do
not vary with the presence or contents of `live_report.json`. A favorable ceiling
remains `unknown` until a future exact result-binding adapter authenticates the
report. The current live replay gate authenticates the spatial six and captured
persona rows, not `live_report.json`; the privileged console exposes that
distinction.

Structural validation and replay verification are deliberately different:

- structural validation recomputes records whose complete preimages are
  persisted and binds streams to the same run, chain, state, actor, and action;
- replay verification invokes the existing provider-free spatial or captured-
  persona replayer and requires byte identity;
- neither state implies training admission, council result approval, quarantine
  clearance, correction validity, or scientific acceptance.

## Scenario-driven maps

The current adapter implements the three-layer map boundary:

| Layer | MVP source | Authority |
|---|---|---|
| topology template | authenticated `closure.json` in privileged mode; accumulated actor-observed rooms/portals in actor mode | canonical facts, scoped by perspective |
| map state | exact per-position observation placement/lifecycle records | canonical facts, scoped by perspective |
| visual theme/layout | `geometric_mvp` plus `derived_grid_v1` | presentation only |

The grid layout never enters run identity. Theme or camera changes cannot alter
connectivity, legal actions, observation, scheduling, movement, or evidence.
Current map-state changes include only facts that existing evidence records:
movement, transit, holdings, containment, and lifecycle. Mutable door state,
ownership, institutional geometry, restrictions, bridges, and continuous
coordinates are not fabricated.

## Provenance display

The research console keeps these dimensions separate:

- artifact validation;
- replay verification;
- report authentication;
- completion;
- behavioral claimability;
- result status;
- training admission;
- governance approval;
- quarantine;
- correction lineage.

Unknown or absent data never selects a favorable state. The current viewer does
not read the separate dirty council repository. Governance is therefore
`not_bound`; admission, quarantine, and correction lineage remain `unknown`
unless a future separately audited adapter provides exact bindings.

## HTTP and content security

The capability prefix is required for the document, static assets, and all API
routes. The only API routes are:

```text
GET /<capability>/api/v1/health
GET /<capability>/api/v1/runs
GET /<capability>/api/v1/runs/<run-id>/view
```

The static allowlist contains `index.html`, `styles.css`, `playback.js`, and
`app.js`. There is no raw-file, directory, upload, write, correction, council,
inference, execution, replay-generation, or asset-build endpoint.

Responses enforce an exact loopback `Host`, `no-store`, `nosniff`,
`no-referrer`, same-origin resource policy, a restrictive permissions policy,
and this CSP:

```text
default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:;
connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none';
form-action 'none'
```

Experiment-controlled strings are serialized as JSON and placed into the DOM
with `textContent`. The client does not use raw HTML insertion or evaluation.

Default loader limits are 8 MiB per JSON file, 64 MiB per JSONL stream, 1 MiB
per line, 250,000 rows per stream, and 256 MiB per run. Absolute configurable
ceilings are 256 MiB per file, 4 MiB per line, 1,000,000 rows, and 1 GiB per run.

## Accessibility and controls

- Space: play/pause.
- Left/right: previous/next recorded position.
- Home/end: beginning/end.
- Every control and map entity is keyboard focusable and labeled.
- Focus has a non-color outline.
- Room, portal, and entity semantics use shape, text, and line pattern in
  addition to color.
- `prefers-reduced-motion` suppresses nonessential motion.
- Playback is discrete over authoritative positions; speed changes timing only.

## Assets and licensing

This slice contains no third-party game art, audio, fonts, sprites, or Blender
output. The arena consists only of original repository-authored SVG geometry and
CSS. Every required role therefore has a geometric fallback by construction.
The Roman tactical diorama design system, an asset manifest, sanitized custom
packs, and optional offline Blender authoring remain separate later sources.
Blender is neither installed nor required here.

## Verification commands

Focused Python/security suite (loopback permission is required for three HTTP
boundary tests):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/test_visualization_mvp.py -q -p no:cacheprovider
```

Browser playback logic:

```bash
node --check coliseum/textlab/visualization/static/playback.js
node --check coliseum/textlab/visualization/static/app.js
node --test tests/test_visualization_playback.js
```

Provider-free replay can also be requested at launch or exercised directly by
the focused tests. No verification command in this slice authorizes live model
or Ollama contact.

Before council routing, run the complete Python suite from a tree containing the
tracked/expected run fixtures, record the exact commit, confirm a clean worktree,
and route that exact commit under a fresh visualization-MVP source. A local green
test is not an integration verdict.

## Troubleshooting

- `No runs admitted`: confirm `--run-root` directly contains run-ID directories
  and, in actor mode, that the pinned observer key belongs to the run.
- `refused directories`: one or more directories failed closed on schema,
  identity, binding, symlink, path, or size validation. The HTTP response never
  includes sensitive parser detail; use focused local diagnostics on a copy.
- `unexpected_host`: open the exact printed capability URL without changing its
  host or port.
- `unverified`: relaunch with `--verify-replay`; this is not equivalent to a
  failure, but it cannot authenticate favorable result claims.
- Missing map features: the MVP renders only current canonical evidence. Add a
  versioned simulation record before adding presentation that implies a new
  authoritative fact.

## Deferred sources

The following remain intentionally outside this implementation candidate:

- Roman diorama design tokens and original semantic SVG icon pack;
- asset manifest, SVG sanitization, custom data-only packs, and license tooling;
- optional deterministic headless Blender export;
- valid baseline/intervention comparison and divergence overlays;
- institution/evaluator disclosure modes;
- live streaming, manual control, simulation mutation, or browser inference.

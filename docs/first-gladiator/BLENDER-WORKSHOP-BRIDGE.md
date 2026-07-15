# Blender Workshop bridge — design source

Status: **DESIGN ONLY**. This source authorizes no Blender execution, repository
implementation, projection of a canonical run, visual claim, asset admission,
or Council integration. Implementation and the first render proof require a
separately routed source after this design receives the applicable plain Council
verdict.

Proposed source: `first-gladiator-blender-workshop-design-001`.

## 1. Purpose

Agent Coliseum may use a locally installed Blender executable as an optional,
offline presentation worker. The first implementation must prove two things:

1. a reviewed repository script can build and render a small original scene;
2. the owner can watch that job through a safe, read-only **Blender Workshop**
   page.

The Workshop is an observation surface, not a scene editor or execution console.
It shows the current stage, latest preview, bounded event log, expected scene
objects, output files, and final hashes while Blender runs. It has no endpoint
for Python, commands, uploads, scene mutation, canonical-run selection, or job
creation.

This work remains subordinate to the learning-first roadmap. It does not modify
the T0-A source, contact a model, create learning evidence, or delay a scientific
critical-path repair.

## 2. Existing boundary retained

This design extends, without weakening,
`VISUALIZATION-ARCHITECTURE.md` and `VISUALIZATION-MVP.md`:

```text
validated canonical evidence
        -> authorized read-only presentation projection
        -> repository-controlled Blender worker
        -> derived scene/render/progress files
        -> read-only Workshop view
```

Blender and the Workshop are presentation consumers. They never:

- read arbitrary historical run directories;
- determine topology, legality, visibility, observations, outcomes, completion,
  claimability, admission, quarantine, governance, or experiment identity;
- contact an LLM or replay provider;
- write beneath `logs/`, a configured run root, a Council repository, or any
  canonical-evidence directory;
- turn interpolation, camera movement, lighting, decoration, or rendering into
  a canonical state;
- turn a successful render into scientific approval;
- become required for the SVG viewer, replay, tests, or normal repository use.

All required visual roles retain SVG/geometric fallbacks. Blender absence is a
supported state.

## 3. Same-host execution profile

The first supported environment is Codex in WSL invoking a trusted Blender
installation on the same Windows host. The currently discovered executable is:

```text
WSL:     /mnt/c/Program Files/Blender Foundation/Blender 5.2/blender.exe
Windows: C:\Program Files\Blender Foundation\Blender 5.2\blender.exe
Version: Blender 5.2.0 LTS
Build:   fbe6228777e7 (Windows Release, 2026-07-14)
```

The implementation must rediscover and verify the executable at runtime; this
observed path is not a canonical contract or experiment field. Supported
configuration is an explicit command-line option, then `BLENDER_EXECUTABLE`,
then a bounded platform-specific discovery list. Discovery never searches
project-controlled PATH entries or downloads an executable.

The bridge invokes Blender with a subprocess argument array, `shell=False`, an
absolute executable, and an allowlisted reviewed script. It never uses `eval`, a
shell command string, Blender global Auto Run, GUI automation, a third-party MCP
server, an unrestricted `execute_python` endpoint, startup files, user plugins,
or uploaded scripts.

WSL paths are translated with `wslpath -w` through an argument-array subprocess.
The returned path must identify the same repository-scoped input or derived
output after normalization. Failure to translate or verify a path refuses the
job.

The smoke invocation is conceptually:

```text
blender.exe --background --factory-startup --disable-autoexec --offline-mode
  -noaudio --python-exit-code 17
  --python <reviewed-smoke-script-windows-path> --
  --job-spec <validated-job-spec-windows-path>
```

The installed Blender 5.2 help output has independently confirmed all flags in
that invocation. The bridge still
verifies them against the executable selected at runtime. Unsupported flags fail
closed; they are not silently removed. The bridge does not pass
`--python-use-system-env`, `--python-use-user-env`, `--online-mode`, `--addons`,
`--python-expr`, `--python-text`, `--python-console`, or `--command`.

## 4. Repository and output layout

Source code follows the integrated visualization package:

```text
coliseum/textlab/visualization/blender/
  __init__.py
  bridge.py
  job.py
  workshop_server.py
  scripts/
    smoke_scene.py
    inspect_scene.py
  static/
    index.html
    app.js
    styles.css
```

Tracked original assets or templates, if later needed, live in a separately
audited repository asset directory. The smoke scene uses only procedural Blender
primitives and repository-owned colors.

Generated files default to:

```text
derived/textlab/visualization/blender/jobs/<job_id>/
  job.json
  progress.json
  events.jsonl
  preview.png
  render.png
  scene.blend
  worker-result.json
  render-manifest.json
```

Generated job directories are derived output and excluded or managed according
to repository policy. They are never committed as canonical run evidence. The
implementation rejects absolute output supplied by an untrusted projection,
parent traversal, symlinks, reparse-point escape where detectable, an existing
non-job directory, and any output beneath an input/canonical/Council root.

If WSL filesystem rendering is materially slow, a later source may introduce a
fixed Windows staging root. That source must authenticate copy-in/copy-out
digests and retain the same no-canonical-write boundary. The first slice does
not require it.

## 5. Job identity and immutable specification

The host constructs `blender_job.v1` from validated values before Blender starts.
The job identity is a SHA-256 content hash over a typed, canonical preimage with
the output id excluded. It includes:

- schema and bridge version;
- job kind (`smoke` initially);
- reviewed script relative path and SHA-256;
- Blender executable version identity;
- template/asset-pack identity, `not_applicable` for smoke;
- authorized projection id/digest, `not_applicable` for smoke;
- output dimensions, frame bounds, renderer, and deterministic render settings;
- expected semantic and decorative object ids;
- repository commit and source name;
- derived output root alias and root-relative job directory.

Implementation reuses `coliseum.textlab._content_record.ContentRecord`,
`schema.canonical_json`, and `schema.config_hash`; it does not introduce a
second identity or registry primitive. Its fixed domain and exhaustive preimage
keys must be bound by the implementation source before code is routed.

It contains no wall clock, process id, absolute path, access token, raw run data,
private observation, completion, Council credential, or user-supplied Python.
Runtime timestamps and process metadata may appear only in non-identity progress
records.

The host writes `job.json` atomically before execution and opens a no-follow file
descriptor where the platform permits it. The worker verifies the job schema,
job id, script hash binding supplied by the host, job kind, output confinement,
and closed enum values before constructing a scene.

## 6. Smoke scene

The reviewed smoke worker starts with `--factory-startup` and clears the scene.
It creates exactly:

- one ground plane;
- three distinct room/base structures;
- three placeholder agent objects;
- one orthographic camera;
- a bounded lighting rig;
- materials made from original constant colors.

It renders one low-resolution preview, renders one final PNG, saves one derived
`.blend`, and writes a bounded worker result. It imports no external model,
texture, script, font, audio, or asset. It does not enable simulation physics,
network access, drivers, handlers, add-ons, compositor file-output nodes, or
arbitrary file references.

The worker's own inventory claim is not sufficient. After the render process
exits, the host invokes a separately reviewed `inspect_scene.py` against the
saved `.blend` under the same factory-startup, autoexec-disabled, offline
profile. The inspector emits only a bounded structural inventory. The host
requires the exact expected object/type set and refuses embedded Text blocks,
drivers, external libraries, packed executable content, compositor file-output
nodes, unexpected images, and undeclared file references. A scene object is not
a canonical Coliseum entity merely because its display name resembles one.

## 7. Watchable progress protocol

The Blender process emits presentation-only progress beneath its one job
directory. `progress.json` is a replace-only snapshot with:

- `schema_version`;
- `job_id`;
- monotonic `sequence`;
- closed `stage` enum;
- bounded integer `completed_units` and `total_units`;
- bounded safe display message;
- latest preview relative filename and SHA-256, when complete;
- declared expected/created object counts;
- terminal status (`running`, `completed`, or `failed`);
- error code from a closed taxonomy, never an unrestricted traceback.

Initial stages are:

```text
created -> scene_clearing -> geometry_building -> materials_building
        -> camera_lighting -> preview_rendering -> preview_ready
        -> final_rendering -> scene_saving -> completed
```

`failed` is terminal from any stage. Stage and sequence regression are refused
by the Workshop adapter. `events.jsonl` contains the same bounded transitions in
append order and is capped by row and byte limits. These files are operational
telemetry, not experiment evidence and not proof that a stage actually completed.
Final artifact validation remains host-side after Blender exits.

The worker publishes files atomically (`temporary sibling -> fsync where
available -> replace`). A preview is referenced only after its bytes are closed
and hashed. The Workshop may miss intermediate frames without affecting the job.

## 8. Blender Workshop page

The host starts a loopback-only `127.0.0.1` read-only server pinned to one job id
and one derived job directory. It reuses the SVG viewer's capability URL, Host
validation, security headers, bounded file reads, safe text rendering, and
method refusal patterns where applicable.

The browser may request only:

- static Workshop HTML/CSS/JavaScript;
- a sanitized host-constructed job summary;
- the latest hash-bound preview PNG;
- a bounded sanitized progress/event projection;
- a host-validated terminal artifact/manifest summary.

The server has no mutation methods. `POST`, `PUT`, `PATCH`, `DELETE`, WebSocket,
server-sent commands, uploads, raw paths, directory listings, arbitrary job ids,
raw worker tracebacks, `.blend` download, and Python/command input all refuse.

The page polls with bounded backoff and displays:

- Blender version and renderer;
- job kind and id prefix;
- current stage and progress;
- latest preview with its digest status;
- expected and created object inventory;
- bounded safe events;
- output validation states and hashes after completion;
- an always-visible **DERIVED VISUALIZATION — NOT EVIDENCE** banner;
- canonical source/claim status only when supplied by a validated projection.

All experiment-controlled strings use `textContent`; no raw HTML or inline SVG is
inserted. Preview responses are `image/png`, `nosniff`, no-store, and digest
checked before serving. Keyboard navigation, visible focus, reduced motion,
scalable text, live-region throttling, and non-color progress semantics are
required.

Watching does not control Blender. Closing the page does not cancel or change the
job. The host CLI, not the browser, owns process cancellation.

To make live observation practical without a browser mutation endpoint, watch
mode is split into host-side steps:

1. `prepare` validates and writes the immutable job, starts the pinned Workshop
   server, and prints its capability URL;
2. Codex gives that URL to the owner, who may open it before rendering starts;
3. `start <job_id>` revalidates the prepared job and launches only its bound
   reviewed worker;
4. the already-open page observes progress until the terminal host validation.

Preparing a job does not execute Blender. Opening or polling the Workshop does
not start it. Only the repository CLI process may perform `start`, and the job id
selects a previously validated immutable spec rather than arbitrary arguments.

## 9. Host/worker trust and failure behavior

The bridge treats Blender as a bounded external worker even though it is local.
It records stdout/stderr to capped host logs outside canonical roots and refuses:

- missing, non-absolute, non-regular, or unapproved executable paths;
- unexpected Blender version output;
- a script outside the repository allowlist or whose digest drifted;
- environment variables that request Python startup, add-ons, network proxies,
  or arbitrary module paths;
- a job spec with unknown keys, unknown enums, excessive dimensions/frames, or
  unsafe paths;
- output symlinks, root escapes, overwrite of pre-existing files, or files not
  declared by the job;
- nonzero exit, timeout, missing terminal progress, missing/empty output,
  invalid PNG, invalid object inventory, hash mismatch, or unexpected file;
- a render manifest when any required validation failed.

A failed job remains a failed derived job. It cannot change a source run or hide
its negative provenance. Cleanup is explicit and never follows symlinks.

## 10. Render manifest

Only the host writes `render_manifest.v1`, after successful worker exit and
independent output validation. It binds:

- job id and schema/bridge versions;
- canonical run id and source evidence digest, or `not_applicable` for smoke;
- authorized presentation-projection id and digest, or `not_applicable`;
- Blender version/build hash;
- reviewed script path, digest, and repository commit;
- template and asset-pack versions/digests;
- frame range, resolution, renderer, camera and deterministic setting summary;
- object inventory digest;
- each output relative path, size, media type, and SHA-256;
- worker result digest;
- derived status and explicit `simulation_impact: none`;
- source completion, claimability, governance, replay, and admission states only
  when copied from a strictly validated projection, never inferred.

Render success cannot promote any source status. Interpolated frames are always
declared presentation-only.

## 11. Later Coliseum projection

The smoke source reads no run. A later, separately audited source may accept a
versioned actor-safe or explicitly privileged visual projection produced by
Coliseum's validated adapter. Blender still cannot parse raw run evidence.

That projection may contain only the authorized subset needed to render:

- canonical run id and source evidence digest;
- projection schema/id/digest and perspective;
- room/portal/base geometry already supported by canonical records;
- authorized agent/object visual ids and public faction display;
- recorded position sequence, movement/event kinds, and tick binding;
- recorded terminal, completion, claimability, replay, and governance states.

Theme and asset choices cannot define topology, movement, legality, visibility,
institutional meaning, or agent knowledge. Interpolation samples between two
recorded positions and snaps at tick boundaries; it never creates an event.

The first real proof should use the already admitted deterministic Society Seed
viewer fixture. It creates a low-poly three-room arena, original placeholders for
ada/bo/cy and token/box/gem, a lightly angled orthographic camera, an image
sequence or short video, a `.blend`, and a render manifest. Every recorded
transition is compared with the authenticated SVG projection. The incomplete
Live Persona capture may be rendered later only with its negative provenance
preserved.

## 12. Required implementation tests

The first implementation source must cover, without requiring Blender for the
normal suite:

1. executable discovery/configuration, exact version parsing, and Blender-absent
   behavior;
2. subprocess argument arrays, `shell=False`, reviewed-script allowlisting, and
   WSL path translation without string evaluation;
3. job identity, strict schema, deterministic settings, dimension/frame caps,
   and immutable input handling;
4. output-root traversal, absolute paths, symlinks, overwrite, undeclared files,
   and canonical/Council root refusal;
5. progress sequence/stage monotonicity, malformed/truncated/oversized telemetry,
   preview hash mismatch, and failure terminals;
6. loopback capability, Host checks, security headers, method refusal, no raw
   path/job selection, safe text, and no arbitrary command/Python endpoint;
7. actor-safe projection before asset resolution and physical absence of private,
   hidden, raw-completion, evaluator, and Council fields;
8. nonzero exit, timeout, missing output, invalid PNG, invalid inventory, and
   unexpected output fail closed without a manifest;
9. manifest hashes, relative paths, Blender/script/template/asset binding,
   presentation-only declaration, and no status promotion;
10. canonical run bundle hashes and Council tree state remain byte-identical;
11. accessibility and reduced-motion behavior;
12. normal visualization, replay, and repository tests pass with Blender absent.

An opt-in integration test, excluded from ordinary CI, invokes the exact approved
local Blender executable and validates one smoke job. It records version and
output hashes but makes no portability claim from one Windows host.

## 13. Acceptance sequence

1. Council audits and approves this design.
2. A narrow implementation source adds the bridge, smoke worker, Workshop page,
   unit/security/accessibility tests, and documentation.
3. Focused and full tests pass with Blender absent.
4. The exact local Blender 5.2 executable runs one reviewed smoke job.
5. The host prepares the job and Workshop; the owner opens the printed
   capability URL; the host then starts the already-bound job.
6. The owner watches progress/preview read-only while Blender runs.
7. Blender exits zero; PNG and `.blend` are nonempty; the PNG is visually
   inspected; the independent inspector confirms the inventory and absence of
   executable/external scene content; a derived render manifest is valid.
8. Canonical run and Council bundle hashes remain unchanged.
9. The implementation receives independent plain GO and authorized integration.
10. A separate projection source renders the admitted Society Seed trajectory.

The smoke proof establishes a secure executable and observation bridge. It does
not establish scientific visualization correctness for a canonical run; the
Society Seed projection proof does that later.

## 14. Explicit deferrals

The first implementation does not add:

- browser scene controls, editing, cancellation, job submission, uploads, or
  arbitrary Blender/Python execution;
- a Blender MCP server, remote worker, public network listener, authentication
  service, GUI automation, global Auto Run, add-ons, or runtime Blender;
- external assets, custom packs, downloaded textures, asset marketplace, or
  proprietary game likeness;
- canonical-run parsing inside Blender, live simulation streaming, model contact,
  hidden-data projection, or scientific claim computation;
- Society Seed animation, GLB/video export, Roman asset polish, or comparison;
- procedural worlds, physics, game mechanics, or a second simulation engine.

Those require their own evidence and, where material, separately audited sources.

# Blender Workshop bridge — design source

Status: **DESIGN ONLY — REVISION 002**. This source authorizes no Blender execution, repository
implementation, projection of a canonical run, visual claim, asset admission,
or Council integration. Implementation and the first render proof require a
separately routed source after this design receives the applicable plain Council
verdict. Revision 002 preserves the blocked revision-001 lineage at Council
event `001433-d1bfc40f` and closes its three reproduced HIGH findings: job
identity/path recursion, fail-open Windows alias handling, and an open-ended
smoke/inspector profile.

Proposed source: `first-gladiator-blender-workshop-design-002`.

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

The version/build and help flags above are a builder-observed environment fact;
revision 001 did not commit a raw digest-bound help capture, so this document
does not call that observation independently verified evidence. The implementation
must record the raw `--version` and `--help` bytes and their SHA-256 in its
separately routed preflight evidence, then verify required flags against the
selected executable at runtime. Unsupported flags fail closed; they are not
silently removed. The bridge does not pass
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
first slice accepts no caller-selected output root. It uses the fixed
repository-relative alias `repo_derived`, whose configured value is
`derived/textlab/visualization/blender`, and derives the job leaf exactly as
specified in section 5.

### 4.1 Fail-closed WSL/Windows confinement

Lexical containment is insufficient. Before Blender starts, a host verifier
must positively attest all of the following or refuse without creating a job
output:

1. The Linux repository root and fixed derived root are absolute canonical
   paths. Every existing component is opened from its parent with no-follow
   semantics, is not a symbolic link, and stays beneath the opened repository
   root. The host records device/inode identity for each opened component.
2. The fresh job directory is created once beneath the already-open derived
   root with owner-only permissions, by a relative `mkdirat`-equivalent. It did
   not exist before preparation and its device/inode is held for the job.
3. `wslpath -w` is invoked as an argument array. Its result is absolute, is not
   a drive-relative path, and is not a caller-provided UNC path. Converting the
   Windows result back with `wslpath -u` yields the same opened Linux path after
   platform-correct normalization.
4. A small reviewed Windows-native path guard resolves repository root,
   derived root, job directory, protected roots, and every existing ancestor by
   handle. It rejects any symlink, junction, mount point, reparse tag, UNC/drive
   alias, case alias that changes identity, device path, alternate data stream,
   or result whose final volume/file identity differs from the WSL attestation.
5. The Windows guard retains non-delete-shared handles for the derived root and
   job directory for the complete child lifetime. It launches only the bound
   Blender executable and exact argument array while those handles are held.
   This prevents an ancestor or job-directory component from being swapped into
   an alias between verification and output creation.
6. Every declared output is a single fixed filename, pre-existence is rejected,
   and creation occurs only in the guarded fresh directory. The worker may use
   only declared temporary siblings; the guard and host inventory reject every
   other file. Before a manifest can exist, the host reopens each output with
   no-follow semantics and requires the same guarded directory identity.
7. Protected canonical, input, run, Git, and Council roots are resolved by both
   Linux and Windows identity, not string prefix, and must be disjoint from the
   output root.

The reviewed guard is part of the future implementation source; it is not an
unrestricted command surface. If Windows handle inspection, reparse detection,
non-delete-sharing, WSL round-trip identity, or any component proof is
unavailable or indeterminate, the bridge fails before starting Blender. The
first slice therefore does not support `/mnt/*` output roots, arbitrary Windows
staging roots, user-selected network paths, or a degraded lexical-only mode.

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
- derived output root alias (`repo_derived`);
- fixed job-directory scheme (`content-addressed-job-dir.v1`); and
- id-independent relative parent (`jobs`).

The preimage never contains `job_id`, `<job_id>`, a substituted job-id string,
or any path component derived from the job's own id. Construction is exactly:

```text
job_id = ContentRecord(blender_job.v1 preimage).id
job_relative_directory = "jobs/" + job_id
```

`job_relative_directory` is a deterministic locator derived **after** identity;
it is not an identity-bearing preimage field. The host requires the stored
`job.json` id to equal a single recomputation from the exhaustive preimage and
requires its actual leaf to equal `jobs/<recomputed-id>`. Placeholder
substitution, an ID-dependent preimage directory, or any other leaf is refused.

Implementation reuses `coliseum.textlab._content_record.ContentRecord`,
`schema.canonical_json`, and `schema.config_hash`; it does not introduce a
second identity or registry primitive. The domain is
`blender_job.v1`. The exhaustive top-level preimage key set is:

```text
job_schema_version
bridge_version
job_kind
smoke_profile_version
reviewed_script                 # {relative_path, sha256}
blender_identity                # {version, build_hash, platform}
template_binding                # {status, identity}; not_applicable for smoke
asset_pack_binding              # {status, identity}; not_applicable for smoke
projection_binding              # {status, id, sha256}; not_applicable for smoke
render_profile                  # exact section-6.1 values and caps
expected_inventory_digest       # canonical section-6.2 inventory
repository_commit
source_name
derived_output_root_alias       # literal repo_derived
job_directory_scheme            # literal content-addressed-job-dir.v1
job_relative_parent             # literal jobs
```

Closed nested schemas use exactly the named keys above; a not-applicable
binding carries its `status` plus the literal `not_applicable` in every other
listed slot rather than omitting keys. Unknown or missing keys refuse. The
output field `job_id` is excluded exactly once by `ContentRecord`.

It contains no wall clock, process id, absolute path, access token, raw run data,
private observation, completion, Council credential, or user-supplied Python.
Runtime timestamps and process metadata may appear only in non-identity progress
records.

The host writes `job.json` atomically before execution and opens it through the
guarded no-follow directory. The worker verifies the job schema,
job id, script hash binding supplied by the host, job kind, output confinement,
and closed enum values before constructing a scene.

## 6. Smoke scene

The initial closed profile is `coliseum-smoke.v1`. Implementations may not tune
it under the same version.

### 6.1 Exact render and resource profile

| Setting | `coliseum-smoke.v1` value |
|---|---|
| frames | start `1`, end `1`, step `1`, current `1` |
| preview | `640x360`, 100 percent |
| final | `1280x720`, 100 percent |
| engine | `CYCLES` |
| device policy | CPU only; GPU, network, and distributed render disabled |
| samples | `16` |
| seed | `0` for every seed-bearing setting; absence of a required seed field refuses |
| threads | fixed `1` |
| denoise | disabled |
| motion blur | disabled |
| compositing/sequencer | disabled; no sequence editor |
| film | opaque, no transparency |
| output | PNG, RGBA, 8-bit, compression `15`; no metadata stamps |
| color management | display `sRGB`, view `Standard`, look `None`, exposure `0`, gamma `1`, view settings fixed |
| camera | orthographic; location `(9,-11,11)`, rotation `(0.872665,0,0.698132)` radians, scale `19`, clip `0.1..100` |
| world | constant color `(0.03,0.03,0.03,1)`; nodes disabled |
| sun | one SUN, energy `2.0`, angle `0.0872665`, rotation `(0.523599,-0.349066,-0.523599)` |

Cycles adaptive sampling, denoising, persistent data, light-tree use,
caustics, and motion blur are disabled. Maximum bounces are `4`; diffuse,
glossy, transmission, transparent, and volume bounces are each `2`; clamp
direct and indirect are `0`. Unsupported or renamed required settings cause the
runtime profile check to refuse rather than silently choosing a substitute.

The ordinary implementation verifier binds exact values and rejects missing,
unknown, or drifted profile keys. The same-host output hash is recorded, but
the design makes no bit-identical portability claim across Blender builds,
drivers, CPUs, or GPUs.

Hard caps are: 64 KiB `job.json`; 32 KiB `progress.json`; 128 events and
128 KiB `events.jsonl`; 64 KiB each worker result and inspector report; 128 KiB
render manifest; 8 MiB preview PNG; 32 MiB final PNG; 64 MiB `.blend`; 1 MiB
each stdout/stderr; 128 MiB total job directory; one Blender child; one render
thread; 4 GiB process-memory job limit; 180 seconds process CPU time; and 180
seconds host wall time. A Windows Job Object or equivalently strong native
process boundary must enforce process count, memory, and CPU limits; if the
host cannot apply it, execution refuses. Exceeding any cap terminates the
derived job and forbids a manifest.

### 6.2 Exact scene inventory

The reviewed worker starts with `--factory-startup`, clears the editable scene,
and creates only this allowlist:

- scene `Scene` and collection `COLISEUM_SMOKE`;
- mesh objects `SMOKE_GROUND`, `SMOKE_ROOM_A`, `SMOKE_ROOM_B`,
  `SMOKE_ROOM_C`, `SMOKE_AGENT_ADA`, `SMOKE_AGENT_BO`, and `SMOKE_AGENT_CY`;
- one same-named mesh datablock per mesh object;
- materials `MAT_GROUND`, `MAT_ROOM_A`, `MAT_ROOM_B`, `MAT_ROOM_C`,
  `MAT_AGENT_ADA`, `MAT_AGENT_BO`, and `MAT_AGENT_CY`, one per mesh;
- camera object `SMOKE_CAMERA` with datablock `SMOKE_CAMERA_DATA`;
- light object `SMOKE_SUN` with datablock `SMOKE_SUN_DATA`;
- world `SMOKE_WORLD`.

The ground is one procedural plane; rooms are three procedural cubes; agents
are three procedural cylinders. Their exact primitive parameters, transforms,
material RGBA values, object-to-datablock links, and collection membership are
constants in the versioned worker and repeated in the strict expected-inventory
fixture. There are exactly nine objects, seven meshes, seven materials, one
camera, one light, one world, one scene, and one non-master collection. Every
object has zero modifiers, zero constraints, zero particle systems, zero
simulation/physics settings, and zero animation drivers. Frame count remains
one; no action or animation datablock exists.

| Object(s) | Primitive and transform | Material RGBA |
|---|---|---|
| `SMOKE_GROUND` | plane size `18`; location `(0,0,0)`; rotation `(0,0,0)`; scale `(1,1,1)` | `(0.36,0.22,0.10,1)` |
| `SMOKE_ROOM_A` | cube dimensions `(4,6,0.4)`; location `(-5,0,0.2)` | `(0.65,0.53,0.34,1)` |
| `SMOKE_ROOM_B` | cube dimensions `(4,6,0.4)`; location `(0,0,0.2)` | `(0.55,0.55,0.58,1)` |
| `SMOKE_ROOM_C` | cube dimensions `(4,6,0.4)`; location `(5,0,0.2)` | `(0.70,0.64,0.50,1)` |
| `SMOKE_AGENT_ADA` | 16-vertex cylinder, radius `0.45`, depth `1.4`; location `(-5,0,1.1)` | `(0.72,0.16,0.12,1)` |
| `SMOKE_AGENT_BO` | same cylinder; location `(0,0,1.1)` | `(0.12,0.34,0.72,1)` |
| `SMOKE_AGENT_CY` | same cylinder; location `(5,0,1.1)` | `(0.16,0.58,0.24,1)` |

All room and agent rotations are `(0,0,0)` and scales are applied to the mesh
before inspection so object scale is `(1,1,1)`. Materials have no texture and
use the fixed RGBA as diffuse and Principled-BSDF base color with metallic `0`,
roughness `0.65`, alpha `1`, and default emission `0`.

Before saving, the worker removes transient render-result images from the
persisted file. The saved file has zero images, Text blocks, fonts, sounds,
movie clips, cache files, volumes, point clouds, curves, armatures, lattices,
metaballs, grease-pencil data, palettes, paint curves, actions, node groups,
libraries, linked/overridden data, and packed items. Materials use only their
declared constant base color and no external texture or custom node group.
Scene compositor nodes, file-output nodes, sequencer strips, add-ons, custom
properties, and executable/script carriers are absent.

### 6.3 Independent closed inspector

The worker renders the preview/final PNG, removes transient render-result data,
saves the derived `.blend`, and writes a bounded worker result. Its own
inventory claim is not sufficient. After it exits, the host invokes separately
reviewed `inspect_scene.py` against the saved file with factory startup,
autoexec disabled, offline mode, and the same native process caps.

The inspector schema has exact keys and counts. It compares every Blender
datablock collection against the `coliseum-smoke.v1` allowlist; collections not
explicitly created by the profile must equal the recorded factory-startup
baseline by name/type fingerprint. Unknown datablock collections, keys, types,
names, links, or counts refuse. It independently rejects:

- any Text/script/executable carrier, driver, scripted expression, add-on, or
  non-baseline application handler;
- any packed item of any type, including non-executable packed data;
- any external, linked, appended-with-external-reference, library, image,
  font, sound, movie, cache, volume, or other file-backed content;
- any compositor node tree or file-output node, sequencer content, node group,
  custom property, modifier, constraint, particle/physics/simulation content,
  action, animation data, or undeclared datablock/content class;
- any path/file reference other than the already-validated `.blend` input; and
- any drift in render settings, object relations, geometry counts/bounds,
  transforms, materials, camera, light, world, factory handler baseline, or
  exact resource profile.

All `bpy.app.handlers` lists are fingerprinted immediately after factory
startup and again after the file opens; any added, replaced, persistent, or
otherwise non-baseline handler refuses. All types exposing `packed_file` or
`packed_files` are traversed and must report zero. A manifest cannot exist
unless the host validates this independent closed report. A scene object is not
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
- a job spec with unknown keys, unknown enums, any value outside the exact
  `coliseum-smoke.v1` profile, or an unsafe path;
- inability to prove the section-4.1 WSL/Windows identity, an unavailable
  reparse detector/path guard, any symlink/junction/reparse/UNC/case/device/
  alternate-stream alias, protected-root identity, component swap, output
  overwrite, or file not declared by the job;
- nonzero exit, timeout, missing terminal progress, missing/empty output,
  resource-cap breach, invalid PNG, invalid/extra scene content, inspector
  baseline drift, hash mismatch, or unexpected file;
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
3. one-pass job identity construction with the real `ContentRecord`, exact
   `jobs/<job_id>` derivation and reload, strict schema/profile, and rejection of
   an ID-dependent preimage directory, mismatched leaf, placeholder
   substitution, deterministic-setting drift, and immutable-input drift;
4. host-only path-verifier cases for unavailable reparse detection, junction/
   reparse escape, UNC/drive/case/device/alternate-stream and protected-root
   aliases, Linux symlinks, component swaps, safe fresh-leaf creation, Windows
   handle identity, WSL round trip, overwrite, and undeclared files; every
   indeterminate case refuses before Blender and creates no output;
5. progress sequence/stage monotonicity, malformed/truncated/oversized telemetry,
   preview hash mismatch, and failure terminals;
6. loopback capability, Host checks, security headers, method refusal, no raw
   path/job selection, safe text, and no arbitrary command/Python endpoint;
7. actor-safe projection before asset resolution and physical absence of private,
   hidden, raw-completion, evaluator, and Council fields;
8. nonzero exit, timeout, every exact resource-cap breach, missing output,
   invalid PNG, invalid inventory, and unexpected output fail closed without a
   manifest;
9. manifest hashes, relative paths, Blender/script/template/asset binding,
   presentation-only declaration, and no status promotion;
10. canonical run bundle hashes and Council tree state remain byte-identical;
11. accessibility and reduced-motion behavior;
12. normal visualization, replay, and repository tests pass with Blender absent.

Ordinary CI also uses strict inspector-report fixtures to reject unknown keys or
classes, wrong counts/types/relations, profile drift, and one case each for
Text/script content, drivers, handlers, all packed content, external libraries
and files, compositor/file output, images/fonts/audio/cache data, node groups,
custom properties, modifiers/constraints, animation, simulation content, and an
otherwise valid but undeclared datablock. The opt-in Blender test constructs
representative prohibited `.blend` files for Text, driver, handler, packed,
external-library/file, compositor-output, and undeclared-datablock cases and
requires independent refusal.

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

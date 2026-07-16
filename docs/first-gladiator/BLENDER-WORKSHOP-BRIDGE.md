# Blender Workshop bridge — design source

Status: **DESIGN ONLY — REVISION 005**. This source authorizes no Blender execution, repository
implementation, projection of a canonical run, visual claim, asset admission,
or Council integration. Implementation and the first render proof require a
separately routed source after this design receives the applicable plain Council
verdict. This revision preserves the blocked revision-001 through revision-004
lineage at Council events `001433-d1bfc40f`, `001438-4a9b7d49`,
`001443-8cc845bb`, and `001448-1affc34a`. Revision 002 closed
job identity/path recursion, fail-open Windows alias handling, and the inspector's
open prohibited-class set. Revision 003 closes the remaining independently
reproduced profile-value incompleteness, reviewed-script check/use race, and
worker-result validation gap. Revision 004 closes the independently reproduced
inventory-construction, mesh/collection/view-layer value-surface, and launch-
attestation normalization gaps without changing the execution boundary.
Revision 005 closes the independently reproduced open render-manifest schema and
auxiliary held-ancestor checksum-preimage gaps without changing the execution
boundary.

Council request: `first-gladiator-blender-workshop-design-002`, document revision
`005`. Re-audit follows `FIX_STARTED -> READY_FOR_REAUDIT` on that existing blocked
request so events `001438-4a9b7d49`, `001443-8cc845bb`, and
`001448-1affc34a` remain its direct audit lineage; no request or
commit history is rewritten.

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
  --python <guarded-staged-smoke-script-windows-path> --
  --job-spec <validated-job-spec-windows-path>
  --launch-attestation <guarded-worker-launch-attestation-windows-path>
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
  profiles/
    coliseum-smoke.v1.json
    blender-5.2.0-factory-profile.json
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
  input/
    smoke_scene.py
    inspect_scene.py
    factory-profile.json
  job.json
  worker-launch-attestation.json
  inspector-launch-attestation.json
  progress.json
  events.jsonl
  preview.png
  render.png
  scene.blend
  worker-result.json
  inspector-report.json
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
5. The Windows guard retains non-delete-shared handles for the derived root, job
   directory, `input` directory, both staged scripts, factory-profile input, and job
   specification for the complete sequential worker/inspector child lifetimes. Input files are opened with
   `FILE_SHARE_READ` only (no write/delete sharing); every component's volume/file
   identity is recorded. It launches only the bound Blender executable and exact
   argument array while those handles are held. This prevents an ancestor,
   input, job-directory component, or verified file from being replaced or
   modified between validation and Blender's pathname open.
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
- reviewed worker/inspector script relative paths and SHA-256 values;
- fixed staged worker/inspector relative paths and the same SHA-256 values;
- closed factory-profile relative path and SHA-256;
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
reviewed_scripts                # {worker: {source_relative_path, sha256,
                                #            staged_relative_path},
                                #  inspector: same exact keys}
factory_profile_binding         # {source_relative_path, staged_relative_path,
                                #  sha256, blender_identity}
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

Before computing the job, the host opens both allowlisted repository scripts and exact
tracked factory/profile fixtures by no-follow descriptors and verifies their
repository-relative identities and digests. It then computes `job_id`, derives and
creates the fresh `jobs/<job_id>` and `input` directories through held parents, and
copies source bytes descriptor-to-descriptor into the fixed staged paths with
create-exclusive semantics. It flushes each copy, rehashes it, and requires equality
with the job-bound source digests. Source pathnames are never passed to Blender. The
Windows guard then opens both staged scripts and every input/path component by native handle, denies
write/delete sharing, records final file identity, and holds those handles until the
worker-and-inspector sequence ends. It performs the same protocol for
`factory-profile.json` and `job.json`.
The job preimage binds only the id-independent staged relative path and digest; it
does not bind a native file identity that can exist only after the `jobs/<job_id>`
directory is derived. A source or source-ancestor replacement after staging is
irrelevant; a staged-file or staged-ancestor replacement/modification is blocked by
the held native handles and must prevent child launch if attempted or indeterminate.

After `job_id` and all staged inputs exist, the host creates
`blender_worker_launch_attestation.v1`. Its exact preimage keys are:

```text
launch_attestation_schema_version   # literal 1
job_id
blender_executable                  # {volume_serial_number, file_id_hex,
                                    #  byte_count, sha256, blender_identity}
staged_worker_script                # {relative_path, volume_serial_number,
                                    #  file_id_hex, byte_count, sha256}
factory_profile                     # same exact file keys
job_spec                            # same exact file keys
held_ancestors                      # canonically ordered [{role, volume_serial_number,
                                    #          file_id_hex}]
argument_array_sha256
native_guard_version
sharing_policy                      # literal read-only-no-write-delete-share.v1
```

The worker attestation id is computed once and the fixed file
`worker-launch-attestation.json` is written atomically. The host reopens and holds it;
worker result and render manifest bind its id. After successful worker-result/output
validation, the host opens `scene.blend` by no-follow Linux and Windows handles,
verifies its worker-declared and independently computed size/digest, denies
write/delete sharing, and creates `blender_inspector_launch_attestation.v1` with
exact keys:

```text
launch_attestation_schema_version   # literal 1
job_id
worker_launch_attestation_id
blender_executable                  # same exact executable keys
staged_inspector_script             # same exact file keys
factory_profile                     # same exact file keys
job_spec                            # same exact file keys
scene_blend                         # same file keys; fixed relative path scene.blend
held_ancestors                      # canonically ordered exact identity rows
argument_array_sha256
native_guard_version
sharing_policy                      # literal read-only-no-write-delete-share.v1
```

The inspector attestation is computed once, written to the fixed
`inspector-launch-attestation.json`, reopened, and held through inspector exit. The
inspector argument array names only the guarded staged inspector, job spec, inspector
attestation, factory profile, and scene file. Inspector report and render manifest
bind its id. No inspector launches before this second attestation exists.

For both records, `native_guard_version` is the literal
`wsl-windows-native-guard.v1`. Relative paths are fixed by this design; each digest is 64
lowercase hex, each `file_id_hex` is the 32-lowercase-hex encoding of `FILE_ID_128`,
byte counts and volume serial numbers are non-negative JSON integers (not booleans),
and `blender_identity` has the exact section-5 nested schema. Unknown/missing keys,
duplicate ancestor roles/identities, a path outside the fixed job layout, or any
mismatch refuses. `argument_array_sha256` is exactly
`sha256(UTF-8(schema.canonical_json(argument_array)))`: the argument array is a
JSON list of exact strings in process order, encoded as UTF-8 with no BOM or
trailing newline. No path, Unicode, slash, case, or environment normalization is
performed after the native paths are validated. `held_ancestors_sha256` is exactly
`sha256(UTF-8(schema.canonical_json(held_ancestors)))` after validation and sorting,
using the same strict UTF-8, no-BOM, no-trailing-newline encoding and no
post-validation normalization. Pretty-printed JSON, a BOM, a trailing newline,
NUL-delimited rows, or any other byte representation cannot satisfy this checksum.
`held_ancestors` is sorted by the
total key `(UTF-8 bytes of role, volume_serial_number as an unsigned integer,
UTF-8 bytes of lowercase file_id_hex)` ascending; identical full keys and duplicate
roles refuse. The worker record uses ContentRecord domain
`blender_worker_launch_attestation.v1` and own id field
`worker_launch_attestation_id`; the inspector uses domain
`blender_inspector_launch_attestation.v1` and own id field
`inspector_launch_attestation_id`. The applicable output id is excluded exactly once by
`ContentRecord` and never occurs in its preimage. Runtime timestamps/handle values
are nonidentity telemetry. Any identity/digest/argument change after its attestation
refuses that launch.

The following fixed construction vector is normative. Its paths and repeated hex
values are fixture data only, but its canonical encodings, ordering, domains, own-id
exclusions, digests, and resulting ids are permanent regressions. Independent
construction and reload must reproduce every literal; changing one argument, ancestor
row/value/order, or preimage field must change the applicable id or refuse.

```json
{
  "argument_array_encoding": "sha256(UTF-8(schema.canonical_json(argv)))",
  "held_ancestors": [
    {
      "file_id_hex": "11111111111111111111111111111111",
      "role": "input_directory",
      "volume_serial_number": 1
    },
    {
      "file_id_hex": "22222222222222222222222222222222",
      "role": "job_directory",
      "volume_serial_number": 1
    }
  ],
  "held_ancestors_sha256": "be46a173345c5c6feeac0e54e4dc649b566028cabfd1fd159fe6ac9f1e55fb3c",
  "inspector_argument_array": [
    "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe",
    "--background",
    "--factory-startup",
    "--disable-autoexec",
    "--offline-mode",
    "-noaudio",
    "--python-exit-code",
    "17",
    "--python",
    "C:\\repo\\derived\\jobs\\7070707070707070707070707070707070707070707070707070707070707070\\input\\inspect_scene.py",
    "--",
    "--job-spec",
    "C:\\repo\\derived\\jobs\\7070707070707070707070707070707070707070707070707070707070707070\\job.json",
    "--launch-attestation",
    "C:\\repo\\derived\\jobs\\7070707070707070707070707070707070707070707070707070707070707070\\inspector-launch-attestation.json",
    "--scene",
    "C:\\repo\\derived\\jobs\\7070707070707070707070707070707070707070707070707070707070707070\\scene.blend",
    "--result",
    "C:\\repo\\derived\\jobs\\7070707070707070707070707070707070707070707070707070707070707070\\inspector-result.json"
  ],
  "inspector_argument_array_sha256": "6e0032f60911008b070f799157733fb055ca68f2464e6f2d2f335011a50ba0ca",
  "inspector_launch_attestation_id": "2aca6cd643b811aa2d9abc544663f6c939382e94ef80ac26e0861ec129f4424e",
  "inspector_preimage": {
    "argument_array_sha256": "6e0032f60911008b070f799157733fb055ca68f2464e6f2d2f335011a50ba0ca",
    "blender_executable": {
      "blender_identity": {
        "build_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "platform": "Windows",
        "version": "5.2.0"
      },
      "byte_count": 100,
      "file_id_hex": "01010101010101010101010101010101",
      "sha256": "1010101010101010101010101010101010101010101010101010101010101010",
      "volume_serial_number": 1
    },
    "factory_profile": {
      "byte_count": 103,
      "file_id_hex": "04040404040404040404040404040404",
      "relative_path": "input/factory-profile.json",
      "sha256": "4040404040404040404040404040404040404040404040404040404040404040",
      "volume_serial_number": 1
    },
    "held_ancestors": [
      {
        "file_id_hex": "11111111111111111111111111111111",
        "role": "input_directory",
        "volume_serial_number": 1
      },
      {
        "file_id_hex": "22222222222222222222222222222222",
        "role": "job_directory",
        "volume_serial_number": 1
      }
    ],
    "job_id": "7070707070707070707070707070707070707070707070707070707070707070",
    "job_spec": {
      "byte_count": 104,
      "file_id_hex": "05050505050505050505050505050505",
      "relative_path": "job.json",
      "sha256": "5050505050505050505050505050505050505050505050505050505050505050",
      "volume_serial_number": 1
    },
    "launch_attestation_schema_version": 1,
    "native_guard_version": "wsl-windows-native-guard.v1",
    "scene_blend": {
      "byte_count": 105,
      "file_id_hex": "06060606060606060606060606060606",
      "relative_path": "scene.blend",
      "sha256": "6060606060606060606060606060606060606060606060606060606060606060",
      "volume_serial_number": 1
    },
    "sharing_policy": "read-only-no-write-delete-share.v1",
    "staged_inspector_script": {
      "byte_count": 102,
      "file_id_hex": "03030303030303030303030303030303",
      "relative_path": "input/inspect_scene.py",
      "sha256": "3030303030303030303030303030303030303030303030303030303030303030",
      "volume_serial_number": 1
    },
    "worker_launch_attestation_id": "e68207158627944ef9e584adf5d6089454d8da778a1d554aec0f943c6b6ed418"
  },
  "worker_argument_array": [
    "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe",
    "--background",
    "--factory-startup",
    "--disable-autoexec",
    "--offline-mode",
    "-noaudio",
    "--python-exit-code",
    "17",
    "--python",
    "C:\\repo\\derived\\jobs\\7070707070707070707070707070707070707070707070707070707070707070\\input\\smoke_scene.py",
    "--",
    "--job-spec",
    "C:\\repo\\derived\\jobs\\7070707070707070707070707070707070707070707070707070707070707070\\job.json",
    "--launch-attestation",
    "C:\\repo\\derived\\jobs\\7070707070707070707070707070707070707070707070707070707070707070\\worker-launch-attestation.json"
  ],
  "worker_argument_array_sha256": "299acb851ead7a64505ffb48b95d3cd30901392b71f14ed57b062739c9e64860",
  "worker_launch_attestation_id": "e68207158627944ef9e584adf5d6089454d8da778a1d554aec0f943c6b6ed418",
  "worker_preimage": {
    "argument_array_sha256": "299acb851ead7a64505ffb48b95d3cd30901392b71f14ed57b062739c9e64860",
    "blender_executable": {
      "blender_identity": {
        "build_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "platform": "Windows",
        "version": "5.2.0"
      },
      "byte_count": 100,
      "file_id_hex": "01010101010101010101010101010101",
      "sha256": "1010101010101010101010101010101010101010101010101010101010101010",
      "volume_serial_number": 1
    },
    "factory_profile": {
      "byte_count": 103,
      "file_id_hex": "04040404040404040404040404040404",
      "relative_path": "input/factory-profile.json",
      "sha256": "4040404040404040404040404040404040404040404040404040404040404040",
      "volume_serial_number": 1
    },
    "held_ancestors": [
      {
        "file_id_hex": "11111111111111111111111111111111",
        "role": "input_directory",
        "volume_serial_number": 1
      },
      {
        "file_id_hex": "22222222222222222222222222222222",
        "role": "job_directory",
        "volume_serial_number": 1
      }
    ],
    "job_id": "7070707070707070707070707070707070707070707070707070707070707070",
    "job_spec": {
      "byte_count": 104,
      "file_id_hex": "05050505050505050505050505050505",
      "relative_path": "job.json",
      "sha256": "5050505050505050505050505050505050505050505050505050505050505050",
      "volume_serial_number": 1
    },
    "launch_attestation_schema_version": 1,
    "native_guard_version": "wsl-windows-native-guard.v1",
    "sharing_policy": "read-only-no-write-delete-share.v1",
    "staged_worker_script": {
      "byte_count": 101,
      "file_id_hex": "02020202020202020202020202020202",
      "relative_path": "input/smoke_scene.py",
      "sha256": "2020202020202020202020202020202020202020202020202020202020202020",
      "volume_serial_number": 1
    }
  }
}
```

The host writes `job.json` atomically before execution and opens it through the
guarded no-follow directory. Immediately before each launch it rereads the applicable staged script,
factory profile, and job spec through their already-held handles, rechecks digests
and identities, and passes only that guarded staged Windows script pathname. The
worker verifies the job schema, job id, staged-script digest binding, factory-profile
binding, launch-attestation id/bindings, job kind, output confinement, and closed enum values before constructing a
scene. The host refuses if Blender cannot open the held file under the required
sharing mode; it never relaxes the guard.

## 6. Smoke scene

The initial closed profile is `coliseum-smoke.v1`. Implementations may not tune
it under the same version.

### 6.1 Exact render and resource profile

`render_profile` is the following closed canonical JSON object. Key spelling,
nesting, enum case, JSON type, array length, and value are normative. Integers are
not accepted for fields typed `number`; booleans are not integers. Unknown/missing
keys, `NaN`/infinity, unsupported/renamed Blender properties, or a normalized value
that differs after assignment refuses before rendering.

```json
{
  "profile_version": "coliseum-smoke.v1",
  "frame": {"start": 1, "end": 1, "step": 1, "current": 1, "fps": 24, "fps_base": 1.0},
  "preview": {"width": 640, "height": 360, "percentage": 100, "samples": 16},
  "final": {"width": 1280, "height": 720, "percentage": 100, "samples": 16},
  "render": {
    "engine": "CYCLES", "feature_set": "SUPPORTED", "device": "CPU",
    "threads_mode": "FIXED", "threads": 1, "use_file_extension": true,
    "use_overwrite": false, "use_placeholder": false, "use_compositing": false,
    "use_sequencer": false, "use_single_layer": true, "use_multiview": false,
    "views_format": "STEREO_3D", "dither_intensity": 1.0, "film_transparent": false,
    "film_transparent_glass": false, "film_transparent_roughness": 0.0,
    "use_motion_blur": false, "use_stamp": false, "use_border": false,
    "use_crop_to_border": false, "pixel_aspect_x": 1.0, "pixel_aspect_y": 1.0
  },
  "image": {
    "file_format": "PNG", "color_mode": "RGBA", "color_depth": "8",
    "compression": 15, "color_management": "FOLLOW_SCENE", "use_preview": false
  },
  "color_management": {
    "display_device": "sRGB", "view_transform": "Standard", "look": "None",
    "exposure": 0.0, "gamma": 1.0, "use_curve_mapping": false,
    "use_white_balance": false, "temperature": 6500.0, "tint": 10.0,
    "sequencer_colorspace": "sRGB"
  },
  "cycles": {
    "seed": 0, "use_animated_seed": false, "samples": 16,
    "preview_samples": 16, "use_adaptive_sampling": false,
    "adaptive_threshold": 0.0, "adaptive_min_samples": 0,
    "use_denoising": false, "use_preview_denoising": false,
    "denoiser": "OPENIMAGEDENOISE", "preview_denoiser": "AUTO",
    "use_persistent_data": false, "use_light_tree": false,
    "use_guiding": false, "use_camera_cull": false, "use_distance_cull": false,
    "use_auto_tile": false, "caustics_reflective": false,
    "caustics_refractive": false, "max_bounces": 4, "min_bounces": 0,
    "diffuse_bounces": 2, "glossy_bounces": 2, "transmission_bounces": 2,
    "volume_bounces": 2, "transparent_max_bounces": 2,
    "transparent_min_bounces": 0, "ao_bounces": 0, "ao_bounces_render": 0,
    "sample_clamp_direct": 0.0, "sample_clamp_indirect": 0.0,
    "blur_glossy": 1.0, "filter_type": "BLACKMAN_HARRIS",
    "filter_width": 1.5, "light_sampling_threshold": 0.01,
    "volume_step_rate": 1.0, "volume_preview_step_rate": 1.0,
    "volume_max_steps": 1024
  },
  "camera": {
    "object": {
      "name": "SMOKE_CAMERA", "location": [9.0, -11.0, 11.0],
      "rotation_mode": "XYZ", "rotation_euler": [0.872665, 0.0, 0.698132],
      "scale": [1.0, 1.0, 1.0], "delta_location": [0.0, 0.0, 0.0],
      "delta_rotation_euler": [0.0, 0.0, 0.0], "delta_scale": [1.0, 1.0, 1.0],
      "parent": null, "hide_render": false, "hide_viewport": false,
      "is_holdout": false, "is_shadow_catcher": false, "pass_index": 0,
      "instance_type": "NONE", "show_instancer_for_render": true, "visible_camera": true,
      "visible_shadow": true, "visible_diffuse": true, "visible_glossy": true,
      "visible_transmission": true, "visible_volume_scatter": true
    },
    "data": {
      "name": "SMOKE_CAMERA_DATA", "type": "ORTHO", "ortho_scale": 19.0,
      "clip_start": 0.1, "clip_end": 100.0, "shift_x": 0.0, "shift_y": 0.0,
      "lens": 50.0, "lens_unit": "MILLIMETERS", "sensor_fit": "AUTO",
      "sensor_width": 36.0, "sensor_height": 32.0, "dof_enabled": false,
      "dof_focus_object": null, "dof_focus_distance": 10.0,
      "dof_aperture_fstop": 2.8, "dof_aperture_blades": 0,
      "dof_aperture_rotation": 0.0, "dof_aperture_ratio": 1.0,
      "panorama_type": "EQUIRECTANGULAR", "stereo_convergence_mode": "OFFAXIS",
      "stereo_convergence_distance": 30.0, "stereo_interocular_distance": 0.065,
      "stereo_pivot": "LEFT", "stereo_use_spherical": false,
      "stereo_use_pole_merge": false, "stereo_pole_merge_angle_from": 1.047198,
      "stereo_pole_merge_angle_to": 1.308997
    }
  },
  "world": {"name": "SMOKE_WORLD", "use_nodes": false, "color": [0.03, 0.03, 0.03]},
  "sun": {
    "object": {
      "name": "SMOKE_SUN", "location": [0.0, 0.0, 8.0],
      "rotation_mode": "XYZ", "rotation_euler": [0.523599, -0.349066, -0.523599],
      "scale": [1.0, 1.0, 1.0], "delta_location": [0.0, 0.0, 0.0],
      "delta_rotation_euler": [0.0, 0.0, 0.0], "delta_scale": [1.0, 1.0, 1.0],
      "parent": null, "hide_render": false, "hide_viewport": false,
      "is_holdout": false, "is_shadow_catcher": false, "pass_index": 0,
      "instance_type": "NONE", "show_instancer_for_render": true, "visible_camera": true,
      "visible_shadow": true, "visible_diffuse": true, "visible_glossy": true,
      "visible_transmission": true, "visible_volume_scatter": true
    },
    "data": {
      "name": "SMOKE_SUN_DATA", "type": "SUN", "color": [1.0, 1.0, 1.0],
      "energy": 2.0, "angle": 0.0872665, "use_nodes": false,
      "use_shadow": true,
      "diffuse_factor": 1.0, "specular_factor": 1.0,
      "transmission_factor": 1.0, "volume_factor": 1.0,
      "use_custom_distance": false, "cutoff_distance": 40.0,
      "shadow_soft_size": 0.25, "shape": "SQUARE", "size": 0.25,
      "size_y": 0.25, "spot_size": 0.785398, "spot_blend": 0.15,
      "show_cone": false
    }
  },
  "resource_caps": {
    "job_json_bytes": 65536, "factory_profile_bytes": 1048576,
    "progress_json_bytes": 32768, "event_count": 128,
    "events_jsonl_bytes": 131072, "worker_result_bytes": 65536,
    "inspector_report_bytes": 65536, "render_manifest_bytes": 131072,
    "preview_png_bytes": 8388608, "final_png_bytes": 33554432,
    "blend_bytes": 67108864, "stdout_bytes": 1048576, "stderr_bytes": 1048576,
    "job_directory_bytes": 134217728, "max_concurrent_child_processes": 1,
    "max_total_child_launches": 2,
    "render_threads": 1, "process_memory_bytes": 4294967296,
    "process_cpu_seconds": 180, "host_wall_seconds": 180
  }
}
```

Using the integrated `schema.canonical_json` byte serialization, the exact object
above has `render_profile_sha256 =
58ef3569c2bb2bd3e593876a38be6898abde20d488a238b9878a7e7ce77d83bb`.
The job constructor recomputes and requires that literal digest; an implementation
cannot bind a different object under the same profile version.

The worker assigns and reads back every field above. `factory-profile.json` is a
closed canonical snapshot produced during the separately audited implementation
preflight from the exact `blender_identity` under `--factory-startup`; it enumerates
every remaining writable RNA property in Scene/RenderSettings/Cycles/ViewSettings/
DisplaySettings/ImageFormatSettings/Camera/Light/World/Material/Object/Mesh/
MeshVertex/MeshEdge/MeshLoop/MeshPolygon/Collection/ViewLayer/LayerCollection and every
datablock collection/handler baseline not explicitly overridden above. Each row is
`{rna_type, property_identifier, normalized_json_type, normalized_value}` in sorted
order; pointers and volatile/runtime/read-only fields are excluded by a closed
allowlist named in the fixture. Its raw bytes and SHA-256 are committed with the
implementation source, and that exact SHA-256 plus Blender identity enters every
job preimage. A missing/extra property, different value, different exclusion set, or
different digest refuses. Thus an implementation cannot choose its own defaults
under `coliseum-smoke.v1`; explicitly assigned values plus one exact bound factory
fingerprint exhaust the value surface.

The same-host output hash is recorded, but the design makes no bit-identical
portability claim across Blender builds, drivers, CPUs, or GPUs. A Windows Job
Object or equivalently strong native boundary enforces the exact caps above; if the
host cannot apply one, execution refuses. Exceeding any cap terminates the derived
job and forbids a manifest.

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

The ground is one procedural plane; rooms are three procedural cubes; agents are
three procedural cylinders. The expected-inventory canonical object is the fully
expanded literal below; the preceding tables and compact construction aid are only
human review aids and the implementation may not generate a substitute from them.
Its raw canonical JSON SHA-256 enters
`expected_inventory_digest`.

Every object's closed transform record has exactly
`{name, data_name, collection, location, rotation_mode, rotation_euler, scale,
delta_location, delta_rotation_euler, delta_scale, parent, hide_render,
hide_viewport, is_holdout, is_shadow_catcher, visible_camera, visible_shadow,
visible_diffuse, visible_glossy, visible_transmission, visible_volume_scatter,
pass_index, instance_type, show_instancer_for_render, material_names}`. For all nine objects: `collection` is
`COLISEUM_SMOKE`, `rotation_mode` is `XYZ`, `scale` and `delta_scale` are
`[1.0,1.0,1.0]`, all rotations/delta rotations/delta locations are `[0.0,0.0,0.0]`
except the camera/sun rotations and sun location fixed in section 6.1, `parent` is
null, both hide/holdout/shadow-catcher flags are false, all six visibility flags and
`show_instancer_for_render` are true, `pass_index` is `0`, `instance_type` is `NONE`,
camera/sun `material_names` is empty, and mesh
objects have exactly their one table material. Camera/sun object values must be
byte-equal to section 6.1 rather than independently defaulted.

| Object | Data | Location | Material | Mesh construction |
|---|---|---|---|---|
| `SMOKE_GROUND` | `SMOKE_GROUND` | `[0.0,0.0,0.0]` | `MAT_GROUND` | plane, size `18.0`, enter-edit false, align `WORLD`; 4 vertices/4 edges/1 polygon; local vertices exactly `[-9,-9,0],[-9,9,0],[9,-9,0],[9,9,0]` as a sorted set |
| `SMOKE_ROOM_A` | `SMOKE_ROOM_A` | `[-5.0,0.0,0.2]` | `MAT_ROOM_A` | cube with applied local dimensions `[4.0,6.0,0.4]`; 8 vertices/12 edges/6 polygons; bounds `[-2,-3,-0.2]..[2,3,0.2]` |
| `SMOKE_ROOM_B` | `SMOKE_ROOM_B` | `[0.0,0.0,0.2]` | `MAT_ROOM_B` | same exact cube mesh construction |
| `SMOKE_ROOM_C` | `SMOKE_ROOM_C` | `[5.0,0.0,0.2]` | `MAT_ROOM_C` | same exact cube mesh construction |
| `SMOKE_AGENT_ADA` | `SMOKE_AGENT_ADA` | `[-5.0,0.0,1.1]` | `MAT_AGENT_ADA` | cylinder vertices `16`, radius `0.45`, depth `1.4`, end-fill `NGON`, align `WORLD`; 32 vertices/48 edges/18 polygons |
| `SMOKE_AGENT_BO` | `SMOKE_AGENT_BO` | `[0.0,0.0,1.1]` | `MAT_AGENT_BO` | same exact cylinder construction |
| `SMOKE_AGENT_CY` | `SMOKE_AGENT_CY` | `[5.0,0.0,1.1]` | `MAT_AGENT_CY` | same exact cylinder construction |
| `SMOKE_CAMERA` | `SMOKE_CAMERA_DATA` | `[9.0,-11.0,11.0]` | none | no mesh; exact object/data record in section 6.1 |
| `SMOKE_SUN` | `SMOKE_SUN_DATA` | `[0.0,0.0,8.0]` | none | no mesh; exact object/data record in section 6.1 |

Cubes and cylinders are explained here only to aid review; the fully expanded
normalized arrays in the normative JSON control on any discrepancy. Cube vertices
are the Cartesian product of the two exact bounds on each axis. A
cylinder's canonical local-vertex multiset is
`[round(0.45*cos(2*pi*k/16),12), round(0.45*sin(2*pi*k/16),12), z]` for integer
`k=0..15` and `z` in `[-0.7,0.7]`; the inspector sorts these triples and binds
edge/polygon topology. The literal sorted vertices, edges, polygon cycles, winding,
per-polygon smooth flags, per-edge sharp flags, custom-normal absence, and loop-normal
source in the normative inventory—not Blender's incidental insertion order—define
the expected geometry. Mesh transforms are applied before inspection; object scale
remains exactly one.

The seven material records have exactly
`{name, diffuse_color, use_nodes, surface_render_method, use_backface_culling,
node_tree}` with `use_nodes: true`, `surface_render_method: "DITHERED"`, and
`use_backface_culling: false`. Their RGBA values are:

| Material | `diffuse_color` and Diffuse-BSDF `Color` |
|---|---|
| `MAT_GROUND` | `[0.36,0.22,0.10,1.0]` |
| `MAT_ROOM_A` | `[0.65,0.53,0.34,1.0]` |
| `MAT_ROOM_B` | `[0.55,0.55,0.58,1.0]` |
| `MAT_ROOM_C` | `[0.70,0.64,0.50,1.0]` |
| `MAT_AGENT_ADA` | `[0.72,0.16,0.12,1.0]` |
| `MAT_AGENT_BO` | `[0.12,0.34,0.72,1.0]` |
| `MAT_AGENT_CY` | `[0.16,0.58,0.24,1.0]` |

The following compact JSON is a **non-normative construction aid** retained only to
make the repeated scene values readable in review. It is never hashed, accepted as a
job input, or expanded by an implementation. References and placeholders in this aid
have no identity authority; the fully expanded canonical value immediately below is
the only expected inventory.

```json
{
  "inventory_schema_version": "coliseum-smoke.inventory.v1",
  "counts": {
    "scenes": 1, "view_layers": 1, "master_collections": 1,
    "collections": 1, "objects": 9, "meshes": 7, "materials": 7,
    "cameras": 1, "lights": 1, "worlds": 1
  },
  "scene": {
    "name": "Scene", "view_layer": "ViewLayer", "camera": "SMOKE_CAMERA",
    "world": "SMOKE_WORLD", "master_collection": "Scene Collection",
    "child_collections": ["COLISEUM_SMOKE"]
  },
  "object_defaults": {
    "collection": "COLISEUM_SMOKE", "rotation_mode": "XYZ",
    "rotation_euler": [0.0,0.0,0.0], "scale": [1.0,1.0,1.0],
    "delta_location": [0.0,0.0,0.0],
    "delta_rotation_euler": [0.0,0.0,0.0], "delta_scale": [1.0,1.0,1.0],
    "parent": null, "hide_render": false, "hide_viewport": false,
    "is_holdout": false, "is_shadow_catcher": false,
    "visible_camera": true, "visible_shadow": true, "visible_diffuse": true,
    "visible_glossy": true, "visible_transmission": true,
    "visible_volume_scatter": true, "pass_index": 0, "instance_type": "NONE",
    "show_instancer_for_render": true
  },
  "objects": [
    {"name":"SMOKE_GROUND","data_name":"SMOKE_GROUND","location":[0.0,0.0,0.0],"materials":["MAT_GROUND"]},
    {"name":"SMOKE_ROOM_A","data_name":"SMOKE_ROOM_A","location":[-5.0,0.0,0.2],"materials":["MAT_ROOM_A"]},
    {"name":"SMOKE_ROOM_B","data_name":"SMOKE_ROOM_B","location":[0.0,0.0,0.2],"materials":["MAT_ROOM_B"]},
    {"name":"SMOKE_ROOM_C","data_name":"SMOKE_ROOM_C","location":[5.0,0.0,0.2],"materials":["MAT_ROOM_C"]},
    {"name":"SMOKE_AGENT_ADA","data_name":"SMOKE_AGENT_ADA","location":[-5.0,0.0,1.1],"materials":["MAT_AGENT_ADA"]},
    {"name":"SMOKE_AGENT_BO","data_name":"SMOKE_AGENT_BO","location":[0.0,0.0,1.1],"materials":["MAT_AGENT_BO"]},
    {"name":"SMOKE_AGENT_CY","data_name":"SMOKE_AGENT_CY","location":[5.0,0.0,1.1],"materials":["MAT_AGENT_CY"]},
    {"name":"SMOKE_CAMERA","record_ref":"render_profile.camera","materials":[]},
    {"name":"SMOKE_SUN","record_ref":"render_profile.sun","materials":[]}
  ],
  "geometry_normalization": {
    "coordinate_round_digits": 12, "vertex_order": "sorted_lexicographic",
    "edge_order": "sorted_endpoint_pairs", "polygon_order": "sorted_vertex_cycles"
  },
  "meshes": [
    {"names":["SMOKE_GROUND"],"primitive":"plane","parameters":{"size":18.0,"align":"WORLD"},
     "vertex_count":4,"edge_count":4,"polygon_count":1,
     "sorted_vertices":[[-9.0,-9.0,0.0],[-9.0,9.0,0.0],[9.0,-9.0,0.0],[9.0,9.0,0.0]]},
    {"names":["SMOKE_ROOM_A","SMOKE_ROOM_B","SMOKE_ROOM_C"],"primitive":"cube",
     "parameters":{"dimensions":[4.0,6.0,0.4],"align":"WORLD","transform_applied":true},
     "vertex_count":8,"edge_count":12,"polygon_count":6,
     "local_bounds":{"minimum":[-2.0,-3.0,-0.2],"maximum":[2.0,3.0,0.2]}},
    {"names":["SMOKE_AGENT_ADA","SMOKE_AGENT_BO","SMOKE_AGENT_CY"],"primitive":"cylinder",
     "parameters":{"vertices":16,"radius":0.45,"depth":1.4,"end_fill":"NGON","align":"WORLD"},
     "vertex_count":32,"edge_count":48,"polygon_count":18,
     "vertex_formula":"[round(0.45*cos(2*pi*k/16),12),round(0.45*sin(2*pi*k/16),12),z] for k=0..15,z in [-0.7,0.7]"}
  ],
  "materials": [
    {"name":"MAT_GROUND","rgba":[0.36,0.22,0.10,1.0]},
    {"name":"MAT_ROOM_A","rgba":[0.65,0.53,0.34,1.0]},
    {"name":"MAT_ROOM_B","rgba":[0.55,0.55,0.58,1.0]},
    {"name":"MAT_ROOM_C","rgba":[0.70,0.64,0.50,1.0]},
    {"name":"MAT_AGENT_ADA","rgba":[0.72,0.16,0.12,1.0]},
    {"name":"MAT_AGENT_BO","rgba":[0.12,0.34,0.72,1.0]},
    {"name":"MAT_AGENT_CY","rgba":[0.16,0.58,0.24,1.0]}
  ],
  "material_defaults": {
    "use_nodes": true, "surface_render_method": "DITHERED",
    "use_backface_culling": false, "diffuse_color_source": "$MATERIAL_RGBA"
  },
  "material_node_template": {
    "nodes": [
      {"name":"Diffuse BSDF","bl_idname":"ShaderNodeBsdfDiffuse","location":[0.0,0.0],
       "width":140.0,"mute":false,"hide":false,
       "inputs":{"Weight":1.0,"Color":"$MATERIAL_RGBA","Roughness":0.65,"Normal":[0.0,0.0,0.0]}},
      {"name":"Material Output","bl_idname":"ShaderNodeOutputMaterial","location":[300.0,0.0],
       "width":140.0,"mute":false,"hide":false,"target":"ALL","is_active_output":true,
       "inputs":{"Surface":{"linked":true},"Volume":{"linked":false,"default":null},
                 "Displacement":{"linked":false,"default":0.0},"Thickness":{"linked":false,"default":0.0}}}
    ],
    "links":[{"from_node":"Diffuse BSDF","from_socket":"BSDF","to_node":"Material Output","to_socket":"Surface"}]
  },
  "zero_per_object_counts": {
    "modifiers": 0, "constraints": 0, "particle_systems": 0,
    "simulation_settings": 0, "animation_data": 0, "drivers": 0,
    "custom_properties": 0
  }
}
```

The following JSON object is the single normative expected inventory. It is already
fully expanded: it has no default merge, reference, alias, placeholder, formula
substitution, or implementation-selected key. Object, material, camera/light data,
collection/view-layer inclusion, vertex, edge, polygon-winding, smoothing, sharp-edge,
and custom-normal values are all literal. The compact aid above cannot override it.

```json
{
  "collections": [
    {
      "children": [],
      "color_tag": "NONE",
      "hide_render": false,
      "hide_viewport": false,
      "instance_offset": [
        0.0,
        0.0,
        0.0
      ],
      "lineart_usage": "INCLUDE",
      "name": "COLISEUM_SMOKE",
      "objects": [
        "SMOKE_GROUND",
        "SMOKE_ROOM_A",
        "SMOKE_ROOM_B",
        "SMOKE_ROOM_C",
        "SMOKE_AGENT_ADA",
        "SMOKE_AGENT_BO",
        "SMOKE_AGENT_CY",
        "SMOKE_CAMERA",
        "SMOKE_SUN"
      ]
    }
  ],
  "counts": {
    "cameras": 1,
    "collections": 1,
    "lights": 1,
    "master_collections": 1,
    "materials": 7,
    "meshes": 7,
    "objects": 9,
    "scenes": 1,
    "view_layers": 1,
    "worlds": 1
  },
  "geometry_normalization": {
    "coordinate_round_digits": 12,
    "edge_order": "sorted_endpoint_pairs",
    "polygon_cycle_rotation": "lowest_vertex_index_first_preserve_winding",
    "polygon_order": "sorted_lexicographic",
    "vertex_order": "sorted_lexicographic"
  },
  "inventory_schema_version": "coliseum-smoke.inventory.v1",
  "master_collection": {
    "children": [
      "COLISEUM_SMOKE"
    ],
    "color_tag": "NONE",
    "hide_render": false,
    "hide_viewport": false,
    "instance_offset": [
      0.0,
      0.0,
      0.0
    ],
    "lineart_usage": "INCLUDE",
    "name": "Scene Collection",
    "objects": []
  },
  "materials": [
    {
      "diffuse_color": [
        0.36,
        0.22,
        0.1,
        1.0
      ],
      "name": "MAT_GROUND",
      "node_tree": {
        "links": [
          {
            "from_node": "Diffuse BSDF",
            "from_socket": "BSDF",
            "to_node": "Material Output",
            "to_socket": "Surface"
          }
        ],
        "nodes": [
          {
            "bl_idname": "ShaderNodeBsdfDiffuse",
            "hide": false,
            "inputs": {
              "Color": [
                0.36,
                0.22,
                0.1,
                1.0
              ],
              "Normal": [
                0.0,
                0.0,
                0.0
              ],
              "Roughness": 0.65,
              "Weight": 1.0
            },
            "location": [
              0.0,
              0.0
            ],
            "mute": false,
            "name": "Diffuse BSDF",
            "width": 140.0
          },
          {
            "bl_idname": "ShaderNodeOutputMaterial",
            "hide": false,
            "inputs": {
              "Displacement": {
                "default": 0.0,
                "linked": false
              },
              "Surface": {
                "linked": true
              },
              "Thickness": {
                "default": 0.0,
                "linked": false
              },
              "Volume": {
                "default": null,
                "linked": false
              }
            },
            "is_active_output": true,
            "location": [
              300.0,
              0.0
            ],
            "mute": false,
            "name": "Material Output",
            "target": "ALL",
            "width": 140.0
          }
        ]
      },
      "surface_render_method": "DITHERED",
      "use_backface_culling": false,
      "use_nodes": true
    },
    {
      "diffuse_color": [
        0.65,
        0.53,
        0.34,
        1.0
      ],
      "name": "MAT_ROOM_A",
      "node_tree": {
        "links": [
          {
            "from_node": "Diffuse BSDF",
            "from_socket": "BSDF",
            "to_node": "Material Output",
            "to_socket": "Surface"
          }
        ],
        "nodes": [
          {
            "bl_idname": "ShaderNodeBsdfDiffuse",
            "hide": false,
            "inputs": {
              "Color": [
                0.65,
                0.53,
                0.34,
                1.0
              ],
              "Normal": [
                0.0,
                0.0,
                0.0
              ],
              "Roughness": 0.65,
              "Weight": 1.0
            },
            "location": [
              0.0,
              0.0
            ],
            "mute": false,
            "name": "Diffuse BSDF",
            "width": 140.0
          },
          {
            "bl_idname": "ShaderNodeOutputMaterial",
            "hide": false,
            "inputs": {
              "Displacement": {
                "default": 0.0,
                "linked": false
              },
              "Surface": {
                "linked": true
              },
              "Thickness": {
                "default": 0.0,
                "linked": false
              },
              "Volume": {
                "default": null,
                "linked": false
              }
            },
            "is_active_output": true,
            "location": [
              300.0,
              0.0
            ],
            "mute": false,
            "name": "Material Output",
            "target": "ALL",
            "width": 140.0
          }
        ]
      },
      "surface_render_method": "DITHERED",
      "use_backface_culling": false,
      "use_nodes": true
    },
    {
      "diffuse_color": [
        0.55,
        0.55,
        0.58,
        1.0
      ],
      "name": "MAT_ROOM_B",
      "node_tree": {
        "links": [
          {
            "from_node": "Diffuse BSDF",
            "from_socket": "BSDF",
            "to_node": "Material Output",
            "to_socket": "Surface"
          }
        ],
        "nodes": [
          {
            "bl_idname": "ShaderNodeBsdfDiffuse",
            "hide": false,
            "inputs": {
              "Color": [
                0.55,
                0.55,
                0.58,
                1.0
              ],
              "Normal": [
                0.0,
                0.0,
                0.0
              ],
              "Roughness": 0.65,
              "Weight": 1.0
            },
            "location": [
              0.0,
              0.0
            ],
            "mute": false,
            "name": "Diffuse BSDF",
            "width": 140.0
          },
          {
            "bl_idname": "ShaderNodeOutputMaterial",
            "hide": false,
            "inputs": {
              "Displacement": {
                "default": 0.0,
                "linked": false
              },
              "Surface": {
                "linked": true
              },
              "Thickness": {
                "default": 0.0,
                "linked": false
              },
              "Volume": {
                "default": null,
                "linked": false
              }
            },
            "is_active_output": true,
            "location": [
              300.0,
              0.0
            ],
            "mute": false,
            "name": "Material Output",
            "target": "ALL",
            "width": 140.0
          }
        ]
      },
      "surface_render_method": "DITHERED",
      "use_backface_culling": false,
      "use_nodes": true
    },
    {
      "diffuse_color": [
        0.7,
        0.64,
        0.5,
        1.0
      ],
      "name": "MAT_ROOM_C",
      "node_tree": {
        "links": [
          {
            "from_node": "Diffuse BSDF",
            "from_socket": "BSDF",
            "to_node": "Material Output",
            "to_socket": "Surface"
          }
        ],
        "nodes": [
          {
            "bl_idname": "ShaderNodeBsdfDiffuse",
            "hide": false,
            "inputs": {
              "Color": [
                0.7,
                0.64,
                0.5,
                1.0
              ],
              "Normal": [
                0.0,
                0.0,
                0.0
              ],
              "Roughness": 0.65,
              "Weight": 1.0
            },
            "location": [
              0.0,
              0.0
            ],
            "mute": false,
            "name": "Diffuse BSDF",
            "width": 140.0
          },
          {
            "bl_idname": "ShaderNodeOutputMaterial",
            "hide": false,
            "inputs": {
              "Displacement": {
                "default": 0.0,
                "linked": false
              },
              "Surface": {
                "linked": true
              },
              "Thickness": {
                "default": 0.0,
                "linked": false
              },
              "Volume": {
                "default": null,
                "linked": false
              }
            },
            "is_active_output": true,
            "location": [
              300.0,
              0.0
            ],
            "mute": false,
            "name": "Material Output",
            "target": "ALL",
            "width": 140.0
          }
        ]
      },
      "surface_render_method": "DITHERED",
      "use_backface_culling": false,
      "use_nodes": true
    },
    {
      "diffuse_color": [
        0.72,
        0.16,
        0.12,
        1.0
      ],
      "name": "MAT_AGENT_ADA",
      "node_tree": {
        "links": [
          {
            "from_node": "Diffuse BSDF",
            "from_socket": "BSDF",
            "to_node": "Material Output",
            "to_socket": "Surface"
          }
        ],
        "nodes": [
          {
            "bl_idname": "ShaderNodeBsdfDiffuse",
            "hide": false,
            "inputs": {
              "Color": [
                0.72,
                0.16,
                0.12,
                1.0
              ],
              "Normal": [
                0.0,
                0.0,
                0.0
              ],
              "Roughness": 0.65,
              "Weight": 1.0
            },
            "location": [
              0.0,
              0.0
            ],
            "mute": false,
            "name": "Diffuse BSDF",
            "width": 140.0
          },
          {
            "bl_idname": "ShaderNodeOutputMaterial",
            "hide": false,
            "inputs": {
              "Displacement": {
                "default": 0.0,
                "linked": false
              },
              "Surface": {
                "linked": true
              },
              "Thickness": {
                "default": 0.0,
                "linked": false
              },
              "Volume": {
                "default": null,
                "linked": false
              }
            },
            "is_active_output": true,
            "location": [
              300.0,
              0.0
            ],
            "mute": false,
            "name": "Material Output",
            "target": "ALL",
            "width": 140.0
          }
        ]
      },
      "surface_render_method": "DITHERED",
      "use_backface_culling": false,
      "use_nodes": true
    },
    {
      "diffuse_color": [
        0.12,
        0.34,
        0.72,
        1.0
      ],
      "name": "MAT_AGENT_BO",
      "node_tree": {
        "links": [
          {
            "from_node": "Diffuse BSDF",
            "from_socket": "BSDF",
            "to_node": "Material Output",
            "to_socket": "Surface"
          }
        ],
        "nodes": [
          {
            "bl_idname": "ShaderNodeBsdfDiffuse",
            "hide": false,
            "inputs": {
              "Color": [
                0.12,
                0.34,
                0.72,
                1.0
              ],
              "Normal": [
                0.0,
                0.0,
                0.0
              ],
              "Roughness": 0.65,
              "Weight": 1.0
            },
            "location": [
              0.0,
              0.0
            ],
            "mute": false,
            "name": "Diffuse BSDF",
            "width": 140.0
          },
          {
            "bl_idname": "ShaderNodeOutputMaterial",
            "hide": false,
            "inputs": {
              "Displacement": {
                "default": 0.0,
                "linked": false
              },
              "Surface": {
                "linked": true
              },
              "Thickness": {
                "default": 0.0,
                "linked": false
              },
              "Volume": {
                "default": null,
                "linked": false
              }
            },
            "is_active_output": true,
            "location": [
              300.0,
              0.0
            ],
            "mute": false,
            "name": "Material Output",
            "target": "ALL",
            "width": 140.0
          }
        ]
      },
      "surface_render_method": "DITHERED",
      "use_backface_culling": false,
      "use_nodes": true
    },
    {
      "diffuse_color": [
        0.16,
        0.58,
        0.24,
        1.0
      ],
      "name": "MAT_AGENT_CY",
      "node_tree": {
        "links": [
          {
            "from_node": "Diffuse BSDF",
            "from_socket": "BSDF",
            "to_node": "Material Output",
            "to_socket": "Surface"
          }
        ],
        "nodes": [
          {
            "bl_idname": "ShaderNodeBsdfDiffuse",
            "hide": false,
            "inputs": {
              "Color": [
                0.16,
                0.58,
                0.24,
                1.0
              ],
              "Normal": [
                0.0,
                0.0,
                0.0
              ],
              "Roughness": 0.65,
              "Weight": 1.0
            },
            "location": [
              0.0,
              0.0
            ],
            "mute": false,
            "name": "Diffuse BSDF",
            "width": 140.0
          },
          {
            "bl_idname": "ShaderNodeOutputMaterial",
            "hide": false,
            "inputs": {
              "Displacement": {
                "default": 0.0,
                "linked": false
              },
              "Surface": {
                "linked": true
              },
              "Thickness": {
                "default": 0.0,
                "linked": false
              },
              "Volume": {
                "default": null,
                "linked": false
              }
            },
            "is_active_output": true,
            "location": [
              300.0,
              0.0
            ],
            "mute": false,
            "name": "Material Output",
            "target": "ALL",
            "width": 140.0
          }
        ]
      },
      "surface_render_method": "DITHERED",
      "use_backface_culling": false,
      "use_nodes": true
    }
  ],
  "meshes": [
    {
      "custom_split_normals_present": false,
      "edge_count": 4,
      "edge_use_edge_sharp": [
        false,
        false,
        false,
        false
      ],
      "loop_normal_source": "flat_polygon_geometric",
      "names": [
        "SMOKE_GROUND"
      ],
      "normalized_polygon_cycles": [
        [
          0,
          2,
          3,
          1
        ]
      ],
      "parameters": {
        "align": "WORLD",
        "size": 18.0
      },
      "polygon_count": 1,
      "polygon_use_smooth": [
        false
      ],
      "primitive": "plane",
      "sorted_edges": [
        [
          0,
          1
        ],
        [
          0,
          2
        ],
        [
          1,
          3
        ],
        [
          2,
          3
        ]
      ],
      "sorted_vertices": [
        [
          -9.0,
          -9.0,
          0.0
        ],
        [
          -9.0,
          9.0,
          0.0
        ],
        [
          9.0,
          -9.0,
          0.0
        ],
        [
          9.0,
          9.0,
          0.0
        ]
      ],
      "vertex_count": 4
    },
    {
      "custom_split_normals_present": false,
      "edge_count": 12,
      "edge_use_edge_sharp": [
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false
      ],
      "loop_normal_source": "flat_polygon_geometric",
      "names": [
        "SMOKE_ROOM_A",
        "SMOKE_ROOM_B",
        "SMOKE_ROOM_C"
      ],
      "normalized_polygon_cycles": [
        [
          0,
          1,
          3,
          2
        ],
        [
          0,
          2,
          6,
          4
        ],
        [
          0,
          4,
          5,
          1
        ],
        [
          1,
          5,
          7,
          3
        ],
        [
          2,
          3,
          7,
          6
        ],
        [
          4,
          6,
          7,
          5
        ]
      ],
      "parameters": {
        "align": "WORLD",
        "dimensions": [
          4.0,
          6.0,
          0.4
        ],
        "transform_applied": true
      },
      "polygon_count": 6,
      "polygon_use_smooth": [
        false,
        false,
        false,
        false,
        false,
        false
      ],
      "primitive": "cube",
      "sorted_edges": [
        [
          0,
          1
        ],
        [
          0,
          2
        ],
        [
          0,
          4
        ],
        [
          1,
          3
        ],
        [
          1,
          5
        ],
        [
          2,
          3
        ],
        [
          2,
          6
        ],
        [
          3,
          7
        ],
        [
          4,
          5
        ],
        [
          4,
          6
        ],
        [
          5,
          7
        ],
        [
          6,
          7
        ]
      ],
      "sorted_vertices": [
        [
          -2.0,
          -3.0,
          -0.2
        ],
        [
          -2.0,
          -3.0,
          0.2
        ],
        [
          -2.0,
          3.0,
          -0.2
        ],
        [
          -2.0,
          3.0,
          0.2
        ],
        [
          2.0,
          -3.0,
          -0.2
        ],
        [
          2.0,
          -3.0,
          0.2
        ],
        [
          2.0,
          3.0,
          -0.2
        ],
        [
          2.0,
          3.0,
          0.2
        ]
      ],
      "vertex_count": 8
    },
    {
      "custom_split_normals_present": false,
      "edge_count": 48,
      "edge_use_edge_sharp": [
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false
      ],
      "loop_normal_source": "flat_polygon_geometric",
      "names": [
        "SMOKE_AGENT_ADA",
        "SMOKE_AGENT_BO",
        "SMOKE_AGENT_CY"
      ],
      "normalized_polygon_cycles": [
        [
          0,
          1,
          5,
          4
        ],
        [
          0,
          2,
          3,
          1
        ],
        [
          0,
          4,
          8,
          12,
          16,
          20,
          24,
          28,
          30,
          26,
          22,
          18,
          14,
          10,
          6,
          2
        ],
        [
          1,
          3,
          7,
          11,
          15,
          19,
          23,
          27,
          31,
          29,
          25,
          21,
          17,
          13,
          9,
          5
        ],
        [
          2,
          6,
          7,
          3
        ],
        [
          4,
          5,
          9,
          8
        ],
        [
          6,
          10,
          11,
          7
        ],
        [
          8,
          9,
          13,
          12
        ],
        [
          10,
          14,
          15,
          11
        ],
        [
          12,
          13,
          17,
          16
        ],
        [
          14,
          18,
          19,
          15
        ],
        [
          16,
          17,
          21,
          20
        ],
        [
          18,
          22,
          23,
          19
        ],
        [
          20,
          21,
          25,
          24
        ],
        [
          22,
          26,
          27,
          23
        ],
        [
          24,
          25,
          29,
          28
        ],
        [
          26,
          30,
          31,
          27
        ],
        [
          28,
          29,
          31,
          30
        ]
      ],
      "parameters": {
        "align": "WORLD",
        "depth": 1.4,
        "end_fill": "NGON",
        "radius": 0.45,
        "vertices": 16
      },
      "polygon_count": 18,
      "polygon_use_smooth": [
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false,
        false
      ],
      "primitive": "cylinder",
      "sorted_edges": [
        [
          0,
          1
        ],
        [
          0,
          2
        ],
        [
          0,
          4
        ],
        [
          1,
          3
        ],
        [
          1,
          5
        ],
        [
          2,
          3
        ],
        [
          2,
          6
        ],
        [
          3,
          7
        ],
        [
          4,
          5
        ],
        [
          4,
          8
        ],
        [
          5,
          9
        ],
        [
          6,
          7
        ],
        [
          6,
          10
        ],
        [
          7,
          11
        ],
        [
          8,
          9
        ],
        [
          8,
          12
        ],
        [
          9,
          13
        ],
        [
          10,
          11
        ],
        [
          10,
          14
        ],
        [
          11,
          15
        ],
        [
          12,
          13
        ],
        [
          12,
          16
        ],
        [
          13,
          17
        ],
        [
          14,
          15
        ],
        [
          14,
          18
        ],
        [
          15,
          19
        ],
        [
          16,
          17
        ],
        [
          16,
          20
        ],
        [
          17,
          21
        ],
        [
          18,
          19
        ],
        [
          18,
          22
        ],
        [
          19,
          23
        ],
        [
          20,
          21
        ],
        [
          20,
          24
        ],
        [
          21,
          25
        ],
        [
          22,
          23
        ],
        [
          22,
          26
        ],
        [
          23,
          27
        ],
        [
          24,
          25
        ],
        [
          24,
          28
        ],
        [
          25,
          29
        ],
        [
          26,
          27
        ],
        [
          26,
          30
        ],
        [
          27,
          31
        ],
        [
          28,
          29
        ],
        [
          28,
          30
        ],
        [
          29,
          31
        ],
        [
          30,
          31
        ]
      ],
      "sorted_vertices": [
        [
          -0.45,
          0.0,
          -0.7
        ],
        [
          -0.45,
          0.0,
          0.7
        ],
        [
          -0.41574578963,
          -0.172207544564,
          -0.7
        ],
        [
          -0.41574578963,
          -0.172207544564,
          0.7
        ],
        [
          -0.41574578963,
          0.172207544564,
          -0.7
        ],
        [
          -0.41574578963,
          0.172207544564,
          0.7
        ],
        [
          -0.318198051534,
          -0.318198051534,
          -0.7
        ],
        [
          -0.318198051534,
          -0.318198051534,
          0.7
        ],
        [
          -0.318198051534,
          0.318198051534,
          -0.7
        ],
        [
          -0.318198051534,
          0.318198051534,
          0.7
        ],
        [
          -0.172207544564,
          -0.41574578963,
          -0.7
        ],
        [
          -0.172207544564,
          -0.41574578963,
          0.7
        ],
        [
          -0.172207544564,
          0.41574578963,
          -0.7
        ],
        [
          -0.172207544564,
          0.41574578963,
          0.7
        ],
        [
          0.0,
          -0.45,
          -0.7
        ],
        [
          0.0,
          -0.45,
          0.7
        ],
        [
          0.0,
          0.45,
          -0.7
        ],
        [
          0.0,
          0.45,
          0.7
        ],
        [
          0.172207544564,
          -0.41574578963,
          -0.7
        ],
        [
          0.172207544564,
          -0.41574578963,
          0.7
        ],
        [
          0.172207544564,
          0.41574578963,
          -0.7
        ],
        [
          0.172207544564,
          0.41574578963,
          0.7
        ],
        [
          0.318198051534,
          -0.318198051534,
          -0.7
        ],
        [
          0.318198051534,
          -0.318198051534,
          0.7
        ],
        [
          0.318198051534,
          0.318198051534,
          -0.7
        ],
        [
          0.318198051534,
          0.318198051534,
          0.7
        ],
        [
          0.41574578963,
          -0.172207544564,
          -0.7
        ],
        [
          0.41574578963,
          -0.172207544564,
          0.7
        ],
        [
          0.41574578963,
          0.172207544564,
          -0.7
        ],
        [
          0.41574578963,
          0.172207544564,
          0.7
        ],
        [
          0.45,
          0.0,
          -0.7
        ],
        [
          0.45,
          0.0,
          0.7
        ]
      ],
      "vertex_count": 32
    }
  ],
  "objects": [
    {
      "collection": "COLISEUM_SMOKE",
      "data_name": "SMOKE_GROUND",
      "delta_location": [
        0.0,
        0.0,
        0.0
      ],
      "delta_rotation_euler": [
        0.0,
        0.0,
        0.0
      ],
      "delta_scale": [
        1.0,
        1.0,
        1.0
      ],
      "hide_render": false,
      "hide_viewport": false,
      "instance_type": "NONE",
      "is_holdout": false,
      "is_shadow_catcher": false,
      "location": [
        0.0,
        0.0,
        0.0
      ],
      "material_names": [
        "MAT_GROUND"
      ],
      "name": "SMOKE_GROUND",
      "parent": null,
      "pass_index": 0,
      "rotation_euler": [
        0.0,
        0.0,
        0.0
      ],
      "rotation_mode": "XYZ",
      "scale": [
        1.0,
        1.0,
        1.0
      ],
      "show_instancer_for_render": true,
      "visible_camera": true,
      "visible_diffuse": true,
      "visible_glossy": true,
      "visible_shadow": true,
      "visible_transmission": true,
      "visible_volume_scatter": true
    },
    {
      "collection": "COLISEUM_SMOKE",
      "data_name": "SMOKE_ROOM_A",
      "delta_location": [
        0.0,
        0.0,
        0.0
      ],
      "delta_rotation_euler": [
        0.0,
        0.0,
        0.0
      ],
      "delta_scale": [
        1.0,
        1.0,
        1.0
      ],
      "hide_render": false,
      "hide_viewport": false,
      "instance_type": "NONE",
      "is_holdout": false,
      "is_shadow_catcher": false,
      "location": [
        -5.0,
        0.0,
        0.2
      ],
      "material_names": [
        "MAT_ROOM_A"
      ],
      "name": "SMOKE_ROOM_A",
      "parent": null,
      "pass_index": 0,
      "rotation_euler": [
        0.0,
        0.0,
        0.0
      ],
      "rotation_mode": "XYZ",
      "scale": [
        1.0,
        1.0,
        1.0
      ],
      "show_instancer_for_render": true,
      "visible_camera": true,
      "visible_diffuse": true,
      "visible_glossy": true,
      "visible_shadow": true,
      "visible_transmission": true,
      "visible_volume_scatter": true
    },
    {
      "collection": "COLISEUM_SMOKE",
      "data_name": "SMOKE_ROOM_B",
      "delta_location": [
        0.0,
        0.0,
        0.0
      ],
      "delta_rotation_euler": [
        0.0,
        0.0,
        0.0
      ],
      "delta_scale": [
        1.0,
        1.0,
        1.0
      ],
      "hide_render": false,
      "hide_viewport": false,
      "instance_type": "NONE",
      "is_holdout": false,
      "is_shadow_catcher": false,
      "location": [
        0.0,
        0.0,
        0.2
      ],
      "material_names": [
        "MAT_ROOM_B"
      ],
      "name": "SMOKE_ROOM_B",
      "parent": null,
      "pass_index": 0,
      "rotation_euler": [
        0.0,
        0.0,
        0.0
      ],
      "rotation_mode": "XYZ",
      "scale": [
        1.0,
        1.0,
        1.0
      ],
      "show_instancer_for_render": true,
      "visible_camera": true,
      "visible_diffuse": true,
      "visible_glossy": true,
      "visible_shadow": true,
      "visible_transmission": true,
      "visible_volume_scatter": true
    },
    {
      "collection": "COLISEUM_SMOKE",
      "data_name": "SMOKE_ROOM_C",
      "delta_location": [
        0.0,
        0.0,
        0.0
      ],
      "delta_rotation_euler": [
        0.0,
        0.0,
        0.0
      ],
      "delta_scale": [
        1.0,
        1.0,
        1.0
      ],
      "hide_render": false,
      "hide_viewport": false,
      "instance_type": "NONE",
      "is_holdout": false,
      "is_shadow_catcher": false,
      "location": [
        5.0,
        0.0,
        0.2
      ],
      "material_names": [
        "MAT_ROOM_C"
      ],
      "name": "SMOKE_ROOM_C",
      "parent": null,
      "pass_index": 0,
      "rotation_euler": [
        0.0,
        0.0,
        0.0
      ],
      "rotation_mode": "XYZ",
      "scale": [
        1.0,
        1.0,
        1.0
      ],
      "show_instancer_for_render": true,
      "visible_camera": true,
      "visible_diffuse": true,
      "visible_glossy": true,
      "visible_shadow": true,
      "visible_transmission": true,
      "visible_volume_scatter": true
    },
    {
      "collection": "COLISEUM_SMOKE",
      "data_name": "SMOKE_AGENT_ADA",
      "delta_location": [
        0.0,
        0.0,
        0.0
      ],
      "delta_rotation_euler": [
        0.0,
        0.0,
        0.0
      ],
      "delta_scale": [
        1.0,
        1.0,
        1.0
      ],
      "hide_render": false,
      "hide_viewport": false,
      "instance_type": "NONE",
      "is_holdout": false,
      "is_shadow_catcher": false,
      "location": [
        -5.0,
        0.0,
        1.1
      ],
      "material_names": [
        "MAT_AGENT_ADA"
      ],
      "name": "SMOKE_AGENT_ADA",
      "parent": null,
      "pass_index": 0,
      "rotation_euler": [
        0.0,
        0.0,
        0.0
      ],
      "rotation_mode": "XYZ",
      "scale": [
        1.0,
        1.0,
        1.0
      ],
      "show_instancer_for_render": true,
      "visible_camera": true,
      "visible_diffuse": true,
      "visible_glossy": true,
      "visible_shadow": true,
      "visible_transmission": true,
      "visible_volume_scatter": true
    },
    {
      "collection": "COLISEUM_SMOKE",
      "data_name": "SMOKE_AGENT_BO",
      "delta_location": [
        0.0,
        0.0,
        0.0
      ],
      "delta_rotation_euler": [
        0.0,
        0.0,
        0.0
      ],
      "delta_scale": [
        1.0,
        1.0,
        1.0
      ],
      "hide_render": false,
      "hide_viewport": false,
      "instance_type": "NONE",
      "is_holdout": false,
      "is_shadow_catcher": false,
      "location": [
        0.0,
        0.0,
        1.1
      ],
      "material_names": [
        "MAT_AGENT_BO"
      ],
      "name": "SMOKE_AGENT_BO",
      "parent": null,
      "pass_index": 0,
      "rotation_euler": [
        0.0,
        0.0,
        0.0
      ],
      "rotation_mode": "XYZ",
      "scale": [
        1.0,
        1.0,
        1.0
      ],
      "show_instancer_for_render": true,
      "visible_camera": true,
      "visible_diffuse": true,
      "visible_glossy": true,
      "visible_shadow": true,
      "visible_transmission": true,
      "visible_volume_scatter": true
    },
    {
      "collection": "COLISEUM_SMOKE",
      "data_name": "SMOKE_AGENT_CY",
      "delta_location": [
        0.0,
        0.0,
        0.0
      ],
      "delta_rotation_euler": [
        0.0,
        0.0,
        0.0
      ],
      "delta_scale": [
        1.0,
        1.0,
        1.0
      ],
      "hide_render": false,
      "hide_viewport": false,
      "instance_type": "NONE",
      "is_holdout": false,
      "is_shadow_catcher": false,
      "location": [
        5.0,
        0.0,
        1.1
      ],
      "material_names": [
        "MAT_AGENT_CY"
      ],
      "name": "SMOKE_AGENT_CY",
      "parent": null,
      "pass_index": 0,
      "rotation_euler": [
        0.0,
        0.0,
        0.0
      ],
      "rotation_mode": "XYZ",
      "scale": [
        1.0,
        1.0,
        1.0
      ],
      "show_instancer_for_render": true,
      "visible_camera": true,
      "visible_diffuse": true,
      "visible_glossy": true,
      "visible_shadow": true,
      "visible_transmission": true,
      "visible_volume_scatter": true
    },
    {
      "collection": "COLISEUM_SMOKE",
      "data": {
        "clip_end": 100.0,
        "clip_start": 0.1,
        "dof_aperture_blades": 0,
        "dof_aperture_fstop": 2.8,
        "dof_aperture_ratio": 1.0,
        "dof_aperture_rotation": 0.0,
        "dof_enabled": false,
        "dof_focus_distance": 10.0,
        "dof_focus_object": null,
        "lens": 50.0,
        "lens_unit": "MILLIMETERS",
        "name": "SMOKE_CAMERA_DATA",
        "ortho_scale": 19.0,
        "panorama_type": "EQUIRECTANGULAR",
        "sensor_fit": "AUTO",
        "sensor_height": 32.0,
        "sensor_width": 36.0,
        "shift_x": 0.0,
        "shift_y": 0.0,
        "stereo_convergence_distance": 30.0,
        "stereo_convergence_mode": "OFFAXIS",
        "stereo_interocular_distance": 0.065,
        "stereo_pivot": "LEFT",
        "stereo_pole_merge_angle_from": 1.047198,
        "stereo_pole_merge_angle_to": 1.308997,
        "stereo_use_pole_merge": false,
        "stereo_use_spherical": false,
        "type": "ORTHO"
      },
      "data_name": "SMOKE_CAMERA_DATA",
      "delta_location": [
        0.0,
        0.0,
        0.0
      ],
      "delta_rotation_euler": [
        0.0,
        0.0,
        0.0
      ],
      "delta_scale": [
        1.0,
        1.0,
        1.0
      ],
      "hide_render": false,
      "hide_viewport": false,
      "instance_type": "NONE",
      "is_holdout": false,
      "is_shadow_catcher": false,
      "location": [
        9.0,
        -11.0,
        11.0
      ],
      "material_names": [],
      "name": "SMOKE_CAMERA",
      "parent": null,
      "pass_index": 0,
      "rotation_euler": [
        0.872665,
        0.0,
        0.698132
      ],
      "rotation_mode": "XYZ",
      "scale": [
        1.0,
        1.0,
        1.0
      ],
      "show_instancer_for_render": true,
      "visible_camera": true,
      "visible_diffuse": true,
      "visible_glossy": true,
      "visible_shadow": true,
      "visible_transmission": true,
      "visible_volume_scatter": true
    },
    {
      "collection": "COLISEUM_SMOKE",
      "data": {
        "angle": 0.0872665,
        "color": [
          1.0,
          1.0,
          1.0
        ],
        "cutoff_distance": 40.0,
        "diffuse_factor": 1.0,
        "energy": 2.0,
        "name": "SMOKE_SUN_DATA",
        "shadow_soft_size": 0.25,
        "shape": "SQUARE",
        "show_cone": false,
        "size": 0.25,
        "size_y": 0.25,
        "specular_factor": 1.0,
        "spot_blend": 0.15,
        "spot_size": 0.785398,
        "transmission_factor": 1.0,
        "type": "SUN",
        "use_custom_distance": false,
        "use_nodes": false,
        "use_shadow": true,
        "volume_factor": 1.0
      },
      "data_name": "SMOKE_SUN_DATA",
      "delta_location": [
        0.0,
        0.0,
        0.0
      ],
      "delta_rotation_euler": [
        0.0,
        0.0,
        0.0
      ],
      "delta_scale": [
        1.0,
        1.0,
        1.0
      ],
      "hide_render": false,
      "hide_viewport": false,
      "instance_type": "NONE",
      "is_holdout": false,
      "is_shadow_catcher": false,
      "location": [
        0.0,
        0.0,
        8.0
      ],
      "material_names": [],
      "name": "SMOKE_SUN",
      "parent": null,
      "pass_index": 0,
      "rotation_euler": [
        0.523599,
        -0.349066,
        -0.523599
      ],
      "rotation_mode": "XYZ",
      "scale": [
        1.0,
        1.0,
        1.0
      ],
      "show_instancer_for_render": true,
      "visible_camera": true,
      "visible_diffuse": true,
      "visible_glossy": true,
      "visible_shadow": true,
      "visible_transmission": true,
      "visible_volume_scatter": true
    }
  ],
  "scene": {
    "camera": "SMOKE_CAMERA",
    "child_collections": [
      "COLISEUM_SMOKE"
    ],
    "master_collection": "Scene Collection",
    "name": "Scene",
    "view_layer": "ViewLayer",
    "world": "SMOKE_WORLD"
  },
  "view_layers": [
    {
      "layer_collections": [
        {
          "exclude": false,
          "hide_viewport": false,
          "holdout": false,
          "indirect_only": false,
          "name": "COLISEUM_SMOKE"
        }
      ],
      "material_override": null,
      "name": "ViewLayer",
      "use": true,
      "use_freestyle": false,
      "use_pass_combined": true,
      "use_pass_mist": false,
      "use_pass_normal": false,
      "use_pass_position": false,
      "use_pass_vector": false,
      "use_pass_z": false,
      "world_override": null
    }
  ],
  "zero_per_object_counts": {
    "animation_data": 0,
    "constraints": 0,
    "custom_properties": 0,
    "drivers": 0,
    "modifiers": 0,
    "particle_systems": 0,
    "simulation_settings": 0
  }
}
```

Under the integrated `schema.canonical_json`, the object above is exactly
17992 bytes and has `expected_inventory_digest =
1ec5e1c2c6a063d85e0e328925296b21e7e4bc435bf4acaf2869741826bd5f60`. Construction tests parse this exact fenced value, require its complete
nested key sets, recompute both literals, and refuse before job creation on drift.

The literal mesh projection binds the complete normalized topology and render-facing
surface state. The exact factory profile additionally covers every remaining writable
`Mesh`, `MeshVertex`, `MeshEdge`, `MeshLoop`, `MeshPolygon`, `Collection`,
`ViewLayer`, and `LayerCollection` RNA property under the pinned Blender identity.
The inspector requires both the literal inventory equality and the factory-profile
equality; a matching vertex/count projection cannot excuse different smoothing,
normals, connectivity, winding, collection visibility, layer exclusion, overrides,
or any other writable value.

Each material node tree has exactly two nodes and one link, with no frame, group, or
interface sockets:

```json
{
  "nodes": [
    {"name":"Diffuse BSDF","bl_idname":"ShaderNodeBsdfDiffuse",
     "location":[0.0,0.0],"width":140.0,"mute":false,"hide":false,
     "inputs":{"Weight":1.0,"Color":"<table-rgba>","Roughness":0.65,
               "Normal":[0.0,0.0,0.0]}},
    {"name":"Material Output","bl_idname":"ShaderNodeOutputMaterial",
     "location":[300.0,0.0],"width":140.0,"mute":false,"hide":false,
     "target":"ALL","is_active_output":true,
     "inputs":{"Surface":{"linked":true},"Volume":{"linked":false,"default":null},
               "Displacement":{"linked":false,"default":0.0},
               "Thickness":{"linked":false,"default":0.0}}}
  ],
  "links":[{"from_node":"Diffuse BSDF","from_socket":"BSDF",
             "to_node":"Material Output","to_socket":"Surface"}]
}
```

All node names, types, locations, widths, flags, socket names/types/defaults, link
endpoints, and material values are exact; unknown nodes, sockets, links, material
settings, or custom properties refuse. Every unlinked Output value is explicit above. Every object has
zero modifiers, constraints, particle systems, simulation/physics settings,
animation data, drivers, and custom properties. There are exactly nine objects,
seven meshes, seven materials, one camera, one light, one world, one scene, one view
layer named `ViewLayer`, the master collection, and one non-master collection named
`COLISEUM_SMOKE`. `Scene.camera` is `SMOKE_CAMERA`; `Scene.world` is `SMOKE_WORLD`;
the view layer includes only `COLISEUM_SMOKE`; frame count remains one.

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
reviewed, guarded staged `inspect_scene.py` against the saved file with factory startup,
autoexec disabled, offline mode, and the same native process caps.

```text
blender.exe --background --factory-startup --disable-autoexec --offline-mode
  -noaudio --python-exit-code 17
  --python <guarded-staged-inspector-windows-path> --
  --job-spec <guarded-job-spec-windows-path>
  --launch-attestation <guarded-inspector-launch-attestation-windows-path>
  --scene <guarded-scene-blend-windows-path>
  --result <fixed-inspector-report-windows-path>
```

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

### 6.4 Closed worker-result and inspector-result boundary

`worker-result.json` is canonical UTF-8 JSON under a closed
`blender.worker_result.v1` schema. Duplicate object keys, a BOM, trailing bytes,
noncanonical numbers, or noncanonical key ordering refuse. Its top level has exactly:

```text
schema_version                 # literal blender.worker_result.v1
job_id                         # 64 lowercase hex, equals recomputed job
worker_launch_attestation_id   # 64 lowercase hex, equals host worker attestation
smoke_profile_version          # literal coliseum-smoke.v1
reviewed_script_sha256         # equals job binding
staged_script_file_identity    # exact launch-attestation-bound Windows identity
factory_profile_sha256         # equals job binding
blender_identity               # exact {version, build_hash, platform}
status                         # completed | failed
error_code                     # null or closed failure enum
terminal_progress_sequence     # non-negative integer, not boolean
frame                          # exact {start: 1, end: 1, current: 1}
outputs                        # closed sorted list below
created_inventory_digest       # 64 lowercase hex or null
simulation_impact              # literal none
```

`worker_launch_attestation_id` resolves to the strict host-authored record from section 5
and its job/script/factory/argument bindings are re-derived before result acceptance.
`staged_script_file_identity` has exactly
`{volume_serial_number, file_id_hex}` where the first value is a non-negative JSON
integer and `file_id_hex` is the 32-lowercase-hex encoding of Windows
`FILE_ID_128`. `blender_identity` has exactly
`{version, build_hash, platform}` and is byte-equal to the job binding. No native
path is serialized in either object.

For `completed`, `error_code` is null, `created_inventory_digest` is 64 lowercase
hex equal to the job's `expected_inventory_digest`, terminal progress is
`completed`, and `outputs` has exactly these three entries in this order:

```json
[
  {"kind":"preview","relative_path":"preview.png","media_type":"image/png",
   "byte_count":"<positive-int>","sha256":"<64-lowercase-hex>"},
  {"kind":"render","relative_path":"render.png","media_type":"image/png",
   "byte_count":"<positive-int>","sha256":"<64-lowercase-hex>"},
  {"kind":"scene","relative_path":"scene.blend","media_type":"application/x-blender",
   "byte_count":"<positive-int>","sha256":"<64-lowercase-hex>"}
]
```

Angle-bracket tokens above denote schema types, not literal accepted strings.
`byte_count` serializes as a JSON integer. For `failed`, `error_code` is one value
from `{worker_schema, job_binding, input_binding, profile_drift, scene_build,
preview_render, final_render, scene_save, output_write, resource_limit,
unexpected_exception}`, `outputs` is empty, `created_inventory_digest` is null, and
terminal progress is `failed`. Any other status/output/error relation refuses.
A missing result is a host failure, not an inferred worker result.

The host parses with duplicate-key rejection, enforces the 64-KiB cap and exact
keys/types/enums, revalidates every job/profile/script/factory/Blender binding, and
then independently opens each declared output through the held directory. It hashes
the bytes, requires exact size/digest equality, validates both PNG structures and
dimensions, and validates the `.blend` through the separate inspector. Worker claims
never substitute for host observations.

`inspector-report.json` likewise has exactly
`{schema_version, job_id, inspector_launch_attestation_id, smoke_profile_version,
reviewed_inspector_script_sha256, staged_inspector_file_identity,
factory_profile_sha256, blend_sha256, status, error_codes, observed_inventory_digest,
observed_render_profile_digest, prohibited_content_counts}`.
`schema_version` is `blender.inspector_result.v1`; `status` is `passed` only when
`error_codes` is empty, both observed digests equal the job-bound expected digests,
and `prohibited_content_counts` has the exact closed keys
`{text, drivers, handlers, packed, external, compositor, sequencer, node_groups,
custom_properties, modifiers, constraints, animation, simulation,
undeclared_datablocks}`, each integer zero. A failure uses status `failed`, at least
one sorted unique code from `{inspector_schema, job_binding, launch_binding,
input_binding, factory_profile, blend_open, profile_drift, inventory_drift,
prohibited_content, resource_limit, unexpected_exception}`, and cannot authorize a
manifest. `job_id`, `inspector_launch_attestation_id`, all script/profile/blend hashes, and
passed observed digests are 64 lowercase hex; staged identity has the exact worker
identity schema. On failure, observed digests may be null but all other bindings and
the closed prohibited-count object remain required. Unknown/missing keys,
malformed/truncated/oversized data, wrong types, wrong bindings, or digest/count drift
refuses before `render_manifest.v1` exists.

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
- inability to stage the reviewed script descriptor-to-descriptor, a staged digest
  mismatch for either reviewed script, any staged input/path identity change, inability to deny write/delete
  sharing for both complete child lifetimes, or any evidence that Blender could
  consume bytes other than the held verified script;
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
  baseline drift, malformed/oversized/unknown-key worker or inspector result,
  worker/job/profile/script/factory/output binding drift, hash mismatch, or
  unexpected file;
- a render manifest when any required validation failed.

A failed job remains a failed derived job. It cannot change a source run or hide
its negative provenance. Cleanup is explicit and never follows symlinks.

## 10. Render manifest

Only the host writes `render_manifest.v1`, after successful worker exit, strict
`blender.worker_result.v1` validation, independent output hashing/PNG validation,
and strict passing `blender.inspector_result.v1` validation. A manifest is a success
record only: its `status` is the literal `completed`. A failed, interrupted, refused,
or partially validated job has no render manifest; its worker/host progress and
failure records remain the evidence. This prevents a permissive failed-state
relation from becoming another output-admission path.

The file is strict UTF-8 integrated `schema.canonical_json` with no BOM or trailing
byte and a maximum of 131072 bytes. The host parses with duplicate-key rejection,
requires byte-for-byte equality with the integrated canonical serialization, and
refuses floats, noncanonical numbers, an unknown or missing key at any depth, a
wrong type/enum/relation, or an array in the wrong order. Its top-level key set is
exactly:

```text
{schema_version, job_id, bridge_version, smoke_profile_version, status,
 source, launches, renderer, inputs, results, outputs,
 derived_visualization_status, simulation_impact, interpolation_semantics}
```

Scalar constraints are exact:

- `schema_version == "render_manifest.v1"`,
  `bridge_version == "blender-workshop-bridge.v1"`,
  `smoke_profile_version == "coliseum-smoke.v1"`, `status == "completed"`,
  `derived_visualization_status == "validated"`, and
  `simulation_impact == "none"`;
- `job_id`, every non-null digest, and every attestation id is 64 lowercase hex;
  `renderer.repository_commit` is 40 lowercase hex; byte counts are positive JSON
  integers (never booleans); and file identities use the exact section-5
  `{volume_serial_number, file_id_hex}` schema;
- `interpolation_semantics` is `none` for this one-frame smoke profile. A later
  audited multi-frame profile may use `presentation_only`; no other value is legal.

`source` has exactly
`{kind, canonical_run_id, source_evidence_sha256,
presentation_projection_id, presentation_projection_sha256, provenance}`.
For `kind == "smoke"`, the four identity/digest values are JSON null and every
provenance field is `not_applicable`. For `kind == "validated_projection"`,
`canonical_run_id` and `presentation_projection_id` are ASCII
`[A-Za-z0-9._:-]{1,240}` strings, both SHA-256 values are 64 lowercase hex, none of
the seven provenance fields may be
`not_applicable`, and all seven are copied byte-for-byte from the strictly validated
projection. `provenance` has exactly these required keys and enums:

```text
completion               complete | incomplete | unknown | not_applicable
behavioral_claimability  claimable | nonclaimable | unknown | not_applicable
replay_verification      verified | unverified | failed | not_exposed | unknown | not_applicable
training_admission       admitted | rejected | unknown | not_applicable
governance_approval      approved | blocked | not_bound | unknown | not_applicable
quarantine               quarantined | not_quarantined | unknown | not_applicable
correction_lineage       valid | invalid | not_present | unknown | not_applicable
```

No field is optional. Absence never selects `complete`, `claimable`, `verified`,
`admitted`, `approved`, `not_quarantined`, or `valid`. The host does not derive one
state from another, inspect the dirty Council tree, or promote an `unknown`/
`not_bound` value. Correction lineage and quarantine remain separate from render
success and from one another.

`launches` has exactly `{worker, inspector}`. `worker` has exactly
`{attestation_id, argument_array_sha256, script_relative_path, script_sha256,
file_identity}`; `inspector` has those keys plus `scene_blend_file_identity`.
The relative paths are the literals `input/smoke_scene.py` and
`input/inspect_scene.py`; all other values equal the independently rederived guarded
launch records. No absolute/native path enters the manifest.

`renderer` has exactly
`{blender_identity, repository_commit, render_engine, frame, resolution,
camera_name, render_profile_sha256, inventory_sha256}`. `blender_identity` is exact
`{version, build_hash, platform}` and equals the job. `render_engine` is
`BLENDER_EEVEE_NEXT`; `frame` is exactly `{start:1,end:1}`; `resolution` is exactly
`{width:640,height:480,percentage:100}`; `camera_name` is `SMOKE_CAMERA`; and both
profile/inventory digests equal the job, worker, and passing inspector bindings.

`inputs` has exactly `{job_spec, factory_profile, template, asset_pack}`. The first
two records have exactly `{relative_path, byte_count, sha256}`, fixed relative paths
`job.json` and `input/factory-profile.json`, and host-observed positive sizes/digests.
`template` and `asset_pack` each have exactly `{status, version, sha256}`. For this
geometric smoke source each is exactly
`{"status":"not_applicable","version":null,"sha256":null}`. A future bound profile
requires `status == "bound"`, a nonempty ASCII version of at most 128 characters,
and a 64-lowercase-hex digest under a separately audited profile; mixed null/bound
relations refuse.

`results` has exactly `{worker, inspector}`. Each nested record has exactly
`{schema_version, relative_path, byte_count, sha256}`. The schema/path pairs are
`blender.worker_result.v1` / `worker-result.json` and
`blender.inspector_result.v1` / `inspector-result.json`. Their bytes are reopened and
hashed by the host after strict parsing; the inspector status must be `passed` and
the worker status `completed`.

`outputs` is exactly the worker's independently host-validated three-entry list in
the fixed section-6.4 order and with the exact key set
`{kind, relative_path, media_type, byte_count, sha256}` per entry: preview PNG,
render PNG, then `scene.blend`. Its scene digest and independently opened native
file identity equal the inspector launch binding. Missing, extra, reordered,
zero-byte, wrongly typed, or digest-divergent output refuses the manifest.

This normative fixed manifest vector exercises every key and terminal relation.
The repeated values are fixture data, not environment assertions:

```json
{"bridge_version":"blender-workshop-bridge.v1","derived_visualization_status":"validated","inputs":{"asset_pack":{"sha256":null,"status":"not_applicable","version":null},"factory_profile":{"byte_count":103,"relative_path":"input/factory-profile.json","sha256":"4040404040404040404040404040404040404040404040404040404040404040"},"job_spec":{"byte_count":104,"relative_path":"job.json","sha256":"5050505050505050505050505050505050505050505050505050505050505050"},"template":{"sha256":null,"status":"not_applicable","version":null}},"interpolation_semantics":"none","job_id":"7070707070707070707070707070707070707070707070707070707070707070","launches":{"inspector":{"argument_array_sha256":"6e0032f60911008b070f799157733fb055ca68f2464e6f2d2f335011a50ba0ca","attestation_id":"2aca6cd643b811aa2d9abc544663f6c939382e94ef80ac26e0861ec129f4424e","file_identity":{"file_id_hex":"03030303030303030303030303030303","volume_serial_number":1},"scene_blend_file_identity":{"file_id_hex":"06060606060606060606060606060606","volume_serial_number":1},"script_relative_path":"input/inspect_scene.py","script_sha256":"3030303030303030303030303030303030303030303030303030303030303030"},"worker":{"argument_array_sha256":"299acb851ead7a64505ffb48b95d3cd30901392b71f14ed57b062739c9e64860","attestation_id":"e68207158627944ef9e584adf5d6089454d8da778a1d554aec0f943c6b6ed418","file_identity":{"file_id_hex":"02020202020202020202020202020202","volume_serial_number":1},"script_relative_path":"input/smoke_scene.py","script_sha256":"2020202020202020202020202020202020202020202020202020202020202020"}},"outputs":[{"byte_count":800,"kind":"preview","media_type":"image/png","relative_path":"preview.png","sha256":"8080808080808080808080808080808080808080808080808080808080808080"},{"byte_count":900,"kind":"render","media_type":"image/png","relative_path":"render.png","sha256":"8181818181818181818181818181818181818181818181818181818181818181"},{"byte_count":1000,"kind":"scene","media_type":"application/x-blender","relative_path":"scene.blend","sha256":"6060606060606060606060606060606060606060606060606060606060606060"}],"renderer":{"blender_identity":{"build_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","platform":"Windows","version":"5.2.0"},"camera_name":"SMOKE_CAMERA","frame":{"end":1,"start":1},"inventory_sha256":"1ec5e1c2c6a063d85e0e328925296b21e7e4bc435bf4acaf2869741826bd5f60","render_engine":"BLENDER_EEVEE_NEXT","render_profile_sha256":"58ef3569c2bb2bd3e593876a38be6898abde20d488a238b9878a7e7ce77d83bb","repository_commit":"9999999999999999999999999999999999999999","resolution":{"height":480,"percentage":100,"width":640}},"results":{"inspector":{"byte_count":1200,"relative_path":"inspector-result.json","schema_version":"blender.inspector_result.v1","sha256":"7272727272727272727272727272727272727272727272727272727272727272"},"worker":{"byte_count":1100,"relative_path":"worker-result.json","schema_version":"blender.worker_result.v1","sha256":"7171717171717171717171717171717171717171717171717171717171717171"}},"schema_version":"render_manifest.v1","simulation_impact":"none","smoke_profile_version":"coliseum-smoke.v1","source":{"canonical_run_id":null,"kind":"smoke","presentation_projection_id":null,"presentation_projection_sha256":null,"provenance":{"behavioral_claimability":"not_applicable","completion":"not_applicable","correction_lineage":"not_applicable","governance_approval":"not_applicable","quarantine":"not_applicable","replay_verification":"not_applicable","training_admission":"not_applicable"},"source_evidence_sha256":null},"status":"completed"}
```

Under integrated canonical JSON the vector is exactly 3588 UTF-8 bytes and has
SHA-256 `dfc2f0aa9fbdd8e2c4342e9593f191a36bddc8a3ea6d217a2faff40af8eee457`.
Independent construction and reload must reproduce both
literals. Every omitted/unknown key, wrong type/enum/relation, duplicate key, BOM,
trailing byte, alternate formatting, source-provenance drift, wrong result/
attestation/output binding, or pre-validation manifest attempt refuses.

Render success cannot promote any source status. Interpolated frames in later
audited profiles are always declared presentation-only.

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
- recorded terminal, completion, claimability, replay, governance, admission,
  quarantine, and correction-lineage states.

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
   substitution, deterministic-setting drift, and immutable-input drift; ordinary
   tests parse the one fully expanded normative inventory block, require no
   placeholder/reference/template key, assert every nested key set, and reproduce
   its literal byte count/digest; fixtures alter one camera object/data, sun
   object/data/color, material, node, mesh/object transform, polygon smooth flag,
   loop/custom-normal state, exact edge or polygon connection/winding, collection
   `hide_render`, layer-collection exclusion, view-layer use/material/world override,
   color-management, Cycles, or factory-profile value at a time and every mutation
   refuses under `coliseum-smoke.v1`; the fixed worker/inspector vector independently
   reconstructs both argument digests, the ordered ancestor digest from the exact
   canonical-JSON UTF-8 equation, and both ContentRecord ids; alternate pretty,
   NUL-delimited, BOM, and newline ancestor bytes do not validate, while one
   argument/ancestor order/value mutation changes identity or refuses;
4. host-only path-verifier cases for unavailable reparse detection, junction/
   reparse escape, UNC/drive/case/device/alternate-stream and protected-root
   aliases, Linux symlinks, component swaps, safe fresh-leaf creation, Windows
   handle identity, WSL round trip, overwrite, and undeclared files; every
   indeterminate case refuses before Blender and creates no output;
   coordinated check/use regressions replace each repository source, staged script,
   staged-script ancestor, factory profile, and job spec after initial validation;
   source replacement after an authenticated copy cannot alter consumed bytes,
   while every staged-input replacement/modification is blocked or refuses before
   launch, and the child-consumed file identity/digest equals the applicable launch
   binding; another regression replaces/modifies `scene.blend` after worker hash
   validation but before inspector pathname open and proves the held scene identity
   blocks/refuses it and the inspector consumed the attested bytes;
5. progress sequence/stage monotonicity, malformed/truncated/oversized telemetry,
   preview hash mismatch, and failure terminals;
6. loopback capability, Host checks, security headers, method refusal, no raw
   path/job selection, safe text, and no arbitrary command/Python endpoint;
7. actor-safe projection before asset resolution and physical absence of private,
   hidden, raw-completion, evaluator, and Council fields;
8. nonzero exit, timeout, every exact resource-cap breach, missing output,
   invalid PNG, invalid inventory, and unexpected output fail closed without a
   manifest; `worker-result.v1` fixtures reject malformed/non-object/duplicate-key/
   truncated/oversized JSON, unknown/missing keys, wrong types/enums, wrong
   job/profile/script/factory/Blender ids, failed/nonterminal status, invalid
   status-output relations, and output size/digest/count drift before any manifest;
9. independently construct/reload the literal manifest vector and reproduce its
   3588-byte length and SHA-256; reject every omitted/unknown nested or top-level
   key, wrong type/enum/relation, duplicate key, BOM/trailing/noncanonical byte,
   favorable provenance inferred from absence, quarantine/correction drift, wrong
   result/attestation/output binding, pre-validation manifest attempt, and failed
   job manifest; retain exact relative paths, Blender/script/template/asset binding,
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

# Blender Workshop Bridge — WSL fixed-staging and manifest-coherence amendment 1

Status: design amendment; no Blender execution or implementation authorization.

Amends: `BLENDER-WORKSHOP-BRIDGE.md` at commit
`e945f99b432f78baea3023f6572e23dd18e5112e`.

Source: `first-gladiator-blender-fixed-staging-amendment-001`.

## 1. Why this amendment is necessary

The integrated bridge design assumed that a Windows Blender process could consume
the repository-local derived directory through a non-UNC Windows pathname. The
actual authenticated environment does not satisfy that assumption:

- the Agent Coliseum repository is on WSL2 ext4 at
  `/home/dummy/agent-coliseum`;
- `wslpath -w /home/dummy/agent-coliseum` returns an internal
  `\\\\wsl.localhost\\Ubuntu\\...` UNC pathname; and
- section 4.1 of the integrated design correctly refuses UNC job paths and does
  not permit a degraded lexical-only mode.

Moving the canonical repository or weakening the guard is not an implementation
detail. The first is a deployment change and the second violates the ratified
security boundary. Section 4.1 already anticipated a later fixed Windows staging
root with authenticated copy-in and copy-out. This amendment specifies that
bounded path.

Independent implementation reconciliation also found a closed-schema
contradiction. Section 6.1 binds `render.engine == "CYCLES"` and the final output
to `1280 x 720`, while section 10's manifest relation and fixed vector claimed
`BLENDER_EEVEE_NEXT` at `640 x 480`. A valid host could not both report the
actual bound render and satisfy that vector. Section 8 below makes the success
manifest truthful without changing the render profile.

Nothing here authorizes browser mutation, an arbitrary staging path, remote
execution, model contact, canonical evidence writes, or a canonical projection.

## 2. Superseded clauses

For the Windows-Blender/WSL-ext4 deployment only, this amendment supersedes:

1. section 4's requirement that generated worker outputs initially exist only
   beneath `repo_derived`;
2. section 4.1's statement that the first slice does not support a fixed Windows
   staging root; and
3. section 10's literal `renderer.render_engine`, `renderer.resolution`, fixed
   manifest bytes, and fixed manifest SHA-256.

All other clauses remain normative. In particular, canonical runs and Council
records remain protected, Blender remains a derived presentation worker, the
browser remains read-only, launch attestations remain content-addressed, worker
and inspector processes remain natively guarded, and a failed job has no render
manifest.

## 3. Closed deployment profile

The implementation supports exactly two deployment profiles:

### 3.1 Direct repository profile

`direct-repo-derived.v1` is eligible only when `wslpath -w` produces a validated
absolute local drive path for the opened repository-derived job directory and all
integrated section-4.1 proofs pass. No behavior changes for that profile.

### 3.2 Fixed Windows staging profile

`fixed-windows-staging.v1` is eligible only when the direct profile is ineligible
because the opened repository is on WSL ext4 and translates to the expected
internal WSL UNC form. Its roots are constants, not configuration or caller input:

```text
native root: C:\ColiseumRenderWorker\v1
WSL root:    /mnt/c/ColiseumRenderWorker/v1
job leaf:    jobs/<job_id>
```

The selected deployment profile is operational provenance. It is stored in the
host execution report and render manifest under the amendment-defined field in
section 8. It is not added to the existing `blender_job.v1` preimage: the same
reviewed job has the same scientific presentation identity whether a local drive
copy is necessary. Its exact source bytes, Blender identity, render profile,
inventory, repository commit, and source name already determine that job.

No environment variable, CLI option, job field, browser input, symlink, registry
value, or config file may replace either fixed root. A different Windows volume or
root requires another audited deployment profile.

## 4. Root initialization and native identity

The native guard creates or validates the fixed root before job preparation. It
must:

1. require local drive `C:` and reject UNC, device, drive-relative, alternate-data-
   stream, substituted-drive, volume-GUID alias, mount point, junction, symbolic
   link, and every reparse tag on the complete path;
2. open every existing component by handle with `FILE_FLAG_OPEN_REPARSE_POINT |
   FILE_FLAG_BACKUP_SEMANTICS` where applicable, resolve its final path, and bind
   volume serial plus `FILE_ID_128`;
3. require the final normalized handle path to equal the one closed native literal
   above under ordinal case-insensitive Windows comparison while preserving one
   canonical emitted spelling;
4. require an NTFS local fixed volume and refuse unavailable or indeterminate
   filesystem/reparse/identity information;
5. create missing `ColiseumRenderWorker`, `v1`, and `jobs` components one at a
   time without traversing a reparse point and apply a protected ACL granting the
   current interactive user, `SYSTEM`, and local `Administrators` only;
6. reopen and revalidate each created component before use; and
7. retain a non-delete-shared handle to `v1`, `jobs`, the fresh job directory,
   and its `input` directory for the complete copy-in, worker, inspector, and
   copy-out sequence.

The host independently requires that `/mnt/c` is the DrvFs view of the same `C:`
volume. The Windows handle identity is authoritative for staging. Linux descriptor
identity is authoritative for repository sources and final repository-derived
copies. An unavailable cross-view proof refuses before Blender starts.

The repository's internal WSL UNC translation is never passed to Blender or the
native guard. Linux proves that the opened repository and canonical protected roots
are on WSL ext4, outside `/mnt/c`; the native worker receives capabilities only for
the fixed staging job. This establishes disjointness without granting Windows
access to the canonical repository.

## 5. Authenticated copy-in

The host still constructs and validates the one-pass `blender_job.v1` from opened
repository source descriptors. It derives both leaves after identity:

```text
repository mirror: derived/textlab/visualization/blender/jobs/<job_id>
native staging:    C:\ColiseumRenderWorker\v1\jobs\<job_id>
```

Both leaves must be absent. The host creates the repository mirror through its
already-open `repo_derived` parent and the native guard creates the staging leaf
through the held native `jobs` handle. Reusing, overwriting, or partially resuming
an existing staging leaf is refused in this first amendment.

Copy-in is descriptor-to-descriptor and create-exclusive:

1. open each allowlisted repository worker script, inspector script, factory
   profile, and host-authored `job.json` with Linux no-follow semantics;
2. authenticate repository-relative identity and expected digest;
3. create the corresponding fixed staging file beneath the held staging `input`
   or job-directory handle with no overwrite;
4. copy bounded bytes, flush, close the write handle, reopen read-only with no
   write/delete sharing, and compare byte count and SHA-256;
5. compare the WSL host observation with the native guard's volume/file identity
   observation; and
6. retain native read-only/no-write-delete-shared handles through the applicable
   worker/inspector lifetime exactly as required by the integrated design.

The job and both launch-attestation preimages retain their existing fixed relative
paths. Native argument arrays use only fixed staging paths. Native paths never enter
the job identity or public Workshop projection.

Source replacement after its bytes were copied from an authenticated open
descriptor cannot affect the staged bytes. Any staged-file or staged-ancestor
replacement, modification, or identity drift blocks or refuses launch.

## 6. Watchable mirroring

The read-only Workshop remains pinned to the repository mirror, never to an
arbitrary `/mnt/c` path. A host telemetry adapter may mirror only these bounded
presentation files from the guarded staging leaf:

```text
progress.json
events.jsonl
preview.png
```

For each poll it reopens the staging file by the held job-directory capability,
enforces the integrated cap, parses/validates telemetry before publication, and
copies a canonical sanitized projection into the repository mirror atomically.
`preview.png` is copied only after PNG structure, dimensions, declared SHA-256,
and staging identity validate. The browser never receives a staging path.

Mirroring is observation only. It cannot start, cancel, retry, reprioritize, or
otherwise signal Blender. Closing the page has no process effect. A missed mirror
update has no effect on the worker or result validity.

## 7. Authenticated copy-out and terminal handling

Blender and the inspector write only to the guarded staging leaf. After both
processes terminate, the host and native guard perform all integrated worker,
output, PNG, scene, inspector, unexpected-file, cap, identity, and digest checks
against staging. A passing staging result is then copied out:

1. the source output is opened beneath the still-held native staging job handle;
2. its final volume/file identity, size, and SHA-256 must equal the validated
   worker/inspector bindings;
3. the destination is a fixed declared filename beneath the already-open fresh
   repository mirror, created with Linux no-follow/create-exclusive semantics;
4. bounded bytes are copied, flushed, reopened, and independently hashed;
5. the destination size/digest must equal staging before it can enter the
   repository render manifest; and
6. undeclared files in either the staging leaf or repository mirror refuse the
   terminal success relation.

The host writes `render-manifest.json` only in the repository mirror after all
copy-out checks. It may copy validated worker/inspector results, launch
attestations, operational telemetry, preview, render, and scene using their fixed
names; logs remain capped and nonpublic. No path follows a link.

Automatic staging deletion is not part of this amendment. A successful or failed
staging leaf remains forensic derived data until a separately reviewed cleanup
operation removes exactly one identity-validated leaf while holding its parent.
Existing leaves therefore refuse a repeat preparation rather than being silently
deleted.

Any failed copy-in, launch, validation, mirror, copy-out, cap, or identity check:

- has no render manifest;
- cannot promote source provenance;
- cannot mutate canonical run or Council content; and
- records only a closed host failure code and bounded operational detail.

## 8. Truthful renderer manifest

For `coliseum-smoke.v1`, section 10 is corrected as follows:

```text
renderer.render_engine == "CYCLES"
renderer.resolution == {"width":1280,"height":720,"percentage":100}
```

These values must equal `job.render_profile.render.engine` and the final render
width, height, and percentage. The host must additionally prove that the preview
PNG is 640 x 360 and the final PNG is 1280 x 720. A manifest cannot claim a
renderer or resolution different from the bound job and host-validated output.

The render manifest top-level schema gains exactly one required field:

```text
execution_profile   # direct-repo-derived.v1 | fixed-windows-staging.v1
```

This additive field makes the operational copy boundary visible without changing
the canonical source or job identity. Under the current environment it is the
literal `fixed-windows-staging.v1`.

Starting from section 10's normative fixed vector, replacing only the two
renderer values produces 3577 canonical UTF-8 bytes and SHA-256:

```text
0448277087bf4c1d5fa3c99acdedb36119db106ce65d062166dc50cda1a7ce4a
```

That 3577-byte value is the corrected *renderer-relation fixture before the
additive `execution_profile` field*. Adding
`"execution_profile":"fixed-windows-staging.v1"` and serializing with integrated
`schema.canonical_json` produces the complete amended vector: exactly 3624 UTF-8
bytes with SHA-256
`9392c5d4f2fea469c17d1bfa9bd42d457c9b559ac4adeb259c39977e7124c55e`.
Independent construction and reload must reproduce those literals. This two-step
statement prevents confusing a direct correction of the old vector with the new
complete schema.

The old 3588-byte / `dfc2f0...e457` manifest vector remains a historical
regression proving the inconsistency and must be rejected by the amended validator.

## 9. Native process containment

The Windows-native guard, not WSL `subprocess` alone, launches Blender. It retains
all section-4 and section-5 handles and uses a Windows Job Object with:

- kill-on-job-close;
- active-process limit one;
- 4 GiB per-process memory limit;
- 180-second per-process user-time limit;
- one worker or inspector child at a time; and
- host-enforced 180-second wall timeout.

It launches only the attested absolute Blender file identity with the exact
argument-array digest. Child-process assignment must succeed before execution can
continue; nested or escaped child creation, unavailable limits, assignment failure,
or guard termination fails closed. The host permits exactly two total Blender
launches: worker, then inspector.

The guard is a reviewed compiled helper with a version-bound source digest. It is
not a general command runner. Its interface has closed operation names, fixed file
roles, fixed roots, fixed Blender flags, bounded Base64 or length-prefixed values,
and no shell or arbitrary executable parameter.

## 10. Additional implementation tests

The integrated section-12 matrix remains required. Add ordinary tests proving:

1. the actual WSL ext4 repository selects `fixed-windows-staging.v1` and never
   passes its UNC translation to Blender;
2. a local-drive repository may select `direct-repo-derived.v1` only after every
   original proof;
3. the fixed root cannot be replaced by CLI, environment, job, symlink, junction,
   drive alias, UNC, device path, ADS, config, or browser data;
4. staging initialization rejects weak ACLs, non-NTFS/removable/network volumes,
   reparse components, identity drift, and indeterminate information;
5. existing/partial job leaves, overwrites, undeclared files, cross-job reuse, and
   output-before-input states refuse;
6. every copy-in and copy-out size/digest/identity mismatch refuses and leaves no
   manifest;
7. replacement races for every staged ancestor/input and every terminal output are
   blocked or detected while native handles remain held;
8. telemetry mirroring publishes only validated sanitized data and cannot control
   Blender;
9. repository-mirror output bytes equal their validated staging sources;
10. the historical Eevee/640x480 manifest is rejected;
11. a Cycles/1280x720 manifest with the wrong execution profile is rejected;
12. amended fixed-vector construction and reload reproduce the committed exact
    byte count and digest; and
13. canonical run bundles and non-protocol Council content remain byte-identical
    across the opt-in smoke execution.

The opt-in smoke report must bind the fixed staging root's native volume/file
identity, guard source and binary digests, deployment profile, copy-in/out digests,
Blender version/help captures, output digests, and repository-mirror manifest.

## 11. Implementation and authorization sequence

1. Independently audit this amendment.
2. Integrate it under plain Council GO.
3. Rebase or restart the waiting bounded Blender Workshop implementation on the
   integrated amendment.
4. Implement the native guard, authenticated staging copy, worker, inspector,
   Workshop, manifest, and tests as one narrow source.
5. Run normal tests without Blender.
6. Route implementation for independent audit.
7. After implementation GO and integration, run the opt-in local smoke proof and
   route its result through the applicable result-handoff protocol.

No design verdict alone authorizes Blender execution. No smoke success authorizes
canonical trajectory rendering; that remains the separately audited Society Seed
projection source.

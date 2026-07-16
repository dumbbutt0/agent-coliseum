# Blender Workshop Bridge — WSL fixed-staging and manifest-coherence amendment 1

Status: design amendment revision 4; no Blender execution or implementation
authorization. Revision 4 addresses `AUDIT_BLOCKED` event `001475-b576ce96` and
preserves the accepted closures from events `001465-fe8ff615` and
`001470-ad766480`.

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
closed `sandbox-execution-report.json` and render manifest under the
amendment-defined relations in section 8. It is not added to the existing
`blender_job.v1` preimage: the same reviewed job has the same scientific
presentation identity whether a local drive copy is necessary. Its exact source
bytes, Blender identity, render profile,
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
6. reopen and revalidate each created component before use;
7. retain a non-delete-shared handle to `v1`, `jobs`, the fresh job directory,
   and its `input` directory for the complete copy-in, worker, inspector, and
   copy-out sequence; and
8. grant the job-specific lowbox SID described in section 9 traverse-only access
   to the fixed ancestors, read access to the closed inputs, and read/write/create
   access only to the current fresh job leaf. No sibling leaf, fixed-root control
   file, or parent receives that SID's write ACE; apply a low mandatory-integrity
   label to the current job leaf so the lowbox can write there, while input DACLs
   remain read-only; and
9. immediately before the denial probe, seal the current leaf and every existing
   staged child with an exact protected DACL. The owner remains the exact queried
   interactive-user SID. An `OWNER RIGHTS` (`S-1-3-4`) deny ACE has the exact
   standard-right mask `WRITE_DAC | WRITE_OWNER` and **no** delete, create, write,
   append, attribute, EA, generic, or object-specific data bit. Presence of that SID
   suppresses the owner's otherwise implicit `READ_CONTROL` and `WRITE_DAC`; the
   explicit read-only user ACE restores only the required read relation. Ordinary-
   token data denial is by absence of an allow, not by an owner deny that would also
   match the derived lowbox's retained `TokenUser`.

   The ACL builder uses no generic rights and expands direct-directory,
   object-inherit, and container-inherit ACEs separately. The exact ordinary-user
   directory read mask is `READ_CONTROL | SYNCHRONIZE | FILE_LIST_DIRECTORY |
   FILE_TRAVERSE | FILE_READ_ATTRIBUTES | FILE_READ_EA`; the exact ordinary-user
   file read mask is `READ_CONTROL | SYNCHRONIZE | FILE_READ_DATA |
   FILE_READ_ATTRIBUTES | FILE_READ_EA`. Neither includes `DELETE`,
   `FILE_DELETE_CHILD`, any create/write/append bit, `WRITE_DAC`, or `WRITE_OWNER`.
   Every enabled SID in the interactive token, including an enabled Administrators
   group, has no data- or descriptor-mutation allow. There is no creator-owner or
   broad user/group write ACE.

   The lowbox's direct current-job/scratch directory mask is exactly `READ_CONTROL |
   SYNCHRONIZE | FILE_LIST_DIRECTORY | FILE_TRAVERSE | FILE_ADD_FILE |
   FILE_ADD_SUBDIRECTORY | FILE_READ_ATTRIBUTES | FILE_WRITE_ATTRIBUTES |
   FILE_READ_EA | FILE_WRITE_EA`; its created-file mask is exactly `READ_CONTROL |
   SYNCHRONIZE | FILE_READ_DATA | FILE_WRITE_DATA | FILE_APPEND_DATA |
   FILE_READ_ATTRIBUTES | FILE_WRITE_ATTRIBUTES | FILE_READ_EA | FILE_WRITE_EA`.
   Its input-directory and input-file masks are the corresponding ordinary read
   masks only. No lowbox ACE grants `WRITE_DAC`, `WRITE_OWNER`, `DELETE`, or
   `FILE_DELETE_CHILD`. `SYSTEM` alone receives the closed broker-control allow.
   The current-leaf DACL itself contains no inherited ACE; its explicit object- and
   container-inherit ACEs produce only these exact child masks. Every later-created
   child is reopened and query-checked against the exact expected inherited form
   before telemetry use or terminal admission.

   The guard must already hold the exact write/delete/security broker handles it
   needs before sealing. It queries back the owner SID, `SE_DACL_PRESENT |
   SE_DACL_PROTECTED` control flags, canonical ACE order, every SID/mask/type/
   inheritance bit, mandatory label, and effective access under both a duplicated
   interactive token and the exact effective lowbox token. The host token must be
   medium-integrity, non-elevated, and contain no `SeTakeOwnershipPrivilege`,
   `SeRestorePrivilege`, or `SeSecurityPrivilege`; presence or indeterminate state
   refuses. The paired preflight must prove the ordinary duplicate lacks DACL,
   owner, create, write, append, replace, delete, and delete-child access while the
   lowbox succeeds for its declared current-job create/write role and no other
   mutation role. Any mismatch, inherited/unknown ACE, owner drift, or descriptor
   drift refuses before a child starts. No DACL or owner change is permitted until
   terminal validation completes.

The host independently requires that `/mnt/c` is the DrvFs view of the same `C:`
volume. The Windows handle identity is authoritative for staging. Linux descriptor
identity is authoritative for repository sources and final repository-derived
copies. An unavailable cross-view proof refuses before Blender starts.

The repository's internal WSL UNC translation is never passed to Blender or the
native guard. Linux proves that the opened repository and canonical protected roots
are on WSL ext4, outside `/mnt/c`. The guard itself remains a trusted broker under
the interactive host identity, but both Blender children use the zero-network,
job-specific AppContainer/lowbox principal in section 9. Fixed pathnames, retained
handles, and Job Objects are not treated as filesystem capabilities. Disjointness
is established only after the effective lowbox token and its denial matrix pass.

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
watch-preview.png
```

For each poll it reopens the staging file by the held job-directory capability,
enforces the integrated cap, parses/validates telemetry before publication, and
copies a canonical sanitized projection into the repository mirror atomically.
The staging worker still writes its declared `preview.png`; the host publishes
those validated bytes in the repository mirror only as the distinct operational
`watch-preview.png`. The latter is not a worker output, launch input, manifest
output, or canonical evidence file. It is copied only after PNG structure,
640-by-360 dimensions, declared SHA-256, and staging identity validate. Repeated
polls with the same staging identity and digest are no-ops. A second publication
with a changed staging identity or digest, any mirror replacement, or any bytes
that do not rehash to the bound value terminally fails the job. The browser never
receives a staging path.

Mirroring is observation only. It cannot start, cancel, retry, reprioritize, or
otherwise signal Blender. Closing the page has no process effect. A missed mirror
update has no effect on the worker or result validity. On terminal success the
Workshop switches its preview endpoint to the validated final `preview.png`; on
failure it may continue displaying the explicitly nonterminal watch copy with a
failed banner.

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
6. undeclared files in the staging leaf refuse the terminal success relation; the
   repository mirror permits only its closed input/attestation/result/output/
   telemetry set plus the operational `watch-preview.png`, and every other file
   refuses success.

The host writes `render-manifest.json` only in the repository mirror after all
copy-out checks and after the passing sandbox execution report in section 8. It may
copy validated worker/inspector results, launch attestations, operational telemetry,
terminal preview, render, scene, and the sandbox report using their fixed names;
logs remain capped and nonpublic. Terminal `preview.png` is therefore absent until
its create-exclusive copy-out. `watch-preview.png` is never renamed, overwritten,
or admitted as that output. No path follows a link.

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

## 8. Truthful renderer and sandbox execution manifest

For `coliseum-smoke.v1`, section 10 is corrected as follows:

```text
renderer.render_engine == "CYCLES"
renderer.resolution == {"width":1280,"height":720,"percentage":100}
```

These values must equal `job.render_profile.render.engine` and the final render
width, height, and percentage. The host must additionally prove that the preview
PNG is 640 x 360 and the final PNG is 1280 x 720. A manifest cannot claim a
renderer or resolution different from the bound job and host-validated output.

The render manifest top-level schema gains exactly two required fields:

```text
execution_profile   # direct-repo-derived.v1 | fixed-windows-staging.v1
sandbox_execution   # closed binding below
```

This additive field makes the operational copy boundary visible without changing
the canonical source or job identity. Under the current environment it is the
literal `fixed-windows-staging.v1`.

`sandbox_execution` has exactly
`{schema_version, relative_path, byte_count, sha256, sandbox_profile}`. Its
values are:

```text
schema_version  == blender.sandbox_execution_report.v1
relative_path   == sandbox-execution-report.json
sandbox_profile == windows-appcontainer-job-lowbox.v1
byte_count      == independently observed positive JSON integer
sha256          == independently observed 64-lowercase-hex digest
```

The host authors canonical UTF-8 `sandbox-execution-report.json` only after the
guard returns both closed launch results. Its maximum is 65536 bytes, it has no BOM
or trailing byte, and its top-level key set is exactly:

```text
schema_version
job_id
execution_profile
sandbox_profile
guard
staging
token_policy
worker
inspector
protected_access_matrix_sha256
status
```

`schema_version`, `execution_profile`, and `sandbox_profile` equal the literals
above; `job_id` equals the recomputed job and every launch/result record; and
`status` is `passed` only after both children exit under the required token and all
access probes pass. `guard` has exactly
`{version,source_sha256,binary_sha256,compiler_identity_sha256,
denial_probe_source_sha256,denial_probe_binary_sha256,
sid_derivation_algorithm,sid_derivation_algorithm_sha256}`. The six SHA fields are
64 lowercase hex and equal the host's reviewed source/binary/compiler/probe
allowlist. `sid_derivation_algorithm` is the literal
`windows.DeriveAppContainerSidFromAppContainerName.v1`; its SHA is the digest of
the canonical UTF-8, no-newline object
`{api,appcontainer_name,schema_version}`, where `api` is
`DeriveAppContainerSidFromAppContainerName`, `appcontainer_name` is the report's
exact derived name, and `schema_version` is
`blender.appcontainer_sid_derivation.v1`. `staging` has exactly
`{root_volume_serial_number,root_file_id_hex,job_file_id_hex}`.
`token_policy` has exactly
`{appcontainer_name,appcontainer_sid,capability_sids,network_capabilities,
integrity_level,write_restricted,privileges,handle_inheritance_policy,
environment_policy}`. The capability, network-capability, and privilege arrays are
empty; integrity is `low`; `write_restricted` is true; and the two policy enums are
the section-9 literals. `worker` and `inspector` each have exactly
`{launch_attestation_id,argument_array_sha256,process_id,appcontainer_sid,
token_information_sha256,access_probe_sha256,job_object_profile,status}`;
process id is nonidentity operational telemetry, all SHA fields and attestation ids
are 64 lowercase hex, both SIDs equal the token policy, job-object profile is
`blender-bounded-child.v1`, and status is `passed`.

Each child `access_probe_sha256` is the digest of that child's canonical UTF-8,
no-newline `blender.protected_access_probe.v1` record. That record has exactly
`{schema_version,job_id,child_role,appcontainer_sid,token_information_sha256,
probe_source_sha256,probe_binary_sha256,entries}`; the probe identities equal the
two `guard` fields, `child_role` is respectively `worker` or `inspector`, and
`entries` is the complete array sorted by `(role,operation)` with each exact entry
`{role,operation,status,error_code}`. `status` is `allowed` only for the declared
current-job probe and `denied` for every required denial; `error_code` is the
observed nonnegative Windows code. Missing, duplicated, reordered, unknown, or
unprobed roles refuse.

`protected_access_matrix_sha256` is not an independent assertion. It must equal
SHA-256 over integrated canonical JSON UTF-8 with no newline of exactly:

```json
{"inspector_access_probe_sha256":"<inspector.access_probe_sha256>","schema_version":"blender.protected_access_matrix.v1","worker_access_probe_sha256":"<worker.access_probe_sha256>"}
```

The bracketed strings are replaced by the two exact report values before hashing.
Swapping roles, mixing a stale probe, changing either child digest, or supplying an
unrelated top-level digest therefore refuses deterministically.

The native guard's fixed protocol returns the token-information and access-probe
records over a bounded inherited pipe. The host independently revalidates the
guard source/binary/compiler and denial-probe source/binary allowlists, the exact
SID-derivation preimage, launch attestations, SIDs, array emptiness, token flags,
both child access-probe preimages, their defined aggregate, and child exit before
constructing the report. A missing, malformed, wrong-allowlist, mixed-profile,
mixed-job, stale, or failed report prevents the manifest. Neither report nor
manifest may be interpreted without the other.

This normative report fixture closes every key and relation. Repeated values are
fixture data, not host assertions. Its SID-derivation preimage hashes to
`7eeaadd8e88cd300cef0ae438d62f9ad83c09cd047689124dde10bda12e74043`;
the canonical worker/inspector aggregate preimage hashes to
`6ec732a93b53b49e7b80609387478cd2fad41bb66e692ff718419d7ed5964602`:

```json
{"execution_profile":"fixed-windows-staging.v1","guard":{"binary_sha256":"1111111111111111111111111111111111111111111111111111111111111111","compiler_identity_sha256":"1212121212121212121212121212121212121212121212121212121212121212","denial_probe_binary_sha256":"1414141414141414141414141414141414141414141414141414141414141414","denial_probe_source_sha256":"1313131313131313131313131313131313131313131313131313131313131313","sid_derivation_algorithm":"windows.DeriveAppContainerSidFromAppContainerName.v1","sid_derivation_algorithm_sha256":"7eeaadd8e88cd300cef0ae438d62f9ad83c09cd047689124dde10bda12e74043","source_sha256":"1010101010101010101010101010101010101010101010101010101010101010","version":"windows-native-guard.v1"},"inspector":{"access_probe_sha256":"3333333333333333333333333333333333333333333333333333333333333333","appcontainer_sid":"S-1-15-2-111111111-222222222-333333333-444444444-555555555-666666666-777777777","argument_array_sha256":"3131313131313131313131313131313131313131313131313131313131313131","job_object_profile":"blender-bounded-child.v1","launch_attestation_id":"3030303030303030303030303030303030303030303030303030303030303030","process_id":102,"status":"passed","token_information_sha256":"3232323232323232323232323232323232323232323232323232323232323232"},"job_id":"7070707070707070707070707070707070707070707070707070707070707070","protected_access_matrix_sha256":"6ec732a93b53b49e7b80609387478cd2fad41bb66e692ff718419d7ed5964602","sandbox_profile":"windows-appcontainer-job-lowbox.v1","schema_version":"blender.sandbox_execution_report.v1","staging":{"job_file_id_hex":"17171717171717171717171717171717","root_file_id_hex":"16161616161616161616161616161616","root_volume_serial_number":1},"status":"passed","token_policy":{"appcontainer_name":"AgentColiseum.BlenderWorker.v1.7070707070707070707070707070707070707070707070707070707070707070","appcontainer_sid":"S-1-15-2-111111111-222222222-333333333-444444444-555555555-666666666-777777777","capability_sids":[],"environment_policy":"closed-blender-lowbox-env.v1","handle_inheritance_policy":"stdio-pipes-only.v1","integrity_level":"low","network_capabilities":[],"privileges":[],"write_restricted":true},"worker":{"access_probe_sha256":"2323232323232323232323232323232323232323232323232323232323232323","appcontainer_sid":"S-1-15-2-111111111-222222222-333333333-444444444-555555555-666666666-777777777","argument_array_sha256":"2121212121212121212121212121212121212121212121212121212121212121","job_object_profile":"blender-bounded-child.v1","launch_attestation_id":"2020202020202020202020202020202020202020202020202020202020202020","process_id":101,"status":"passed","token_information_sha256":"2222222222222222222222222222222222222222222222222222222222222222"}}
```

It is exactly 2751 canonical UTF-8 bytes with no newline and SHA-256
`a4310fdaf5ed23b8f9fba2f050626fa46a2ce12cd2ca1e2ea322e25e581e484c`.
Independent construction must reproduce the SID preimage, aggregate preimage,
report length, and all three digests without trusting the document literals.

Starting from section 10's normative fixed vector, replacing only the two
renderer values produces 3577 canonical UTF-8 bytes and SHA-256:

```text
0448277087bf4c1d5fa3c99acdedb36119db106ce65d062166dc50cda1a7ce4a
```

That 3577-byte value is the corrected *renderer-relation fixture before the
additive execution fields*. Adding only
`"execution_profile":"fixed-windows-staging.v1"` and serializing with integrated
`schema.canonical_json` produces the revision-1 intermediate vector: exactly 3624
UTF-8 bytes with SHA-256
`9392c5d4f2fea469c17d1bfa9bd42d457c9b559ac4adeb259c39977e7124c55e`.
That intermediate value is no longer a complete accepted manifest because it lacks
`sandbox_execution`. For the normative revision-4 fixture, add exactly the binding
for the complete report above:

```json
{"byte_count":2751,"relative_path":"sandbox-execution-report.json","sandbox_profile":"windows-appcontainer-job-lowbox.v1","schema_version":"blender.sandbox_execution_report.v1","sha256":"a4310fdaf5ed23b8f9fba2f050626fa46a2ce12cd2ca1e2ea322e25e581e484c"}
```

as the top-level `sandbox_execution` value. The repeated size/digest are fixture
data, not an environment assertion. Starting from the original section-10 vector,
making the two renderer corrections, adding `execution_profile`, and adding that
exact object produces exactly 3898 canonical UTF-8 bytes with SHA-256
`9cd3ce9de5b9964912a2ba8ebfb674a897334452fb3837d6a9355b417fd86bf6`.
Independent construction and reload must reproduce those literals. This three-step
lineage prevents confusing the renderer correction, the superseded revision-1
staging schema, the revision-2 underbound sandbox report, and the complete
sandbox-bound schema.

Both the old 3588-byte / `dfc2f0...e457` renderer vector and the 3624-byte /
`9392c5...c55e` staging-only vector remain historical rejection fixtures. The
revision-2 3898-byte / `7059f24a...bcfab` vector is also rejected because its
bound report schema cannot carry the required probe and SID-derivation identities.

## 9. Native AppContainer process containment

The Windows-native guard, not WSL `subprocess` alone, launches Blender. Running a
child with the interactive user's token is forbidden even when its arguments,
handles, and Job Object are correct. Each job deterministically derives an
unregistered AppContainer SID from the fixed name
`AgentColiseum.BlenderWorker.v1.<job_id>`. The guard must not register an
AppContainer profile or create package-private storage. It creates a primary
lowbox token by this closed native sequence:

1. open the guard process token for query/duplicate only;
2. call `CreateRestrictedToken` with exactly
   `DISABLE_MAX_PRIVILEGE | WRITE_RESTRICTED`, the derived job SID as the sole
   restricting SID, all enabled nonmandatory group SIDs disabled, and no retained
   privileges;
3. duplicate it as a primary token, set low mandatory integrity, and query back
   the restriction, privilege, group, and integrity information;
4. call `CreateProcessAsUserW` with `EXTENDED_STARTUPINFO_PRESENT` and one
   `PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES` entry containing the exact
   AppContainer SID and zero capability SIDs; and
5. create suspended, assign the process to the Job Object, re-query its effective
   token, verify the inherited-handle list, and resume exactly once only after all
   relations succeed.

The resulting effective token must have:

- that exact AppContainer SID;
- zero capability SIDs;
- zero network capabilities;
- low mandatory integrity;
- all privileges removed;
- a write-restricted token policy;
- no interactive logon, desktop, clipboard, device, registry-write, or shell
  capability; and
- only the fixed staging-job ACL described in section 4.

The sandbox profile is `windows-appcontainer-job-lowbox.v1`. If the OS cannot
derive the SID, construct and query the effective lowbox token, keep the profile
unregistered, prove zero capabilities/privileges, or prove denial of package/user
storage and network access, the guard refuses before launch. It does not fall back
to a restricted same-user process.

The child environment is a closed allowlist. `TEMP`, `TMP`, `HOME`, `APPDATA`,
`LOCALAPPDATA`, `USERPROFILE`, and every Blender user-script/config/cache variable
resolve to a fixed `scratch` directory inside the current job leaf; proxy, Python,
add-on, startup, credential, network, and inherited search-path variables are
absent. The working directory is the current job leaf. Input files and their
directory are protected read-only from the lowbox SID; retained no-write/delete-
shared handles remain defense in depth. Only the current job leaf grants that SID
write/create access. Undeclared current-leaf files may be physically created by a
compromised child but are detected by the closed terminal inventory and can never
enter a manifest; no write outside the leaf may succeed.

Before Blender is eligible, the same guard launches a repository-owned harmless
native denial probe under the exact effective token, environment, handle list,
working directory, ACLs, and Job Object profile. The probe must demonstrate:

- one declared probe file in the current job succeeds;
- writes to the input directory, job specification, launch attestation, fixed root,
  `jobs` parent, and a sibling job fail;
- writes to the repository internal WSL UNC path, canonical-run root, Council root,
  repository sources, Windows user profile, Desktop, Documents, AppData, `%TEMP%`
  outside the rebound scratch, public directories, drive root, and another ordinary
  user-writable test root all fail;
- reads from repository sources, canonical-run roots, Council state, user-private
  paths, and the internal WSL UNC namespace also fail; only the attested Blender/
  Windows runtime dependencies and staged current-job inputs are readable;
- UNC/network connection, registry write, process escape, shell launch, and a
  second child all fail; and
- the only successful write's native parent identity equals the held current job.

Protected paths enter the probe through guard-opened identity roles, never browser
or job input. The probe output is a closed sorted role/status/error-code table. Its
canonical digest and queried token-information digest enter the sandbox execution
report. An unavailable protected role, surprising success, indeterminate denial,
different SID/token, or inability to delete the guard-created harmless probe file
through its held identity refuses Blender. Unit tests may use fake roots; the opt-in
same-host preflight must exercise the real protected identities without modifying
them.

The denial probe also attempts mutation from a second ordinary process running
with a duplicate of the guard's pre-seal interactive token while the sealed child
phase is active. For every staged role it first attempts `SetSecurityInfo`-style
DACL broadening and owner replacement, then create, replace, write, delete, and
delete-child. Every security-descriptor and data mutation must fail. The guard
queries the descriptor and effective token access again afterward and requires
byte-equivalent owner/control/ACE state. Against that same queried descriptor, the
effective lowbox denial probe must create and write its one declared current-job
probe, must lack `WRITE_DAC`, `WRITE_OWNER`, `DELETE`, and `FILE_DELETE_CHILD`, and
must fail every other protected role in the complete matrix. This paired result
proves the narrow `OWNER RIGHTS` restriction blocks owner control without defeating
the distinct lowbox-SID data allow, while a different same-user process cannot
restore write access or inject a later output.

The guard retains all section-4 and section-5 handles and uses a Windows Job Object
with:

- kill-on-job-close;
- active-process limit one;
- 4 GiB per-process memory limit;
- 180-second per-process user-time limit;
- one worker or inspector child at a time; and
- host-enforced 180-second wall timeout.

The Job Object also applies the closed UI restriction class denying desktop switch,
global atoms, clipboard, system parameters, handles outside the explicit inherited
handle list, and display-setting changes. `PROC_THREAD_ATTRIBUTE_HANDLE_LIST` is
used with exactly the bounded stdout/stderr pipes; no staging, broker, token,
repository, Council, or source handle is inheritable. The handle policy literal is
`stdio-pipes-only.v1`; the environment policy literal is
`closed-blender-lowbox-env.v1`.

It launches only the attested absolute Blender file identity with the exact
argument-array digest. Child-process assignment must succeed before execution can
continue; nested or escaped child creation, unavailable limits, assignment failure,
or guard termination fails closed. The host permits exactly two total Blender
launches: worker, then inspector.

The guard is a reviewed compiled helper with a version-bound source digest. It is
not a general command runner. Its interface has closed operation names, fixed file
roles, fixed roots, fixed Blender flags, bounded Base64 or length-prefixed values,
and no shell or arbitrary executable parameter.

The guard source, compiled binary, compiler identity, denial-probe source/binary,
fixed sandbox profile, and expected SID derivation algorithm are allowlisted by the
host implementation and bound into `sandbox-execution-report.json`. Runtime
compilation is not accepted unless the implementation source defines and audits a
deterministic compiler-input/output binding; an arbitrary binary with the right
version string refuses.

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
9. live observation uses only `watch-preview.png`, terminal `preview.png` remains
   create-exclusive, repeated identical polls are no-ops, and every mirror/staging
   identity or byte drift leaves no manifest;
10. repository-mirror output bytes equal their validated staging sources;
11. the historical Eevee/640x480 and staging-only manifest vectors are rejected;
12. a Cycles/1280x720 manifest with a wrong execution or sandbox profile is
    rejected;
13. the sandbox report rejects wrong SID, capabilities, privileges, token flags,
    guard/compiler/binary identity, denial-probe source or binary, SID-derivation
    algorithm or digest, unequal/stale/mixed child probes or aggregate access
    matrix, job, launch, and mixed profile;
14. a paired access check against one exact queried descriptor proves the ordinary
    pre-seal-token duplicate lacks descriptor and data mutation while a harmless
    fake child under the actual lowbox token writes its declared current-job probe;
    every sibling, parent, repository UNC, canonical, Council, repository-source,
    user-profile, public, temp, registry, network, shell, and process-escape probe
    is denied, and protected/private read probes are denied;
15. after child-phase ACL sealing, a second interactive-user process cannot broaden
    the DACL, replace the owner, create, write, replace, or delete a staging input,
    output, telemetry file, or undeclared file, and the exact descriptor is unchanged;
16. an interactive-user, low-integrity-only, Job-Object-only, or unavailable-token
    fallback is refused before Blender;
17. complete revision-4 report and manifest construction and reload reproduce the
    2751-byte / `a4310fda...e484c` report and 3898-byte /
    `9cd3ce9d...6bf6` manifest fixtures, while the revision-2 vector refuses; and
18. canonical run bundles and non-protocol Council content remain byte-identical
    across the opt-in smoke execution.

The opt-in smoke report must bind the fixed staging root's native volume/file
identity, guard source/binary/compiler digests, lowbox SID/token/access-probe
digests, deployment and sandbox profiles, copy-in/out digests, Blender version/help
captures, output digests, sandbox execution report, and repository-mirror manifest.

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

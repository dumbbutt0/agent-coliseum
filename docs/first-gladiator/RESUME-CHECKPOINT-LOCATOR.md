# Resume-Checkpoint Locator (repo descriptor)

This is a **static descriptor**. It deliberately contains **no checkpoint hash and no
chain head** — those live only in the external checkpoint and in the locator's live
validation output, because they change on every append. This file only tells a reader
*where the checkpoint is and why a repo search cannot find it*.

## The checkpoint lives OUTSIDE this repository

The machine-readable resume checkpoint is a single file:

- **filename:** `resume_checkpoint.json`
- **location:** the **configured council root** — `get_config().council_root` — which is
  a **separate directory from this git repo** (it is chain-adjacent, sitting next to
  `events.jsonl`). It is intentionally **not tracked in git**, like all council
  operational state.
- **stable locator convention:** `council-root://resume_checkpoint.json` — a
  council-root-relative name, **not** an absolute machine path. The concrete path is
  resolved from configuration at call time, never hard-coded.

Because the artifact is outside the repo, a **repo-only search (e.g. a Codex audit run)
cannot discover it** — it will find only this descriptor and the locator string in
`tools/council/resume_locator.py`. There is **no copy or mirror** of the checkpoint
inside the repository, and there must never be one. The **external checkpoint is the
sole source of truth** for resuming an interrupted session.

## Resolve + validate it

```
python3 -m tools.council.cli locate-resume-checkpoint --json
```

The command resolves the path strictly from configuration and validates the checkpoint
against the live chain and policy pin. Its JSON reports: the configured `council_root`,
the resolved path, existence, schema version, recorded vs. recomputed content hash, the
checkpoint's chain head + length, the live chain head + length, the policy-pin
comparison, a typed `status`, `resume_authorized`, and typed failure `reasons`. It exits
`0` only when resume is authorized (a fully validated `RESOLVED`).

To resolve the council root directly:

```
python3 -c "from tools.council import get_config; print(get_config(role='claude').council_root)"
```

## Fail-closed semantics (typed `status`)

| status | meaning | resume |
| --- | --- | --- |
| `RESOLVED` | accessible root, present + well-formed artifact, content hash matches, chain binding consistent with the live chain, policy pin matches | **authorized** |
| `CHECKPOINT_ARTIFACT_UNAVAILABLE` | the configured council root is **not accessible** (or its chain is unreadable) — the auditor cannot determine checkpoint state | fails closed |
| `CHECKPOINT_MISSING` | root accessible, but **no** checkpoint file at the resolved path | fails closed |
| `CHECKPOINT_MALFORMED` | present but not a well-formed JSON object | fails closed |
| `CONTENT_HASH_MISMATCH` | recorded `checkpoint_hash` ≠ recomputed content hash (edited out of band) | fails closed |
| `STALE_CHAIN_BINDING` | the recorded chain head is not a prefix of the live chain (stale or divergent) | fails closed |
| `POLICY_PIN_MISMATCH` | the recorded effective policy pin ≠ the live pin | fails closed |

`CHECKPOINT_ARTIFACT_UNAVAILABLE` is **distinct from** `CHECKPOINT_MISSING`: an
inaccessible council root never claims "no checkpoint exists." Unavailability fails
closed for **resume authority only** and leaves unrelated read-only auditing available.

## Scope

The resolver (`tools/council/resume_locator.py`) is **generic**: it imports no project
(Coliseum) code and assumes no project-specific registry — it depends only on the
generic council chain + policy primitives. This is structural discoverability work, not
a policy amendment, activation, authority expansion, or owner decision.

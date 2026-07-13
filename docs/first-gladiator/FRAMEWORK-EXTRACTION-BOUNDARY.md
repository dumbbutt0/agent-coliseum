# Council Framework Extraction — Boundary & Slice Plan (priority #3)

**Goal.** Make the IMPLEMENTED council engine in `tools/council/` a *reusable, project-independent
framework* by turning Coliseum-specific **content** into **injected** content, so a different program
could run the same engine by supplying its own profile. This is a content-injection refactor, **not** a
physical relocation and **not** an import untangling — the import seam already holds (there is zero
`import coliseum` / `from coliseum` anywhere under `tools/council/`, verified 2026-07-13).

This work does **not** require governance activation; it is Class-A structural-source work under the
established build→Codex-audit→integrate path. Each slice is bounded, independently Codex-audited, and
**behavior-preserving for Coliseum** (the existing suite stays green; the live chain/identity/policy are
untouched).

**Inviolable (owner-directed).** Extraction must NOT weaken any of: append-only hash-chained history,
independent audits, hidden-evaluation controls, identity binding, critical-violation vetoes, or the
owner's revocation power. If a slice cannot preserve all of these it fails closed and stops for the owner.

## What is generic (framework) vs Coliseum (injected profile)

| Layer | Framework (generic mechanism) | Coliseum profile (injected content) |
| --- | --- | --- |
| FS/crypto leaves | `strictjson`, `storage`, `locking`, `txn`, `git_state`, `resume_locator` | — |
| Chain | `events` append/verify pipeline; `state_machine` FSM engine | the transition table + per-event verify hooks |
| Identity | hash-chained identity + enrollment-anchor **check** | the anchor **location** (deploy-time, see security note) |
| Policy | pin / amend / effective-pin walk; authorization-oracle shapes | `POLICY_ID`, `POLICY_VERSIONS` v1–v5, per-profile evaluators |
| Vocabulary | event-type / role / token-required **registries** | the specific event types, the `claude/codex/human` cast |
| Config | `Config` + `get_config()` shape | `DEFAULT_COUNCIL_ROOT`, `DEFAULT_REPO_ROOTS`, test-command paths |

Four extension points let the profile inject content instead of the core hard-coding it:
1. **Config/paths** — framework core carries no project defaults; the profile supplies council_root,
   repo_roots, and test commands.
2. **Role registry** — replace the hard-coded `ROLES=("claude","codex","human")` with an injected role
   set + per-role authority map (only the owner/human role is crypto-bound).
3. **Event-type registry** — event types + token-required/verdict frozensets become a registered
   vocabulary the FSM and append hooks consult by name.
4. **Policy-profile registry** — the profile registers its `POLICY_VERSIONS` + evaluators; the core keeps
   only the pin/amend/verify walk and calls registered evaluators by name (no `eff_version >= 4` inline).

## Security note — the anchor-injection model (the one slice that can weaken a control)

`ENROLLMENT_HASH_FILE` (`identity.py:126`, `/etc/coliseum/enrollment.sha256`) and `CHECKPOINT_FILE`
(`checkpoint.py:24`, `/etc/coliseum/chain-head.sha256`) are **deliberately** root-owned, agent-unwritable
absolute paths. The append pipeline verifies every human token against the enrollment anchor
(`events.py:226`); the chain-head checkpoint is the external anti-rewrite commitment. **Their whole
security value is that the agent user cannot write OR redirect them.**

Therefore, when these paths become "injected," the injection channel MUST remain outside agent write
authority: they are **deployment configuration** set by the operator/root, never a runtime, agent-settable
value (an env var the agent process controls, or a repo/agent-writable config file, is NOT acceptable). A
delegated program must not be able to point its own identity anchor at a file it controls. This slice is
sequenced **last** and carries adversarial tests proving no agent-writable channel can redirect the anchor.

## Slice sequence (smallest / safest first; security-critical last)

- **S1 — de-hardcode project defaults.** Move `DEFAULT_COUNCIL_ROOT` / `DEFAULT_REPO_ROOTS` out of the
  generic core; the framework core requires them via config, a Coliseum profile supplies the current
  values. Behavior byte-identical. No security surface. *(first)*
- **S2 — role registry.** Injected role set + authority map; Coliseum registers `claude/codex/human`.
- **S3 — event-type registry.** Injected event vocabulary + token/verdict sets + FSM transition table;
  Coliseum registers its lifecycle. `EXPERIMENT_TEST_COMMAND` moves to the profile.
- **S4 — policy-profile registry.** Core keeps the pin/amend/verify walk + oracle shapes; Coliseum
  registers `POLICY_VERSIONS` and the delegation/governance/revocation evaluators.
- **S5 — anchor deployment-config model (security-critical, adversarially audited).** Enrollment +
  chain-head anchor locations become operator/deploy configuration that no agent-writable channel can set.

Each slice: build + tests (incl. a Coliseum-unchanged regression) → commit → route as a `source` request →
Codex adversarial audit → integrate on a valid verdict. Stop for the owner on any Class-C authority
expansion, a blocked verdict past the cycle bound, or any inability to preserve the inviolable controls.

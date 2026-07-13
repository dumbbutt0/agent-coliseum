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

> **Scope decision (2026-07-13, owner): LIGHT.** Ship the safe, high-value decoupling (slice **S1**, done +
> integrated) and **document** the framework/adapter boundary + the four injection seams as the reusability
> contract — but make **no further code changes** to the role, event-type, policy, or anchor internals.
> Rationale: every remaining slice (S2–S5) would refactor code that *implements* a constitutional safety
> control (the crypto-bound-role check in the policy pin-walk and `identity.py`; the policy engine; the
> `/etc/coliseum` anti-tamper anchors), for reusability value that has **no second consumer yet**. **What S1
> delivers is precisely bounded: deployment portability (the council root / repo roots are injectable, no
> baked-in machine path) and import decoupling (the core imports no `coliseum` code). It does NOT deliver
> complete project independence** — the roles, event vocabulary, policy versions, and anti-tamper anchors
> all remain Coliseum-profile-bound until S2–S5 (or an equivalent second-consumer extraction) are actually
> implemented. **S2–S5 below are the documented, not-yet-built extension design; building any of them
> requires explicit owner go-ahead.**

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

## Slice sequence (S1 built; S2–S5 documented-but-deferred per the LIGHT decision)

- **S1 — de-hardcode project defaults. ✅ BUILT + INTEGRATED** (commit `9dbdb5ac`, plain GO `000808`,
  `CHANGE_INTEGRATED` **000809**; suite 1075 passed). `DEFAULT_COUNCIL_ROOT` / `DEFAULT_REPO_ROOTS` moved
  out of the generic core into `tools/council/site_defaults.py` + a runtime `register_site_defaults()`
  hook; `get_config()` resolution byte-identical (env → runtime override → site default). No security
  surface. This realizes injection **seam #1** below.
- **S2 — role registry. ⏸ DEFERRED (design only).** Injected role set + authority map; Coliseum registers
  `claude/codex/human`. Touches the crypto-bound-role literal in `policy.py:306` (pin-walk) and
  `identity.py` — constitutional-control code. *Build requires explicit owner go-ahead.*
- **S3 — event-type registry. ⏸ DEFERRED (design only).** Injected event vocabulary + token/verdict sets +
  FSM transition table; Coliseum registers its lifecycle; `EXPERIMENT_TEST_COMMAND` moves to the profile.
- **S4 — policy-profile registry. ⏸ DEFERRED (design only).** Core keeps the pin/amend/verify walk + oracle
  shapes; Coliseum registers `POLICY_VERSIONS` and the delegation/governance/revocation evaluators.
- **S5 — anchor deployment-config model. ⏸ DEFERRED (design only, security-critical).** Enrollment +
  chain-head anchor locations become operator/deploy configuration that no agent-writable channel can set;
  must ship with adversarial "an agent cannot redirect its own anchor" tests.

If any deferred slice is later authorized, each proceeds as: build + tests (incl. a Coliseum-unchanged
regression) → commit → route as a `source` request → Codex adversarial audit → integrate on a valid
verdict. Stop for the owner on any Class-C authority expansion, a blocked verdict past the cycle bound, or
any inability to preserve the inviolable controls.

## What S1 delivers, precisely (and what it does NOT)

**Delivered by S1:** (1) **deployment portability** — the council root and repo roots are injectable (env
vars or `register_site_defaults(...)`), so no machine-specific path is baked into the generic core; and
(2) **import decoupling** — `tools/council/*` imports no `coliseum` code. A second deployment could point
the engine at its own filesystem locations without editing the package.

**NOT delivered by S1 (still Coliseum-profile-bound):** the **roles** (`claude/codex/human`), the **event
vocabulary** (`SENDER_ALLOWED`, token/verdict sets, the FSM table), the **policy versions/evaluators**
(`POLICY_VERSIONS`, delegation/governance/revocation), and the **anti-tamper anchors** (`/etc/coliseum`
enrollment + chain-head). These remain welded to the Coliseum profile until S2–S5 (or an equivalent
second-consumer extraction) are implemented. So the engine is **import-decoupled and deployment-portable
after S1 — not project-independent.** A genuinely second consumer would still have to parameterize the four
injection seams above (only seam #1, config/paths, is implemented) before it could run its own roles,
events, or policy.

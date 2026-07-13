# Governance v4 (A/B/C/D `governance_v1`) — Owner Activation Package

This is the single **Class-D, owner-reserved** action that turns on the A/B/C/D
governance machinery. Only the owner can mint the S/KEY token; **Claude never runs it.**
Until this authenticated amendment occurs, the v3 policy remains authoritative and the
entire governance machinery stays **INERT**.

## What one command activates

A single owner-authenticated amendment advances the effective policy pin **v3 → v4
(`governance_v1`)**. Delegation (v3) is **retained** — v4 is forward-additive. This flips
the fully-integrated but currently **INERT** machinery to **live**:

| Slice | Generic core (`tools/council`) | Coliseum adapter/driver | Integrated (inert) |
| --- | --- | --- | --- |
| G1 | `governance_route` — routes A→delegation, B→codex_lifecycle, C→council, D→owner; fail-closed→D | — | `057b1300` (chain 742) |
| G2 | `evaluate_class_c` — 7 frozen gates; append-boundary on `COUNCIL_RESOLVED` | — | chain 742 |
| G3 | `acceptance_authorization` (generic; no claim states) | `accepted_transition` (claim-ladder mutation) | `115bdb17` (000760) |
| G4 | `continuation_status` + `evaluate_matter_accepted` + `MATTER_ACCEPTED` (exactly-once, chain-anchored) | `continue_acceptance` (durable, resumable, idempotent driver) | `1613268e` (000772) |

The resume-checkpoint locator (`locate-resume-checkpoint`, `3443444b`, event 000784) is
**already live** — it is read-only discoverability and is not gated on v4.

## Preconditions (verify before activating)

```
python3 -m tools.council.cli verify-chain                                    # chain healthy
python3 -m tools.council.cli --role claude locate-resume-checkpoint --json   # policy_pin.live.version == 3
```
- All governance `CHANGE_INTEGRATED` events present (G1–G4 + locator), each **INERT**.
- Working tree clean at the integrated HEAD.

## The single command (owner-reserved)

```
python3 -m tools.council.cli --role human amend-policy \
    --target-version 4 \
    --impl-commit 3443444b01e02aee1edf4155777e86f099eff890
```

- `--impl-commit` names the last audited machinery commit (the integrated
  checkpoint-locator HEAD, which contains the complete G1–G4 machinery). Strict
  "version-introducing" semantics would instead name G1
  `057b13001cc2668546eebee015b3a9ec33e89599`.
- Prompts for the owner passphrase (S/KEY) — never on argv.
- Writes `POLICY_VERSIONS[4]` over the policy file and records **one** `POLICY_AMENDED`
  binding `{prev_policy_hash = be3c42b1…, new v4 hash, policy_version = 4, diff,
  impl_commit, owner token}`.
- **Atomic**: any token/append failure rolls the file back to v3 (no unpinned drift).

## Expected transition

- `effective_policy_pin`: `(be3c42b1…, 3) → (<new v4 hash>, 4)`.
- `governance.enabled == true`; `governance_route` / `evaluate_class_c` /
  `acceptance_authorization` / `continuation_status` become authorized on the
  owner-ratified pin.
- Delegation stays active (v4 retains v3). No code changes — only the pin moves.

## Post-activation verification

```
python3 -m tools.council.cli verify-chain
python3 -m tools.council.cli --role claude status                            # pin shows v4
python3 -m tools.council.cli --role claude locate-resume-checkpoint --json   # policy_pin.live.version == 4
```
**Expected, not an error:** the existing resume checkpoint is pinned to v3, so immediately
after activation the locator reports `POLICY_PIN_MISMATCH` until the checkpoint is
refreshed to the v4 pin.

## Digest note (why no pre-computed hash)

The v4 on-disk policy file embeds an `amended_utc` timestamp, so its exact hash is known
only after the write. Verify by confirming `amend-policy` prints **version 4** and a
`new_hash`, and that `governance.enabled` is true — do not rely on a pre-computed digest.

## Revocation path

`v5` (delegation-revocation) is code-defined and forward-additive: a future single owner
amend to v5 disables delegation while keeping governance. The pin is monotonic (no
downgrade); undoing an erroneous activation is itself an owner decision.

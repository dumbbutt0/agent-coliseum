# Minimal Society Seed — evidence pack + report

Date: 2026-07-14. Under **OWNER AUTHORIZATION SC-LC (2026-07-14)**, execution-order
step 7 (the final step). The scripted Minimal Society Seed is designed, audited,
integrated, and its deterministic evidence pack is run. **The program stops here**
— live-persona Society runs and adaptive Butterfly phases require separate owner
authorization.

**Claim ceiling (enforced in code):** *the scripted seed demonstrates
deterministic room separation, private information, institutional enforcement,
trust bookkeeping, and counterfactual replay in one bounded run; it makes no
human-fidelity or society-simulation claim.*

## 1. State of record

| Fact | Value |
|---|---|
| Repo HEAD | `6a20ee2292244d5139f8d182913e4b9fd48ecc00` |
| Council chain | 1270 events, verify-chain OK, control active, `autonomy_paused` false, policy v4 |
| Full suite | **1404 passed / 13 skipped** |
| Design source | `MINIMAL-SOCIETY-SEED.md` rev 1, integrated 001238 @ `85c22433` (first-cycle GO 001237) |
| Implementation | integrated 001270 @ `6a20ee22` (plain GO 001269) |

Implementation audit trajectory (every finding real, fixed additively, contract
never weakened): -001 BLOCKED 001243 (4 HIGH) → -002 external content filter
killed the auditor session (rerouted per the owner's audit probe-reroute policy)
→ -003 filter-safe BLOCKED 001257 (3 HIGH) → -004 BLOCKED 001263 (2 HIGH
fail-open) → -005 GO 001269.

## 2. The bounded seed (exactly the SC-LC scope)

Three rooms A–B–C; three scripted agents ada(A)/bo(B)/cy(C); one portable token
(floor A); one private Boolean fact `cy.gem_in_box` (a gem inside a box in C,
invisible to every actor view); eight deterministic ticks (scheduler rounds
0–7); the fixed six-kind spatial action vocabulary; one hard-coded institutional
rule; six integer trust edges; one authenticated counterfactual fork. The
society layer is derived ABOVE byte-identical spatial evidence (the spatial six
files equal a plain spatial run — a committed regression).

Canonical run: **`society_seed_v1--seed42--b4f03e16d88940f3`**.

## 3. The ten required proofs — results

| # | Required proof | Result |
|---|---|---|
| 1 | Byte-identical replay | **PASS** — the eight-file replay gate (run.json, chain, transitions, observations, activations, closure, society.jsonl, society_report.json) re-executes from nothing and byte-matches |
| 2 | Per-agent perception non-interference | **PASS** — the fork's per-agent perception-divergence coordinates `{ada:16, bo:16, cy:17}` all lie beyond fork position 14; agents perceive cy's counterfactual at different coordinates (fog/privacy scoping) |
| 3 | Deterministic scheduling + trust updates | **PASS** — trust re-derives byte-identically; final matrix `{bo→ada:+1, else 0}`; the single update is a witnessed give with its justifying `actor_observation_id` provenance |
| 4 | Object location + possession invariants | **PASS** — the token has exactly one authoritative placement at every state (S2A-admitted); terminal location room_A (the institutional rule kept it there) |
| 5 | Institutional-rule enforcement trace | **PASS** — 2 enforcement events under `institution.token_stays_in_a.v1`; the committed script is rule-clean (no committed move is blocked); a blocked intent refuses at build time |
| 6 | Fork isolation + authenticated ancestry | **PASS** — distinct world lines via the integrated witnessed-fork machinery; parent evidence replays byte-identically after the fork; pair `a0d2e8c9…`, divergence report `c0806da6…` |
| 7 | Valid TRS trajectory records | **PASS** — `project_spatial_trajectory` yields per-agent manifests for ada/bo/cy over the seed run directory (schema-0.2-compatible core) |
| 8 | Actor-safe + privileged reports | **PASS** — closed-schema actor-safe reports carry only each agent's own outgoing trust (`ada:{ada→*:0}`, `bo:{bo→ada:1,bo→cy:0}`, `cy:{cy→*:0}`), no other agent's trust/facts/privileged content; the privileged report carries the full 6-edge matrix + enforcement trace |
| 9 | Society outcome report, no simulation claim | **PASS** — the closed `SocietyOutcomeReport` carries the final trust matrix, token terminal location, enforcement count, private fact, the canonical fork divergence summary, and the fixed claim ceiling; any other claim string refuses |
| 10 | Permanent regression coverage for every reproduced finding | **PASS** — 24 committed tests: all ten proofs + twelve pinned threat vectors (counterfeit chain, perception-scoped trust, committed-blocked-move refusal, tick drift, fork transplant, spatial non-interference byte-equality, closed actor schema, evidence tamper via the replay gate, claim-ceiling violation, private-fact cardinality closure, per-agent-divergence-beyond-fork, coordinated fork-forgery via replay) |

## 4. Pinned identities (permanent regressions)

- society run manifest: `7a7353b67adc3d0fe90968e7a0d2bcff7a76bbb928a0ca4654deb8fc2d18fe25`
- eight-file source binding: `cccc3f8555b92d0bbc8c8f8a999105c09f8b0b98df4b1c65c50711dae6677a07`
- outcome report: `7ff002a73a52192a9bb8f3163dd5e4dc5221e9996cf5d07fcc012deb6d4337f3`
- fork matched pair: `a0d2e8c9895299c04e808ff034797085d826aaeed1ffbbd8edc9eba8ca372bd9`
- fork divergence report: `c0806da62446287a4081a7b4af6524bb3003854d25c8c8c974ff47a8deb9df9d`

## 5. What the seed proves together (the owner's question)

Room separation (agents perceive only their own room), private information (the
gem never enters an actor view), institutional enforcement (a token-holder is
blocked from leaving room A, trace non-empty, script rule-clean), trust evolution
(perception-scoped: bo trusts ada more only because bo *witnessed* the give), and
counterfactual replay (the private-fact flip forks with authenticated ancestry,
leaves the parent unmutated, and its per-agent perception divergence proves the
counterfactual reaches each agent at a different, fog-shaped coordinate) — all in
one bounded, byte-replayable run.

## 6. Reproduce

```
cd /home/dummy/agent-coliseum
python3 -c "from coliseum.textlab.society.run import execute_society_seed, replay_society_seed; \
s=execute_society_seed(42); print(s['run_id']); print(replay_society_seed(s['run_id']))"
python3 -m pytest tests/test_society_seed.py -q
```

## 7. Stop

Per SC-LC, the program stops after this evidence pack. **Live-persona Society
runs, adaptive Butterfly phases, T0-B labels, training, and any expansion beyond
the bounded seed require separate owner authorization.** The next meaningful
question is the owner's: the scripted seed has now proven room separation,
private information, institutional enforcement, trust evolution, and
counterfactual replay together.

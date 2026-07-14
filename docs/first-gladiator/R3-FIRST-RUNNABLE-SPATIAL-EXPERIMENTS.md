# R3 — First Runnable Spatial Experiments (report + decision brief)

Date: 2026-07-14. Author: Claude (autonomous, under the owner's binding
runnable-experiments master directive, 2026-07-13). Status: **R3 REACHED.**

## 1. State of record

| Fact | Value |
|---|---|
| Repo HEAD | `36a46fbbef8b81ed29f6918976d3d5ec45be051c` |
| Council chain | 1172 events, head `fcd0693e4beede7f...`, verify-chain OK, control active, autonomy_paused false |
| Policy | v4 active (owner pin `2dd060fd`), delegation retained |
| Full suite | **1350 passed / 13 skipped** (`python3 -m pytest tests/ -q`) |

Integrated sources (design + implementation, each on a Codex plain GO):

| Slice | Design | Implementation |
|---|---|---|
| S2A mutable exclusive-location state | 001018 (rev 6) | 001036 |
| S2B deterministic scheduler (pure linear replay chain) | 001102 @ `e79b4cf4` (rev 11) | **001136 @ `9e773591`** (audit cycles: filter-kill -> 3 HIGH -> 2 HIGH -> 1 HIGH -> GO 001135) |
| S2C perception + non-interference | **001154 @ `be6991a7`** (rev 3; GO 001153) | **001166 @ `c4d9295`** (GO 001165) |
| S2D scripted runner + CLI + scenario | (master directive step 4 as authority) | **001172 @ `36a46fbb`** (GO 001171, first cycle) |

All audits ran under the owner's audit probe-reroute policy (filter-safe
methodology; acceptance criteria unchanged). Every AUDIT_BLOCKED finding across
the program was real, reproduced, and fixed additively; no contract was weakened.

## 2. The exact first command

```
cd /home/dummy/agent-coliseum
python3 -m coliseum.textlab.cli spatial-run --scenario spatial_two_agent_private_object_v1 --seed 42
python3 -m coliseum.textlab.cli spatial-replay spatial_two_agent_private_object_v1--seed42--e5657a18d0970388
python3 -m coliseum.textlab.cli spatial-inspect spatial_two_agent_private_object_v1--seed42--e5657a18d0970388 --view actor --agent alice
```

Evidence root: `logs/spatial-runs/` (separate from the vignette `logs/runs` tree).
Run identities are content-addressed; no wall-clock or host entropy enters any
evidence byte, so the run id above is stable on every machine.

## 3. Run pack results (A-E)

**A — canonical smoke: PASS.**
`spatial-run --scenario spatial_two_agent_private_object_v1 --seed 42` ->
run id `spatial_two_agent_private_object_v1--seed42--e5657a18d0970388`;
manifest `e5657a18d09703888958b7483587c0fce8211f5c6a6f77439f089e821c01898a`;
6 scheduler states (explicit stop 5, fork point 1); terminal world state
`7f8b8f3c18e2603b37a2332e38e387b9b948cf8178fc08129b8575524b6eb08d`;
verify_manifest whole-chain re-derivation runs BEFORE evidence is written.
Scenario content: 2 connected rooms; alice+bob (scripted); 1 portable token;
1 private gem INSIDE a container box; alice takes the token (object interaction +
the state-dependent legality change), bob crosses B->A (portal move), both cross
to B; 12 observations (2 observers x 6 positions), both views.

**B — fresh replay / reconstruction: PASS.**
`spatial-replay` re-executes from NOTHING and byte-compares every evidence file:
`byte-identical: run.json, chain.jsonl, transitions.jsonl, observations.jsonl`.
Tamper matrix (on evidence copies): truncated / appended / reordered chain.jsonl
each REJECTED by the gate. Re-execution across independent roots is byte-identical;
insertion-order variation never changes identities (committed regressions).

**C — perception non-interference twin: PASS.**
For EVERY chain position and BOTH observers (12 pairs): the twin state differing
ONLY in hidden content (the private gem) renders an IDENTICAL actor observation id
and a DIFFERENT privileged id. The private object appears in NO actor view at any
position for either agent (also verified from evidence alone by the committed
runner tests). Script: appendix C.

**D — counterfactual fork: PASS.**
At the recorded fork point (position 1; alice holds the token): fork genesis
authenticated WITH the S2B reachability witness and REFUSED without it; the child
world-line diverges (child action `drop` vs the parent's continuation; child
manifest `cf10659782407fb1...` != parent `e5657a18d0970388...`); the parent's
on-disk evidence replays byte-identically AFTER all fork activity (unmutated); a
fork genesis claiming a different parent state is refused (anti-transplant).
Script: appendix D.

**E — deterministic contention: PASS.**
Both agents co-located with the one exclusive token: settlement is deterministic
(round-order head `alice` wins; `bob` has NO take candidate at the settled state
— state-dependent legality); identical winner + identical settled state id across
independent registries (`e6ca6c9b91830622...`); replaying the stale
pre-contention take at the settled state is refused, and a stale cursor against
the settled state is refused. Script: appendix E.

## 4. Non-identity metadata (excluded from identity, recorded honestly)

The CLI seed scopes ONLY the recorded RandomStream identity and the run id (the
base scheduler consumes no randomness; scripted agents draw nothing): seeds 42 and
43 produce the SAME world/genesis/closure/manifest/terminal identities and
different `random_stream_id`/run ids (committed regression). Latency and
wall-clock exist nowhere in the evidence.

## 5. Remaining blockers

None for R3. Deferred by design (gated): portal/container mutable state (open/
close), audibility, reveal conditions, LabelRecord (T0-B), live-LLM spatial runs
(owner), society surfaces (SC-LC + G-SOCIETY-PROFILE), training (M14/SC-8).

## 6. Is this R3?

**Yes.** A two-agent, scripted, deterministic, perception-split spatial experiment
runs behind one stable command; its evidence is content-addressed, byte-replayable
from nothing, tamper-detecting, fork-capable without mutating the parent, and its
actor views provably carry no private state. S2B+S2C+S2D are integrated on plain
GOs; runs A-E pass. Per the master directive, the program now STOPS for the owner.

## 7. Decision brief — three options (owner chooses; none auto-starts)

**Option 1 — More spatial experiments on this substrate.**
Cheapest next step. Add scenarios (multi-room topologies, container open/close as
the first mutable object state, contention-heavy scripts), grow the run pack, emit
the integrated training-readiness records from spatial runs (the record layer is
already integrated and architecture-neutral). Best if the goal is a deeper
evidence base + more behavioral surface BEFORE any agency.
Cost: low. Risk: low. Gates: none.

**Option 2 — Minimal Society Seed.**
Use the integrated Persistent Society MVP Profile to stand up the smallest
persistent-identity slice on this substrate (persistent gladiator bodies +
world-lines across runs; NO institutions, comms, or relationships yet). Best if
the goal is the Living Coliseum bridge phase.
Cost: medium. Risk: medium. Gates: **owner SC-LC required before any live
persistent/embodied society run** (G-SOCIETY-PROFILE already satisfied).

**Option 3 — Butterfly MVP on the runnable substrate.**
The bounded 10-run behavioral-calibration track (interventions / matched
trajectories / hidden evals) now has a deterministic spatial world to run against
scripted personas first. Best if the goal is behavioral measurement machinery
before society scale.
Cost: medium. Risk: low-medium. Gates: live-LLM runs need the owner (scripted
calibration runs do not).

---

## Appendix C — run-pack C script (verbatim)

```python
"""Run pack C — perception non-interference twin (master directive step 5C).

For EVERY scheduler position of the canonical run and EVERY observer: construct
the twin state differing ONLY in hidden content (the private gem relocated out of
its container into the observers' complement — i.e. removed from every visible
scope), admit + register it, render both, and require IDENTICAL actor observation
ids with DIFFERENT privileged ids. Pure verification over the integrated APIs;
registers only twin variant states in a fresh in-memory registry."""
import sys
sys.path.insert(0, "/home/dummy/agent-coliseum")

from coliseum.textlab.spatial.registry import SpatialSpecRegistry
from coliseum.textlab.spatial.scenario import build_scenario
from coliseum.textlab.spatial.scheduler import schedule, _rehydrate_world_state
from coliseum.textlab.spatial.perception import render_observation_pair
from coliseum.textlab.spatial.state import WorldState, admit_world_state

reg = SpatialSpecRegistry()
sc = build_scenario("spatial_two_agent_private_object_v1", reg, 42)
chain, transitions, manifest = schedule(sc["run"], sc["genesis"], list(sc["script"]),
                                        sc["closure"], reg)
gem = sc["ids"]["gem"]
checked = 0
for cursor in chain:
    state = _rehydrate_world_state(reg.get(cursor.content["current_world_state_hash"]))
    # the twin: identical placements/lifecycle EXCEPT the hidden gem is absent.
    placements = [dict(p, location=dict(p["location"]))
                  for p in state.content["placements"] if p["entity_id"] != gem]
    lifecycle = [dict(e) for e in state.content["entity_lifecycle"]
                 if e["entity_id"] != gem]
    twin = WorldState(state.world_line_id, state.logical_step, placements, lifecycle)
    admit_world_state(twin, reg); reg.register(twin)
    for key in sc["observers"]:
        a1, p1 = render_observation_pair(state, sc["ids"][key], sc["closure"], reg)
        a2, p2 = render_observation_pair(twin, sc["ids"][key], sc["closure"], reg)
        assert a1.id == a2.id, f"ACTOR DIVERGED at pos {cursor.content['scheduler_position']} {key}"
        assert p1.id != p2.id, f"PRIVILEGED FAILED TO DIVERGE at pos {cursor.content['scheduler_position']} {key}"
        checked += 1
print(f"RUN C PASS: {checked} (position, observer) pairs — actor ids IDENTICAL, "
      f"privileged ids DIFFERENT when only hidden content changes")
print(f"  chain positions: {len(chain)}; observers: {sc['observers']}; "
      f"manifest {manifest.id[:16]}")

```

## Appendix D — run-pack D script (verbatim)

```python
"""Run pack D — counterfactual fork (master directive step 5D).

Fork the canonical run at its RECORDED fork point (position 1: alice holds the
token). The child world-line diverges (alice DROPS the token instead of moving);
verify: (1) the child's fork genesis passes the S2B anti-transplant + reachability
witness validation, and FAILS without the witness; (2) the child chain shares the
parent prefix semantics but diverges from the fork state; (3) the parent's
finalized manifest + evidence are UNMUTATED (byte-identical replay after the
fork); (4) no transplant: a fork genesis claiming a different parent state is
refused."""
import sys
sys.path.insert(0, "/home/dummy/agent-coliseum")

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.spatial.fork import ForkDecision, materialize_fork
from coliseum.textlab.spatial.registry import SpatialSpecRegistry
from coliseum.textlab.spatial.run import replay_spatial_run
from coliseum.textlab.spatial.scenario import build_scenario
from coliseum.textlab.spatial.scheduler import (SchedulerRun, WorldLineGenesis,
                                                _closure_hash,
                                                _rehydrate_world_state,
                                                action_script_commitment,
                                                candidate_effects,
                                                materialize_fork_closure, schedule,
                                                validate_world_line_genesis)
from coliseum.textlab.spatial.world_line import WorldLine

reg = SpatialSpecRegistry()
sc = build_scenario("spatial_two_agent_private_object_v1", reg, 42)
chain, transitions, manifest = schedule(sc["run"], sc["genesis"], list(sc["script"]),
                                        sc["closure"], reg)
fork_pos = sc["fork_position"]
fork_cursor = chain[fork_pos]
assert fork_cursor.content["current_world_state_hash"] == sc["fork_state_hash"]
fs = _rehydrate_world_state(reg.get(sc["fork_state_hash"]))

# 1) authorized fork: ForkDecision -> forked WorldLine -> materialize_fork ->
#    fork closure -> fork WorldLineGenesis with the reachability witness.
D = ForkDecision(sc["world_line"].id, fs.id, fs.logical_step,
                 "counterfactual-drop-instead-of-move", {})
reg.register(D)
child_line = WorldLine.forked(sc["world_line"].id, D.id,
                              "counterfactual-drop-instead-of-move", {})
reg.register(child_line)
child_state, finit = materialize_fork(fs, child_line, D, reg)
reg.register(child_state); reg.register(finit)
child_closure = materialize_fork_closure(sc["closure"], child_line.id, reg)
fg = WorldLineGenesis(child_line.id, child_state.id, _closure_hash(child_closure),
                      "fork", parent_world_line_id=sc["world_line"].id,
                      parent_state_hash=fs.id, fork_logical_step=fs.logical_step,
                      source_fork_decision_hash=D.id)
reg.register(fg)
witness = {"scheduler_state_id": fork_cursor.id, "scheduler_manifest_id": manifest.id,
           "action_script": sc["script"]}
validate_world_line_genesis(fg, reg, witness=witness)
print("D1 PASS: fork genesis authenticated with the reachability witness "
      f"(parent position {fork_pos})")
try:
    validate_world_line_genesis(fg, reg)
    raise SystemExit("D1 FAIL: witness-less fork genesis was accepted")
except ContentRecordError:
    print("D1 PASS: the same fork genesis WITHOUT the witness is refused")

# 2) divergent child run: remap ids via the child closure and DROP instead of move.
child_ids = {reg.get(i).content["deterministic_logical_instance_key"]: i
             for i in child_closure["bodies"] + child_closure["objects"]}
alice_c, token_c = child_ids["alice"], child_ids["token"]
cands = candidate_effects(alice_c, child_state, child_closure, reg)
drop = next(e for e in cands["drop"] if e["object_instance_id"] == token_c)
child_script = [drop]
child_run = SchedulerRun(child_line.id, fg.id, action_script_commitment(child_script),
                         explicit_stop_position=1)
reg.register(child_run)
c_chain, c_tr, c_manifest = schedule(child_run, child_state, child_script,
                                     child_closure, reg, witness=witness)
parent_action = transitions[fork_pos].content["effect"]["action"] \
    if fork_pos < len(transitions) else None
child_action = c_tr[0].content["effect"]["action"]
assert c_manifest.id != manifest.id
print(f"D2 PASS: child diverges at fork position {fork_pos} — child action "
      f"'{child_action}' vs parent continuation; child manifest "
      f"{c_manifest.id[:16]} != parent {manifest.id[:16]}")

# 3) parent evidence unmutated: the canonical run's on-disk evidence still replays
#    byte-identically after all fork activity.
ok, detail = replay_spatial_run(
    "spatial_two_agent_private_object_v1--seed42--e5657a18d0970388",
    out_root="logs/spatial-runs")
assert ok, detail
print(f"D3 PASS: parent evidence unmutated — {detail}")

# 4) no transplant: a fork genesis claiming a DIFFERENT parent state (the genesis
#    state instead of the fork state) is refused even with a witness.
D2 = ForkDecision(sc["world_line"].id, sc["genesis"].id, 0, "transplant-probe", {})
reg.register(D2)
line2 = WorldLine.forked(sc["world_line"].id, D2.id, "transplant-probe", {})
reg.register(line2)
gs2, finit2 = materialize_fork(_rehydrate_world_state(reg.get(sc["genesis"].id)),
                               line2, D2, reg)
reg.register(gs2); reg.register(finit2)
cc2 = materialize_fork_closure(sc["closure"], line2.id, reg)
bad_fg = WorldLineGenesis(line2.id, gs2.id, _closure_hash(cc2), "fork",
                          parent_world_line_id=sc["world_line"].id,
                          parent_state_hash=sc["genesis"].id, fork_logical_step=0,
                          source_fork_decision_hash=D2.id)
reg.register(bad_fg)
try:
    validate_world_line_genesis(bad_fg, reg,
                                witness={"scheduler_state_id": fork_cursor.id,
                                         "scheduler_manifest_id": manifest.id,
                                         "action_script": sc["script"]})
    raise SystemExit("D4 FAIL: mismatched witness/parent-state accepted")
except ContentRecordError:
    print("D4 PASS: a witness not matching the claimed parent state is refused "
          "(anti-transplant)")
print("RUN D PASS: authorized fork + divergence + parent immutability + "
      "anti-transplant all verified")

```

## Appendix E — run-pack E script (verbatim)

```python
"""Run pack E — deterministic contention (master directive step 5E).

Both agents co-located with ONE exclusive-possession token, both intending to
take it. Verify: (1) settlement is DETERMINISTIC — the round order is the sorted
body-id order, the first-activated body's take succeeds, and the token is no
longer a take candidate for the second body (state-dependent legality); (2) the
same contention replays to the identical winner + identical state across
independent registries; (3) STALE-ACTION REFUSAL — committing the loser's
pre-contention take (built against the PRE state) is refused at consume, and a
stale cursor is refused at next_step."""
import sys
sys.path.insert(0, "/home/dummy/agent-coliseum")

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.spatial.registry import SpatialSpecRegistry
from coliseum.textlab.spatial.scenario import build_scenario
from coliseum.textlab.spatial.scheduler import (SchedulerRun, _mk_transition,
                                                _rehydrate_world_state,
                                                action_script_commitment,
                                                candidate_effects, consume,
                                                initial_scheduler_state, next_step)
from coliseum.textlab.spatial.state import WorldState, admit_world_state


def contention(reg):
    """Build the scenario, move both bodies into room A at step 0 (an admitted
    variant genesis is NOT a scheduler genesis — so drive the contention from the
    canonical genesis: bob's first intent already brings him to room A at the
    fork-adjacent state). Here we reproduce contention exactly at the canonical
    position where both bodies stand in room A with the token present: position 0
    round order decides who may take first."""
    sc = build_scenario("spatial_two_agent_private_object_v1", reg, 42)
    ids = sc["ids"]
    # a contention world state: both bodies in room A, token on the floor.
    g = sc["genesis"].content
    placements = [dict(p, location=dict(p["location"])) for p in g["placements"]]
    next(p for p in placements if p["entity_id"] == ids["bob"])["location"] = \
        {"tag": "in_room", "room_instance_id": ids["room_A"]}
    state = WorldState(sc["world_line"].id, 0, placements,
                       [dict(e) for e in g["entity_lifecycle"]])
    admit_world_state(state, reg); reg.register(state)
    order = sorted([ids["alice"], ids["bob"]])
    first, second = order[0], order[1]
    # both have the take candidate at the contention state.
    for b in order:
        assert any(e["object_instance_id"] == ids["token"]
                   for e in candidate_effects(b, state, sc["closure"], reg)["take"])
    # the first body takes; the settlement state removes the candidate for the second.
    take = next(e for e in candidate_effects(first, state, sc["closure"], reg)["take"]
                if e["object_instance_id"] == ids["token"])
    t = _mk_transition(state, take, reg, actor=first)
    from coliseum.textlab.spatial.transition import apply_transition
    post = apply_transition(state, t, reg); reg.register(post)
    assert not any(e["object_instance_id"] == ids["token"]
                   for e in candidate_effects(second, post, sc["closure"], reg)
                   .get("take", ()))
    return sc, ids, state, post, first, second, take, t


regA, regB = SpatialSpecRegistry(), SpatialSpecRegistry()
scA, idsA, preA, postA, firstA, secondA, takeA, tA = contention(regA)
scB, idsB, preB, postB, firstB, secondB, takeB, tB = contention(regB)
assert (firstA, postA.id) == (firstB, postB.id)
key_of = {v: k for k, v in idsA.items() if k in ("alice", "bob")}
print(f"E1 PASS: deterministic settlement — winner is the round-order head "
      f"'{key_of[firstA]}'; loser '{key_of[secondA]}' has NO take candidate at the "
      f"settled state (state-dependent legality)")
print(f"E2 PASS: identical winner + identical settled state id across independent "
      f"registries ({postA.id[:16]})")

# E3: stale-action refusal at the SCHEDULER boundary. Drive the canonical run to
# position 1 (alice's take consumed); then try to consume the SAME take again —
# the cursor now points at the post state, and the stale transition (built
# against the PRE state) must be refused.
reg = SpatialSpecRegistry()
sc = build_scenario("spatial_two_agent_private_object_v1", reg, 42)
cursor = initial_scheduler_state(sc["run"], sc["genesis"], reg)
step = next_step(cursor, sc["genesis"], sc["closure"], reg)
take0 = sc["script"][0]
t0 = _mk_transition(sc["genesis"], take0, reg, actor=step.content["agent_body_id"])
cursor1, state1 = consume(cursor, sc["genesis"], t0, sc["closure"], reg)
try:
    consume(cursor1, state1, t0, sc["closure"], reg)   # the STALE take, again
    raise SystemExit("E3 FAIL: a stale pre-contention action was accepted")
except ContentRecordError as e:
    print(f"E3 PASS: replaying the stale pre-contention take at the settled state "
          f"is refused ({str(e)[:60]}...)")
try:
    next_step(cursor, state1, sc["closure"], reg)       # stale CURSOR vs new state
    raise SystemExit("E3 FAIL: a stale cursor was accepted")
except ContentRecordError:
    print("E3 PASS: a stale cursor against the settled state is refused")
print("RUN E PASS: deterministic contention settlement + stale-action refusal verified")

```

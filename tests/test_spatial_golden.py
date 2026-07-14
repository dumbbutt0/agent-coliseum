"""The spatial GOLDEN SUITE (owner directive 2026-07-14) — permanent regression
tests stressing every major subsystem of the integrated spatial substrate:
navigation/exploration, object interaction (all v0 action kinds), information
asymmetry (fog + private inventories + privileged observers), coordination +
conflict over a scarce resource, and a LONG trajectory. Every scenario's complete
run identity is PINNED (manifest + terminal state + chain length): ANY drift in
world identity, dispatch, legality, perception, evidence bytes, or replay changes
a pinned literal and fails here. Tests drive the SAME CLI entry point as a user."""
from __future__ import annotations

import json
import os

import pytest

from coliseum.textlab.cli import main as cli_main
from coliseum.textlab.spatial.run import inspect_spatial_run

#: the pinned golden identities (seed 42). Content-addressed with no wall-clock or
#: host entropy — stable on every machine. Recompute ONLY on an audited,
#: version-bumped semantic change; never to silence a failure.
GOLDEN = {
    "spatial_nav_exploration_v1": {
        "manifest": "9fde484b3be1b5c919dbf2fc6517a922dd8418eb48ffa3ba4979987d1a2ade43",
        "terminal": "7678121592e87863ca7ccd94dbc28a58d0a93abf4006b38f651b4c060ff4a3d0",
        "chain_length": 12,
    },
    "spatial_object_pipeline_v1": {
        "manifest": "eec737100e9d649446604b903509ce73ac65a805e253af833d227f18a08c8ce8",
        "terminal": "9ba62d54d877d050630d121a70fae3c64335c97132bf19ed5c5b27320c590abe",
        "chain_length": 15,
    },
    "spatial_info_asymmetry_v1": {
        "manifest": "e97c21c8193aca8165f457752ee9d2ce4848158d758512a9b2c6e1fc4795abe5",
        "terminal": "34d284d139559e645f3f5f834902bcf84481fbce87058ee8c44496d6caf7c92b",
        "chain_length": 12,
    },
    "spatial_scarce_resource_v1": {
        "manifest": "620daff1081b1a6060573be9dcd8e9adc31f983d5f7f0dd684db88685254294f",
        "terminal": "8a66174a26190d28ae450caacef8e63230522c08691018d718d5b43d3b4bd0e6",
        "chain_length": 9,
    },
    "spatial_long_march_v1": {
        "manifest": "ae28d82f74d09bfad0364829fe5276f03973e107886d2febfd2d05bc721ac885",
        "terminal": "4e46ee2de468fb538b04f207eb95662c8973f609843fd2dc137386ad595ba41a",
        "chain_length": 240,
    },
}


@pytest.fixture(scope="module")
def golden_runs(tmp_path_factory):
    """Execute every golden scenario ONCE through the CLI (module-scoped: the
    long-march run is shared by its assertions), then replay each via the CLI."""
    root = str(tmp_path_factory.mktemp("golden"))
    runs = {}
    for name in GOLDEN:
        cli_main(["spatial-run", "--scenario", name, "--seed", "42",
                  "--spatial-root", root])
        run_id = next(d for d in os.listdir(root) if d.startswith(name))
        cli_main(["spatial-replay", run_id, "--spatial-root", root])
        summary = json.load(open(os.path.join(root, run_id, "run.json")))
        transitions = [json.loads(l) for l in
                       open(os.path.join(root, run_id, "transitions.jsonl"))]
        runs[name] = {"root": root, "run_id": run_id, "summary": summary,
                      "transitions": transitions}
    return runs


def test_golden_identities_pinned(golden_runs):
    """The heart of the suite: every scenario's manifest, terminal state, and
    chain length are exactly the pinned literals — and each replayed
    byte-identically through the CLI gate inside the fixture."""
    for name, pins in GOLDEN.items():
        s = golden_runs[name]["summary"]
        assert s["manifest_id"] == pins["manifest"], name
        assert s["terminal_world_state_id"] == pins["terminal"], name
        assert s["chain_length"] == pins["chain_length"], name


# ---------------------------------------------------------- navigation/exploration
def test_nav_exploration_route_and_revisit(golden_runs):
    """The agent traverses A->B->C->D and returns D->C->B->A: multi-portal
    routing, REVISITED rooms, and a terminal placement back in the home room."""
    r = golden_runs["spatial_nav_exploration_v1"]
    ids = r["summary"]["instance_ids"]
    moves = [t["content"]["effect"] for t in r["transitions"]
             if t["content"]["effect"]["action"] == "move"]
    route = [m["to_room_instance_id"] for m in moves]
    assert route == [ids["room_B"], ids["room_C"], ids["room_D"],
                     ids["room_C"], ids["room_B"], ids["room_A"]]
    assert len(set(route)) == 4 and route.count(ids["room_C"]) == 2  # revisits
    # terminal: home again (evidence-level, from the final actor observation).
    last = inspect_spatial_run(r["run_id"], out_root=r["root"], view="actor",
                               agent="alice")[-1]
    assert last["content"]["visible_room_identity"] == ids["room_A"]


# ------------------------------------------------------------- object interaction
def test_object_pipeline_covers_every_action_kind(golden_runs):
    """take, give (a direct trade), put_inside, take_out, drop, move all occur;
    exclusive possession holds at every step; the final state is exactly the
    choreographed handback (alice holds token1; token2 on the floor)."""
    r = golden_runs["spatial_object_pipeline_v1"]
    ids = r["summary"]["instance_ids"]
    kinds = [t["content"]["effect"]["action"] for t in r["transitions"]]
    assert {"take", "give", "put_inside", "take_out", "drop",
            "move"} <= set(kinds)
    give = next(t["content"]["effect"] for t in r["transitions"]
                if t["content"]["effect"]["action"] == "give")
    assert give["object_instance_id"] == ids["token1"]
    assert give["recipient_agent_body_id"] == ids["bob"]
    # terminal placements from the final privileged observation (world truth).
    last = inspect_spatial_run(r["run_id"], out_root=r["root"],
                               view="privileged", agent="alice")[-1]
    placements = {p["entity_id"]: p["location"] for p in
                  last["content"]["observable_state_projection"]
                  ["authoritative_placements"]}
    assert placements[ids["token1"]] == {"tag": "held_by",
                                         "agent_body_id": ids["alice"]}
    assert placements[ids["token2"]]["tag"] == "in_room"


# ----------------------------------------------------------- information asymmetry
def test_info_asymmetry_fog_private_inventory_privileged(golden_runs):
    """(1) the private gem appears in NO actor view at ANY position for EITHER
    agent — including positions where bob is co-located with alice and sees her
    AND the carried box; (2) fog-of-war: at position 0 bob (two rooms away) sees
    neither alice nor the box; (3) the privileged observer carries the gem at
    every position."""
    r = golden_runs["spatial_info_asymmetry_v1"]
    ids = r["summary"]["instance_ids"]
    actor = inspect_spatial_run(r["run_id"], out_root=r["root"], view="actor")
    for row in actor:
        assert ids["gem"] not in row["content"]["visible_entity_identities"]
    bob0 = next(row for row in actor
                if row["observer_key"] == "bob" and row["scheduler_position"] == 0)
    assert ids["alice"] not in bob0["content"]["visible_entity_identities"]
    assert ids["box"] not in bob0["content"]["visible_entity_identities"]
    colocated = [row for row in actor if row["observer_key"] == "bob"
                 and ids["alice"] in row["content"]["visible_entity_identities"]]
    assert colocated                                  # the tour passes bob
    assert any(ids["box"] in row["content"]["visible_entity_identities"]
               for row in colocated)                  # bob sees the carried box...
    priv = inspect_spatial_run(r["run_id"], out_root=r["root"], view="privileged",
                               agent="bob")
    assert all(ids["gem"] in row["content"]["visible_entity_identities"]
               for row in priv)                       # ...but only privilege sees in


# ------------------------------------------------------- coordination + conflict
def test_scarce_resource_deterministic_settlement_and_relay(golden_runs):
    """One exclusive token, two claimants: alice's take settles first (pinned
    order), bob yields, and possession then transfers by a drop/take floor
    relay — the final holder is bob."""
    r = golden_runs["spatial_scarce_resource_v1"]
    ids = r["summary"]["instance_ids"]
    takes = [t["content"] for t in r["transitions"]
             if t["content"]["effect"]["action"] == "take"]
    assert [t["actor_body_id"] for t in takes] == [ids["alice"], ids["bob"]]
    last = inspect_spatial_run(r["run_id"], out_root=r["root"],
                               view="privileged", agent="bob")[-1]
    placements = {p["entity_id"]: p["location"] for p in
                  last["content"]["observable_state_projection"]
                  ["authoritative_placements"]}
    assert placements[ids["token"]] == {"tag": "held_by",
                                        "agent_body_id": ids["bob"]}


# ------------------------------------------------------------------ long trajectory
def test_long_march_chain_integrity(golden_runs):
    """A 240-state chain: strictly monotonic positions with intact previous-hash
    links across the whole file, 120 committed moves alternating rooms, and the
    byte-identical CLI replay already enforced by the fixture."""
    r = golden_runs["spatial_long_march_v1"]
    rows = [json.loads(l) for l in
            open(os.path.join(r["root"], r["run_id"], "chain.jsonl"))]
    assert len(rows) == 240
    for i, row in enumerate(rows):
        assert row["content"]["scheduler_position"] == i
        if i:
            assert row["content"]["previous_scheduler_state_hash"] == \
                rows[i - 1]["scheduler_state_id"]
    moves = [t["content"]["effect"]["to_room_instance_id"]
             for t in r["transitions"]
             if t["content"]["effect"]["action"] == "move"]
    ids = r["summary"]["instance_ids"]
    assert len(moves) == 120
    assert moves[::2] == [ids["room_B"]] * 60 and moves[1::2] == [ids["room_A"]] * 60

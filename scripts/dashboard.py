#!/usr/bin/env python3
"""Program Dashboard generator (First Gladiator M5).

    PYTHONPATH=. python3 scripts/dashboard.py            # write docs/first-gladiator/DASHBOARD.md
    PYTHONPATH=. python3 scripts/dashboard.py --stdout   # print only

DERIVED, never hand-edited. Each section is computed from its authoritative
source: milestones from the roadmap YAML; council health from the live
chain projection; scenario/experiment/claim coverage from the three
registries; test count from pytest collection (passed in, not run here, so
the dashboard itself stays a pure function). Idempotent: same inputs ->
byte-identical output (no wall-clock in the body).
"""
from __future__ import annotations

import argparse
import os
import sys

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from coliseum.textlab.registry import (load_claims_registry,  # noqa: E402
                                       load_experiments_registry)


def _council_health():
    """(chain_len, verify_ok, active, blocked, integrated_recent) or a
    reason string if the live council is unreachable (dashboard still
    renders)."""
    try:
        from tools.council import events, get_config, state_machine
        root = get_config(role="claude").council_root
        chain = events.read_chain(root)
        proj = state_machine.project(chain)
        active, blocked = [], []
        for rid, r in sorted(proj.items()):
            st = r["state"]
            if st == "blocked":
                blocked.append(rid)
            elif st in ("requested", "claimed", "go",
                        "policy_validation", "awaiting_human"):
                active.append(f"{rid}:{st}")
        # milestone completion is authoritative from the CHAIN (integrated
        # first-gladiator-mN requests), not the owner-edited roadmap task
        # statuses — those drive launcher selection, not progress tracking
        integrated = sorted({
            e["payload"].get("task_id", "") for e in chain
            if e["event_type"] == "CHANGE_INTEGRATED"
            and str(e["payload"].get("task_id", "")).startswith(
                "first-gladiator-m")})
        return {"chain_len": len(chain),
                "verify": events.verify_chain(root).healthy,
                "active": active, "blocked": blocked,
                "integrated_milestones": integrated}
    except Exception as exc:  # pragma: no cover - env-dependent
        return {"error": str(exc)[:120]}


def render(test_count: int | None = None) -> str:
    roadmap = yaml.safe_load(open(os.path.join(
        REPO, "configs", "autonomy-roadmap.yaml")))
    tasks = roadmap["tasks"]

    scen = yaml.safe_load(open(os.path.join(
        REPO, "configs", "registry", "scenarios.yaml")))["scenarios"]
    families = sorted({s["family"] for s in scen})
    SPEC_FAMILIES = ["authority", "moral_conflict", "uncertainty",
                     "time_pressure", "self_preservation", "social_pressure",
                     "deception", "memory_persistence"]
    exp = load_experiments_registry(os.path.join(
        REPO, "configs", "registry", "experiments.yaml"))["experiments"]
    claims = load_claims_registry(os.path.join(
        REPO, "configs", "registry", "claims.yaml"))["claims"]
    by_state = {}
    for c in claims:
        by_state.setdefault(c["state"], 0)
        by_state[c["state"]] += 1

    ch = _council_health()
    task_ids = [t["task_id"] for t in tasks]
    integrated = ch.get("integrated_milestones", []) if "error" not in ch \
        else []
    # milestone number of each chain task_id (first-gladiator-mN -> "mN")
    integrated_nums = {tid.rsplit("-", 1)[-1] for tid in integrated}
    # a roadmap task (mN-title) is done iff its mN appears in the chain;
    # current = the first roadmap task not yet integrated
    done_n = sum(1 for tid in task_ids
                 if tid.split("-", 1)[0] in integrated_nums)
    remaining = [tid for tid in task_ids
                 if tid.split("-", 1)[0] not in integrated_nums]
    current = remaining[0] if remaining else None
    nxt = remaining[1] if len(remaining) > 1 else None
    L = ["# First Gladiator — Program Dashboard", "",
         "> DERIVED artifact (scripts/dashboard.py). Never hand-edited; "
         "regenerated at every milestone close. Idempotent. Milestone "
         "completion is read from the CHAIN (integrated requests), not the "
         "roadmap task statuses.", "",
         "## Milestones", "",
         f"- roadmap milestone: **{roadmap['milestone']}**  "
         f"({done_n}/{len(tasks)} integrated on the chain)",
         f"- integrated: {', '.join(integrated) or 'none'}",
         f"- current: **{current or '—'}**  next: {nxt or '—'}", "",
         "## Council health", ""]
    if "error" in ch:
        L.append(f"- (live council unreachable: {ch['error']})")
    else:
        L += [f"- chain length: {ch['chain_len']}  verify: "
              f"{'OK' if ch['verify'] else 'UNHEALTHY'}",
              f"- active requests: {', '.join(ch['active']) or 'none'}",
              f"- BLOCKED requests: {', '.join(ch['blocked']) or 'none'}"]
    L += ["", "## Coverage", "",
          f"- tests: {test_count if test_count is not None else '(run pytest --collect-only)'}",
          f"- scenario families: {len(families)}/8 present "
          f"({', '.join(families)})",
          f"- families still to build: "
          f"{', '.join(f for f in SPEC_FAMILIES if f not in families) or 'none'}",
          f"- registered scenarios: {len(scen)}  experiments: {len(exp)}",
          "", "## Claim ladder census", ""]
    for state in ("accepted", "generalized", "replicated", "observation",
                  "speculation", "refuted", "demoted"):
        if state in by_state:
            L.append(f"- {state}: {by_state[state]}")
    accepted = [c["claim_id"] for c in claims if c["state"] == "accepted"]
    L += ["", "## Paper candidates (ACCEPTED only)", "",
          ("- none yet (no claim has passed an independent finding audit)"
           if not accepted else
           "\n".join(f"- `{c}`" for c in sorted(accepted)))]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dashboard")
    ap.add_argument("--stdout", action="store_true")
    ap.add_argument("--test-count", type=int, default=None)
    args = ap.parse_args(argv)
    text = render(args.test_count)
    if args.stdout:
        sys.stdout.write(text)
        return 0
    out = os.path.join(REPO, "docs", "first-gladiator", "DASHBOARD.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

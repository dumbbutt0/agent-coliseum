"""Preflight guard: every autonomy transition checks the SAME conditions.

Authority order (owner directive 2026-07-11):
  1. STATUS/STOP emergency controls
  2. the immutable autonomy policy (hash-pinned in the chain)
  3. the hash-pinned structured roadmap
  4. council events, requests, verdicts
  5. the exact committed repository state
  6. wiki prose (context only — never executable authority)

Any failed condition means: append AUTONOMY_PAUSED with the exact reasons
and stop. The guard itself never fixes anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tools.autonomy import default_roadmap_path, roadmap as roadmap_mod
from tools.council.schemas import CouncilError
from tools.council import Config, events, git_state, policy, state_machine, \
    storage


@dataclass
class GuardReport:
    ok: bool
    failures: list = field(default_factory=list)
    policy: dict | None = None
    policy_hash: str | None = None
    roadmap: dict | None = None
    roadmap_hash: str | None = None
    requests: dict = field(default_factory=dict)


def preflight(cfg: Config, repo: str | None = None,
              expect_head: str | None = None,
              roadmap_path: str | None = None,
              pinned_roadmap_hash: str | None = None) -> GuardReport:
    """Evaluate every precondition; fail-closed, collect ALL failures."""
    root = cfg.council_root
    failures: list = []

    # 1. emergency controls
    stop = storage.emergency_stop_reason(root)
    if stop:
        failures.append(f"emergency_stop: {stop}")

    # 4 (early — everything else reads the chain): chain verifies
    report = events.verify_chain(root)
    requests: dict = {}
    if not report.ok:
        failures.append(f"event_chain: {report.error}")
    else:
        chain = events.read_chain(root, verify=False)
        requests = state_machine.project(chain)
        flags = state_machine.global_flags(requests)
        if flags["autonomy_paused"]:
            failures.append("flags: autonomy_paused is set — only the owner "
                            "resumes (cancel or fresh request)")
        if flags["milestone_reached"]:
            failures.append("flags: society milestone reached — autonomous "
                            "continuation is forbidden")
        # H1: identity replay — the verifier must EQUAL the chain-replayed
        # state; a substituted, missing, or diverged verifier (or any
        # inconsistent burn/rotation history) is a fail-closed condition
        try:
            from tools.council import identity
            pin, expected = identity.replay_identity(chain)
            verifier = identity.read_verifier(root)
            if pin is not None:
                if verifier is None:
                    failures.append(
                        "identity: chain pins a token tip but the verifier "
                        "file is missing — identity-restore-from-pin")
                else:
                    steps = expected["counter"] - verifier["counter"]
                    if steps < 0 or identity.chain_value(
                            bytes.fromhex(verifier["tip_hex"]),
                            steps).hex() != expected["tip_hex"]:
                        failures.append(
                            "identity: verifier does not descend from the "
                            "chain-replayed state — possible substitution "
                            "or revived tokens")
        except CouncilError as exc:
            failures.append(f"identity: {exc}")

    # 2. immutable policy, unchanged since pinned
    pol = pol_hash = None
    try:
        pol, pol_hash = policy.load_policy(root)
        if report.ok:
            pinned = policy.pinned_policy_hash(
                events.read_chain(root, verify=False))
            if pinned is not None and pinned != pol_hash:
                failures.append(
                    "policy: autonomy_policy.json changed since it was "
                    f"pinned in the chain (pinned {pinned[:12]}, "
                    f"now {pol_hash[:12]})")
    except Exception as exc:
        failures.append(f"policy: {exc}")

    # 3. hash-pinned roadmap
    rm = rm_hash = None
    if pol is not None:
        path = roadmap_path or default_roadmap_path(root)
        try:
            rm, rm_hash = roadmap_mod.load_roadmap(path, pol)
            if pinned_roadmap_hash is not None and \
                    rm_hash != pinned_roadmap_hash:
                failures.append(
                    f"roadmap: file hash {rm_hash[:12]} differs from the "
                    f"pinned hash {pinned_roadmap_hash[:12]} — the roadmap "
                    "changed after it was pinned")
        except roadmap_mod.RoadmapError as exc:
            failures.append(f"roadmap: {exc}")

    # 5. exact committed repository state
    if repo is not None:
        try:
            if not git_state.is_clean(repo, cfg.repo_roots):
                failures.append("git: working tree is dirty")
            head = git_state.head_commit(repo, cfg.repo_roots)
            if expect_head is not None and head != expect_head:
                failures.append(
                    f"git: HEAD {head[:12]} is not the bound commit "
                    f"{expect_head[:12]}")
        except Exception as exc:
            failures.append(f"git: {exc}")

    return GuardReport(ok=not failures, failures=failures, policy=pol,
                       policy_hash=pol_hash, roadmap=rm, roadmap_hash=rm_hash,
                       requests=requests)


def pause(cfg: Config, request_id: str, repo: str, commit: str,
          failures: list) -> dict:
    """Record AUTONOMY_PAUSED with every reason (works under emergency stop)."""
    reason = "; ".join(str(f) for f in failures) or "unspecified"
    return events.pause_autonomy(cfg.council_root, cfg, "claude", request_id,
                                 repo, commit, reason)

"""Deterministic resume: reconstruct the current eligible work from the
council event chain + the hash-pinned roadmap. READ-ONLY — prints what a
fresh Claude session (or a session recovering from a crash) must do next;
it never records events, never launches anything.

Owner correction 2 (2026-07-11): this command is the cross-session
continuity mechanism for v1. An automatic process that launches new
writable Claude sessions is deliberately NOT built here — that is a
separately audited future capability (docs/AUTONOMY.md).
"""
from __future__ import annotations

import json

from tools.autonomy import default_roadmap_path, roadmap as roadmap_mod
from tools.council import Config, events, policy, state_machine, storage

# state -> (who acts, what they run/do). Deterministic: same chain + same
# roadmap => same answer.
NEXT_ACTION = {
    "building": ("claude", "finish the bounded build; run tests; commit "
                           "by-name; record BUILD_READY"),
    "fixing": ("claude", "finish the scoped fixes; run tests; commit "
                         "by-name; record BUILD_READY"),
    "ready": ("claude", "publish the audit request: python3 -m "
                        "tools.council.cli --role claude publish-request "
                        "--file <request.json> [--reaudit]"),
    "requested": ("codex", "wait: codex_watch claims the ready request"),
    "claimed": ("codex", "wait: Codex audits the exact commit and submits "
                         "a structured verdict"),
    "blocked": ("claude", "record FIX_STARTED and fix ONLY the scoped "
                          "findings (bounded: max 5 audit cycles)"),
    "go": ("claude", "run policy validation: python3 -m tools.autonomy.cli "
                     "policy-continue --request-id <id> (or claude_watch "
                     "--once if the verdict is unconsumed)"),
    "policy_validation": ("claude", "policy validation was interrupted — "
                                    "python3 -m tools.autonomy.cli "
                                    "policy-continue --request-id <id>"),
    "auto_approved": ("claude", "run the approved task: python3 -m "
                                "tools.autonomy.cli run-task --request-id "
                                "<id> --config <frozen experiment config>"),
    "awaiting_human": ("human", "owner approval required: python3 -m "
                                "tools.council.cli --role human approve "
                                "<id> --commit <bound commit>"),
    "awaiting_result_handoff_owner": (
        "human", "owner result-handoff approval required: python3 -m "
        "tools.council.cli --role human approve-result-handoff <id> "
        "--commit <bound commit>"),
    "result_handoff_approved": (
        "claude", "build the provider-free closure bundle: python3 -m "
        "tools.council.cli --role claude result-handoff --request-id <id>"),
    "approved": ("claude", "run the human-approved task: python3 -m "
                           "tools.autonomy.cli run-task --request-id <id> "
                           "--config <frozen experiment config>"),
    "experiment_running": ("claude", "CRASHED MID-EXPERIMENT: inspect the "
                                     "evidence; record EXPERIMENT_COMPLETE "
                                     "only if it is complete and valid, "
                                     "else AUTONOMY_PAUSED"),
    "experiment_complete": ("claude", "record RESULT_VALIDATION_REQUIRED "
                                      "with the validation battery results"),
    "result_validation": ("claude", "request the result audit (runner tail) "
                                    "— validations must all pass first"),
    "result_audit": ("codex", "wait: Codex audits the evidence and submits "
                              "--result-audit"),
    "result_approved": ("claude", "task complete: update the roadmap status "
                                  "(audited commit), mirror to the wiki, "
                                  "then select the next eligible task"),
    "result_blocked": ("claude", "record FIX_STARTED and address the scoped "
                                 "result findings"),
    "next_milestone_ready": ("claude", "select the next eligible roadmap "
                                       "task and record BUILD_STARTED under "
                                       "a fresh request id"),
    "autonomy_paused": ("human", "autonomy is paused — only the owner "
                                 "resumes (cancel or fresh request)"),
    "milestone_reached": ("human", "society milestone reached — owner "
                                   "briefing; nothing runs"),
    "canceled": ("nobody", "terminal"),
}


def compute_resume(cfg: Config, roadmap_path: str | None = None) -> dict:
    root = cfg.council_root
    out: dict = {"council_root": root, "ok": True, "problems": []}

    stop = storage.emergency_stop_reason(root)
    if stop:
        out["ok"] = False
        out["problems"].append(f"emergency_stop: {stop}")

    report = events.verify_chain(root)
    out["chain"] = {"ok": report.ok, "length": report.length,
                    "head": report.head_hash, "error": report.error}
    if not report.ok:
        out["ok"] = False
        out["problems"].append(f"event_chain: {report.error}")
        return out

    chain = events.read_chain(root, verify=False)
    requests = state_machine.project(chain)
    out["flags"] = state_machine.global_flags(requests)

    out["requests"] = {}
    approved_m8_results = {}
    for event in chain:
        if event["event_type"] != "RESULT_HANDOFF_READY":
            continue
        request = event.get("payload", {}).get("request", {})
        artifacts = request.get("result_artifacts", {})
        source_id = artifacts.get("source_request_id")
        if artifacts.get("profile_id") == \
                "m8_budget_exhausted_incomplete_handoff.v1" and \
                requests.get(event["request_id"], {}).get("state") == \
                state_machine.RESULT_APPROVED:
            approved_event = next((
                item for item in reversed(chain)
                if item["request_id"] == event["request_id"] and
                item["event_type"] == "RESULT_APPROVED"), None)
            if source_id and approved_event:
                approved_m8_results[source_id] = (
                    event["request_id"], approved_event["event_id"])
    for rid, req in sorted(requests.items()):
        state = req["state"]
        actor, action = NEXT_ACTION.get(state, ("?", "unknown state"))
        if state == state_machine.AUTONOMY_PAUSED and \
                rid in approved_m8_results:
            result_id, result_event = approved_m8_results[rid]
            actor = "human"
            action = (
                "close the paused M8 lifecycle: python3 -m "
                "tools.council.cli --role human close-paused-result "
                f"{rid} --result-request {result_id} "
                f"--result-event {result_event}")
        out["requests"][rid] = {
            "state": state,
            "target_commit": req["target_commit"],
            "audit_cycles": req["audit_cycles"],
            "next_actor": actor,
            "next_action": action.replace("<id>", rid).replace(
                "<bound commit>", str(req["target_commit"])),
        }

    pol = None
    try:
        pol, pol_hash = policy.load_policy(root)
        out["policy_hash"] = pol_hash
        # amendment-aware (M7a): an owner-authorized POLICY_AMENDED is not drift
        eff_hash, _ = policy.effective_policy_pin(chain)
        if eff_hash is not None and eff_hash != pol_hash:
            out["ok"] = False
            out["problems"].append("policy hash drifted from the pinned one")
    except Exception as exc:
        out["ok"] = False
        out["problems"].append(f"policy: {exc}")

    if pol is not None:
        path = roadmap_path or default_roadmap_path(root)
        try:
            doc, rm_hash = roadmap_mod.load_roadmap(path, pol)
            active = roadmap_mod.active_task(doc)
            out["roadmap"] = {
                "path": path, "hash": rm_hash,
                "active_task": active["task_id"] if active else None,
                "eligible_tasks": [t["task_id"] for t in
                                   roadmap_mod.eligible_tasks(doc)],
                "human_gated_ready": [
                    t["task_id"] for t in doc["tasks"]
                    if t["status"] == "ready" and t["requires_human"]],
            }
        except roadmap_mod.RoadmapError as exc:
            out["ok"] = False
            out["problems"].append(f"roadmap: {exc}")

    # the single most-actionable pointer: the newest non-terminal request
    live = [(rid, r) for rid, r in requests.items()
            if r["state"] not in ("canceled", "milestone_reached",
                                  "result_approved", "next_milestone_ready")]
    if live:
        rid, req = max(live, key=lambda kv: kv[1]["last_event_id"] or "")
        out["current"] = {"request_id": rid, **out["requests"][rid]}
    elif out.get("roadmap", {}).get("eligible_tasks"):
        nxt = out["roadmap"]["eligible_tasks"][0]
        out["current"] = {"request_id": None, "next_actor": "claude",
                          "next_action": f"start roadmap task {nxt!r}: "
                                         "record BUILD_STARTED under a fresh "
                                         "request id"}
    elif out.get("roadmap", {}).get("human_gated_ready"):
        gated = out["roadmap"]["human_gated_ready"]
        out["current"] = {"request_id": None, "next_actor": "human",
                          "next_action": "only human-gated task(s) are "
                                         f"ready: {gated} — awaiting the "
                                         "owner; nothing runs autonomously"}
    else:
        out["current"] = {"request_id": None, "next_actor": "human",
                          "next_action": "no live request and no eligible "
                                         "task — owner decides"}
    return out


def render(out: dict) -> str:
    lines = [f"resume: chain {out['chain']['length']} events "
             f"({'OK' if out['chain']['ok'] else 'BROKEN'}); "
             f"flags {out.get('flags')}"]
    for p in out.get("problems", []):
        lines.append(f"  !! {p}")
    for rid, req in out.get("requests", {}).items():
        lines.append(f"  {rid}: {req['state']} -> [{req['next_actor']}] "
                     f"{req['next_action']}")
    rm = out.get("roadmap")
    if rm:
        lines.append(f"  roadmap {rm['hash'][:12]}: active="
                     f"{rm['active_task']} eligible={rm['eligible_tasks']}")
    cur = out.get("current", {})
    lines.append(f"NEXT: [{cur.get('next_actor')}] {cur.get('next_action')}")
    return "\n".join(lines)


def main_json(cfg: Config, roadmap_path: str | None = None) -> str:
    return json.dumps(compute_resume(cfg, roadmap_path), indent=2,
                      sort_keys=True)

"""Journaled post-integration result-audit handoff.

This is deliberately not an experiment runner.  It authenticates one closed,
already-captured compatibility pack, publishes an event-first request, and
opens the ordinary independent result-audit path.  It never contacts a model.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
import sys

from tools.autonomy.runner import validation_report_hash
from tools.council import events, git_state, locking, state_machine, storage
from tools.council.schemas import (CouncilError, SchemaViolation,
                                   compute_request_payload_hash, domain_hash,
                                   EVIDENCE_INVENTORY_DOMAIN, payload_hash,
                                   validate_request)
from tools.council.strictjson import loads_strict

SENDER = "claude"
CONFIG_DOMAIN = "council:result-handoff-config:v1"
TRANSACTION_DOMAIN = "council:result-handoff-transaction:v1"
PROFILE_ID = "society_live_persona_result_handoff.v1"
RUN_ID = "society_seed_v1--seed42--b63d84694594b499"
RUN_DIR = f"logs/live-persona-runs/{RUN_ID}"
MANIFEST_FILE = f"{RUN_DIR}.manifest.json"
CONCLUSION_SCOPE = (
    "incomplete authenticated capture-replay only; no behavioral claim")

ARTIFACT_ROLES = {
    "activations.jsonl": "primary_capture",
    "chain.jsonl": "primary_capture",
    "closure.json": "primary_capture",
    "live_report.json": "derived_result",
    "observations.jsonl": "primary_capture",
    "persona.jsonl": "primary_capture",
    "persona_latency.jsonl": "primary_capture",
    "run.json": "primary_capture",
    "transitions.jsonl": "primary_capture",
}
PRIMARY_CAPTURE_HASHES = {
    "activations.jsonl": "db7db81d0fdd07165a29e01e5b1ac75db55a8127e11100dfb8890b58f4fef159",
    "chain.jsonl": "262a9590ebfa4046cab9fe78b469e689812e84cca285a3f7a3a0b0501f3bc5ad",
    "closure.json": "d7f37589d8856d595c6fdba7d699f89d82ef35cdebe6ae768d13951471638324",
    "observations.jsonl": "178b4a2d8424a5717046b8bc3ddb0b0c61c90f550d75b320f6d1579c78d22319",
    "persona.jsonl": "103c04eb9ea4c367a37c2eb787a30ce99c64c7d03f4830e499ee0c15c2f0f04f",
    "persona_latency.jsonl": "b1ac8cbe8db219bec672658b1152917487d4d512c4eb942d160902780ac3b96c",
    "run.json": "6550784d49d05fdda1bd5a801079b00c0f2d01296799b65f2533b082551afb82",
    "transitions.jsonl": "c4e625f30d04ef94aa0700c937bc12d2c3252ebb4a2eef59bdf0a0adaab6418b",
}
INVENTORY = dict(PRIMARY_CAPTURE_HASHES,
                 **{"live_report.json":
                    "d5645dad79fca107197f880cada717555d17d136367e5c7d6711db1ecf00f974"})
INVENTORY_HASH = "3906af0c0fd56562df284690c9634c796ee048271c3ca06098814c95efca4af7"

REGIME = {
    "backend_version": "0.22.0",
    "decoding": {"num_predict": 256, "seed": 42, "temperature": 0.0},
    "model_digest": "103482475c9b4d4032999dd5d7383478cad8b966ae6ae984d525daf7352c2219",
    "model_id": "huihui_ai/qwen2.5-abliterate:7b-instruct",
    "parser_version": "society_numeric_menu.v1",
    "persona_actor_version": "0.1",
    "prompt_version": "society_persona_prompt.v1",
    "seed_supported": True,
}
RESULT_CONFIG = {
    "artifact_roles": ARTIFACT_ROLES,
    "authorization_profile_id": PROFILE_ID,
    "conclusion_scope": CONCLUSION_SCOPE,
    "evidence_inventory_hash": INVENTORY_HASH,
    "limits": {"adaptive_intervention": False, "live_agents": 1,
               "live_runs": 1, "max_requested_decisions": 8,
               "retries": 0, "scripted_controls": 2, "training": False},
    "live_source_evidence_id": "7037594c102e5c19ace51a248fd25e315d3685029b4e0b385f1e41a09968c0d5",
    "manifest_file": MANIFEST_FILE,
    "outcome": {
        "behavioral_departure_claimable": False,
        "behavioral_departure_count": 1, "complete": False,
        "decisions_parsed_ok": 4, "decisions_requested": 4,
        "effective_n": 4, "effective_n_floor": 6,
        "first_divergence_tick": 1, "observability_restricted_count": 2,
        "status": "incomplete",
        "terminated": {"code": "control_desync", "control": "bo",
                       "scheduler_position": 15,
                       "terminal_coding": "control_desync_termination",
                       "tick": 3}},
    "primary_capture_hashes": PRIMARY_CAPTURE_HASHES,
    "regime": REGIME,
    "regime_id": "a442b818f2f164d446519edca7fc995abde04a3bdffd20e1ca78c16f5b1c3cb0",
    "report_id": "b91a808ef43fc896edb3c2644b1bcfb8baa17931734ea8a288b2f4c7aece2e59",
    "run_dir": RUN_DIR, "run_id": RUN_ID,
    "schema_version": "result-handoff-config.v1",
}
AUTHORIZATION_PROFILE = {
    "design": {
        "go_event_hash": "0ba0421b524fc870d487ca987da80a9195b114b9dba8fa280721dc2f826dae4d",
        "go_event_id": "001314-f9213572",
        "integrated_commit": "e792a1981bdfd76b404a85deefcf933646901a78",
        "integration_event_hash": "cbfbc43d15d5b62476cdba755f7357a509edac34e4379db2bdc3d92680706e3c",
        "integration_event_id": "001315-1359cd7b",
        "publication_event_hash": "34ca25084012ede04af66587537d62e6406a9b9de5fc8c230a14f06854763954",
        "publication_event_id": "001312-87b4f8ee",
        "request_id": "first-gladiator-society-live-persona-design-008",
        "request_payload_hash": "77c96d1d7e5592c2073ecd19536486b99d48f651951f3219e1ae257d880f4857"},
    "implementation": {
        "go_event_hash": "2df86105543b42b5a7c0ddef1c13c1800f76247536de82eb20b5a73b57bd812a",
        "go_event_id": "001340-da14306d",
        "integrated_commit": "06d3afab15ecbff14723338fd5418751f77a288b",
        "integration_event_hash": "70d3f8dadbc4d2d74fcf0bcddbc48418c684972a2bb0308d1755a8acd471d11c",
        "integration_event_id": "001341-a1718410",
        "publication_event_hash": "4044f8e15fcef4b6cbaab8db2429f64e61c0cac9d0421fb93acafc1dc49801e8",
        "publication_event_id": "001338-9140ea10",
        "request_id": "first-gladiator-society-live-persona-impl-005",
        "request_payload_hash": "b152824b0e0d14346eaa2ef6f3ecb18c7b5d07ab91f2b94e869ff9343f1d7c55"},
    "profile_id": PROFILE_ID,
}

_HANDOFF_FIELDS = {
    "task_kind", "run_id", "run_dir", "manifest_file",
    "evidence_inventory_hash", "validations", "validation_report_hash",
    "result_config", "experiment_config_hash", "artifact_roles",
    "primary_capture_hashes", "authorization_profile",
    "live_source_evidence_id", "conclusion_scope",
}
_CORRECTION_FIELDS = {
    "prior_result_request_id", "prior_ready_event_id",
    "prior_result_audit_event_id", "prior_blocked_event_id",
    "prior_fix_started_event_id", "prior_experiment_config_hash",
    "prior_evidence_inventory_hash",
}

# These outcome fields express the authorized conclusion ceiling, rather than
# merely a recomputable report summary.  A derived-only correction may repair
# counts or report structure, but it cannot turn this incomplete pilot into a
# complete or behaviorally claimable result.
CORRECTION_OUTCOME_CEILING = {
    "behavioral_departure_claimable": False,
    "complete": False,
    "status": "incomplete",
}


def _safe_relpath(value: object, field: str) -> None:
    if not isinstance(value, str) or not value or value.startswith(("/", "\\")) \
            or "\\" in value or "\x00" in value or ".." in value.split("/"):
        raise SchemaViolation(f"{field} must be a safe repository-relative path")


def validate_handoff_request(request: dict) -> None:
    """Closed semantic validation used by the ordinary request schema."""
    profile = request.get("authorization_profile", {}).get("profile_id")
    if profile == "m8_budget_exhausted_incomplete_handoff.v1":
        from tools.council.m8_incomplete_handoff import \
            validate_m8_handoff_request
        validate_m8_handoff_request(request)
        return
    if profile != PROFILE_ID:
        raise SchemaViolation(
            f"unknown result-handoff profile {profile!r}")
    from tools.council.schemas import REQUEST_REQUIRED_FIELDS
    correction = "prior_result_request_id" in request
    expected = set(REQUEST_REQUIRED_FIELDS) | _HANDOFF_FIELDS
    if correction:
        expected |= _CORRECTION_FIELDS
    if set(request) != expected:
        raise SchemaViolation(
            "result_handoff request has missing or unknown keys: "
            f"missing={sorted(expected-set(request))}, "
            f"unknown={sorted(set(request)-expected)}")
    config = request["result_config"]
    if not correction and config != RESULT_CONFIG:
        raise SchemaViolation("initial result_config differs from the pin")
    if correction:
        if not isinstance(config, dict) or set(config) != set(RESULT_CONFIG):
            raise SchemaViolation("correction result_config shape differs")
        derived = {"evidence_inventory_hash", "outcome", "report_id"}
        for key in set(RESULT_CONFIG) - derived:
            if config[key] != RESULT_CONFIG[key]:
                raise SchemaViolation(
                    f"correction changed frozen result_config field {key}")
        if not isinstance(config["outcome"], dict) or not config["outcome"]:
            raise SchemaViolation("correction outcome must be a non-empty object")
        for field, ceiling in CORRECTION_OUTCOME_CEILING.items():
            value = config["outcome"].get(field)
            if type(value) is not type(ceiling) or value != ceiling:
                raise SchemaViolation(
                    f"correction outcome exceeds frozen conclusion ceiling: {field}")
        for field in ("evidence_inventory_hash", "report_id"):
            if not isinstance(config[field], str) or not re.fullmatch(
                    r"[0-9a-f]{64}", config[field]):
                raise SchemaViolation(f"correction {field} must be sha256 hex")
    if request["authorization_profile"] != AUTHORIZATION_PROFILE:
        raise SchemaViolation("authorization_profile differs from the pin")
    if request["artifact_roles"] != ARTIFACT_ROLES or \
            request["primary_capture_hashes"] != PRIMARY_CAPTURE_HASHES:
        raise SchemaViolation("artifact role or primary-capture map drift")
    exact = {"run_id": RUN_ID, "run_dir": RUN_DIR,
             "manifest_file": MANIFEST_FILE,
             "live_source_evidence_id":
             RESULT_CONFIG["live_source_evidence_id"],
             "conclusion_scope": CONCLUSION_SCOPE}
    for key, value in exact.items():
        if request[key] != value:
            raise SchemaViolation(f"{key} differs from the pinned profile")
    if request["evidence_inventory_hash"] != config["evidence_inventory_hash"]:
        raise SchemaViolation("request/config evidence inventory mismatch")
    _safe_relpath(request["run_dir"], "run_dir")
    _safe_relpath(request["manifest_file"], "manifest_file")
    if request["experiment_config_hash"] != domain_hash(
            CONFIG_DOMAIN, request["result_config"]):
        raise SchemaViolation("experiment_config_hash does not bind result_config")
    if not isinstance(request["validations"], list) or \
            request["validation_report_hash"] != validation_report_hash(
                request["validations"]):
        raise SchemaViolation("validation_report_hash does not bind validations")
    if correction:
        if request["prior_result_request_id"] == request["request_id"]:
            raise SchemaViolation("correction must use a new request_id")
        for field in ("prior_ready_event_id", "prior_result_audit_event_id",
                      "prior_blocked_event_id", "prior_fix_started_event_id"):
            if not isinstance(request[field], str) or not re.fullmatch(
                    r"\d{6}-[0-9a-f]{8}", request[field]):
                raise SchemaViolation(f"{field} must be a council event id")
        for field in ("prior_experiment_config_hash",
                      "prior_evidence_inventory_hash"):
            if not isinstance(request[field], str) or not re.fullmatch(
                    r"[0-9a-f]{64}", request[field]):
                raise SchemaViolation(f"{field} must be sha256 hex")


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_pack(repo: str, request: dict) -> None:
    config = request["result_config"]
    run_dir = os.path.join(repo, request["run_dir"])
    if not os.path.isdir(run_dir) or os.path.islink(run_dir):
        raise SchemaViolation("run_dir must be a real directory, not a symlink")
    names = sorted(os.listdir(run_dir))
    if names != sorted(ARTIFACT_ROLES):
        raise SchemaViolation("run directory inventory differs from the pin")
    actual = {}
    for name in names:
        path = os.path.join(run_dir, name)
        mode = os.lstat(path).st_mode
        if not stat.S_ISREG(mode) or stat.S_ISLNK(mode):
            raise SchemaViolation(f"manifested member {name!r} is not regular")
        actual[name] = _sha256_file(path)
    primary = {name: digest for name, digest in actual.items()
               if ARTIFACT_ROLES[name] == "primary_capture"}
    if primary != PRIMARY_CAPTURE_HASHES:
        raise SchemaViolation("a frozen primary capture differs from the pin")
    manifest_path = os.path.join(repo, request["manifest_file"])
    with open(manifest_path, "rb") as fh:
        manifest = loads_strict(fh.read(), max_bytes=262_144)
    inventory_content = {
        "schema_version": "evidence-manifest.v1", "run_id": RUN_ID,
        "run_dir": RUN_DIR, "file_count": len(actual),
        "files": dict(sorted(actual.items()))}
    computed_inventory = domain_hash(EVIDENCE_INVENTORY_DOMAIN,
                                     inventory_content)
    if manifest.get("files") != actual or manifest.get("file_count") != 9 \
            or set(manifest) != {"schema_version", "run_id", "run_dir",
                                "file_count", "files", "inventory_hash",
                                "generated_utc"} \
            or manifest.get("schema_version") != "evidence-manifest.v1" \
            or manifest.get("inventory_hash") != computed_inventory \
            or manifest.get("run_id") != RUN_ID \
            or manifest.get("run_dir") != RUN_DIR:
        raise SchemaViolation("sibling manifest does not authenticate the pack")
    if request["evidence_inventory_hash"] != computed_inventory or \
            config["evidence_inventory_hash"] != computed_inventory:
        raise SchemaViolation("request/config inventory does not bind manifest")
    with open(os.path.join(run_dir, "live_report.json"), "rb") as fh:
        report = loads_strict(fh.read(), max_bytes=2_000_000)
    content = report.get("content", {})
    outcome = config["outcome"]
    outcome_fields = {key: content.get(key) for key in outcome}
    if set(report) != {"id", "content"} or \
            report.get("id") != payload_hash(content) or \
            report.get("id") != config["report_id"] or \
            content.get("regime_id") != RESULT_CONFIG["regime_id"] or \
            content.get("regime") != REGIME or outcome_fields != outcome:
        raise SchemaViolation("live report identity or regime differs from pin")
    bound_names = ("run.json", "chain.jsonl", "transitions.jsonl",
                   "observations.jsonl", "activations.jsonl", "closure.json",
                   "persona.jsonl")
    binding_preimage = {
        "_domain": "trs.source_evidence.live.v1", "run_id": RUN_ID,
        "pack_kind": "incomplete",
        "evidence_file_hashes": {name: actual[name] for name in bound_names}}
    if payload_hash(binding_preimage) != RESULT_CONFIG["live_source_evidence_id"]:
        raise SchemaViolation("live source binding recomputation differs")
    replay = subprocess.run(
        [sys.executable, "-m", "coliseum.textlab.society.live", "replay",
         run_dir], cwd=repo, capture_output=True, text=True, timeout=120,
        env={"PATH": os.environ.get("PATH", ""),
             "PYTHONPATH": repo, "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        replay_result = loads_strict(replay.stdout.encode(), max_bytes=2_000_000)
    except (ValueError, SchemaViolation) as exc:
        raise SchemaViolation(f"zero-model replay output invalid: {exc}") from exc
    if replay.returncode != 0 or replay_result.get("replay_ok") is not True:
        raise SchemaViolation("zero-model capture replay failed")


def _validate_authority(root: str, cfg, chain: list, request: dict) -> None:
    by_id = {e["event_id"]: e for e in chain}
    for label in ("design", "implementation"):
        pin = AUTHORIZATION_PROFILE[label]
        for key in ("publication", "go", "integration"):
            event = by_id.get(pin[f"{key}_event_id"])
            if event is None or event["event_hash"] != pin[f"{key}_event_hash"]:
                raise SchemaViolation(f"{label} {key} authority anchor mismatch")
        pub, go, integ = (by_id[pin[f"{key}_event_id"]]
                          for key in ("publication", "go", "integration"))
        if pub["request_id"] != pin["request_id"] or \
                pub["payload"].get("request_payload_hash") != \
                pin["request_payload_hash"] or go["event_type"] != "AUDIT_GO" \
                or go["payload"].get("conditions") != [] \
                or integ["event_type"] != "CHANGE_INTEGRATED" \
                or integ["target_commit"] != pin["integrated_commit"] \
                or integ["request_id"] != pin["request_id"] \
                or integ["payload"].get("audit_go_event") != \
                pin["go_event_id"]:
            raise SchemaViolation(f"{label} authority predicate failed")
        from tools.council import publish
        source_request, failures, source_repo, source_commit = \
            publish.verified_request(root, cfg, pin["request_id"])
        if failures or source_request.get("task_kind") != "source" or \
                source_request.get("request_payload_hash") != \
                pin["request_payload_hash"] or source_repo != request["repository"] \
                or source_commit != pin["integrated_commit"]:
            raise SchemaViolation(
                f"{label} source request is not valid plain-GO authority")
    correction = "prior_result_request_id" in request
    ready_requests = {
        e["request_id"]: e["payload"].get("request", {}) for e in chain
        if e["event_type"] in ("RESULT_HANDOFF_READY", "RESULT_FIX_READY")}
    lineage = set()
    cursor = request.get("prior_result_request_id")
    while cursor:
        if cursor in lineage:
            raise SchemaViolation("correction lineage contains a cycle")
        lineage.add(cursor)
        cursor = ready_requests.get(cursor, {}).get("prior_result_request_id")
    for event in chain:
        if event["event_type"] not in ("RESULT_HANDOFF_READY", "RESULT_FIX_READY"):
            continue
        prior = event["payload"].get("request", {})
        if any(prior.get(k) == request.get(k) for k in
               ("run_id", "run_dir", "live_source_evidence_id",
                "evidence_inventory_hash")):
            if event["request_id"] != request["request_id"] and \
                    event["request_id"] not in lineage:
                raise SchemaViolation("result profile/evidence already used")
    if correction:
        prior_id = request["prior_result_request_id"]
        expected = {
            "prior_ready_event_id":
                ("RESULT_HANDOFF_READY", "RESULT_FIX_READY"),
            "prior_result_audit_event_id": ("RESULT_AUDIT_REQUESTED",),
            "prior_blocked_event_id": ("RESULT_BLOCKED",),
            "prior_fix_started_event_id": ("FIX_STARTED",),
        }
        for field, types in expected.items():
            event = by_id.get(request[field])
            if event is None or event["request_id"] != prior_id or \
                    event["event_type"] not in types:
                raise SchemaViolation(
                    f"correction lineage anchor {field} is invalid")
        prior_request = by_id[request["prior_ready_event_id"]]["payload"][
            "request"]
        if request["prior_experiment_config_hash"] != \
                prior_request.get("experiment_config_hash") or \
                request["prior_evidence_inventory_hash"] != \
                prior_request.get("evidence_inventory_hash"):
            raise SchemaViolation(
                "correction predecessor hashes do not match its ready event")


def _publish_handoff_locked(root: str, cfg, request: dict,
                            correction: bool = False,
                            _m8_budget=None,
                            _m8_exact_bundle_target: bool = False,
                            _m8_resume_verified_ready: bool = False) -> dict:
    """Preflight, then roll forward the three-step event-first journal."""
    request = dict(request)
    request["request_payload_hash"] = compute_request_payload_hash(request)
    validate_request(request, cfg.repo_roots)
    if correction != ("prior_result_request_id" in request):
        raise SchemaViolation("command mode does not match request lineage")
    repo, commit, rid = (request["repository"], request["target_commit"],
                         request["request_id"])
    exact_m8_target = False
    if _m8_exact_bundle_target:
        profile = request.get("authorization_profile", {}).get("profile_id")
        if profile != "m8_budget_exhausted_incomplete_handoff.v1":
            raise SchemaViolation(
                "exact bundle target exception is M8-profile-only")
        from tools.council.m8_incomplete_handoff import \
            target_has_only_exact_bundle
        exact_m8_target = target_has_only_exact_bundle(
            repo, cfg.repo_roots, request.get("derived_artifact_hashes"))
    if git_state.head_commit(repo, cfg.repo_roots) != commit or \
            not (git_state.is_clean(repo, cfg.repo_roots) or exact_m8_target):
        raise SchemaViolation("handoff target must be the clean repository HEAD")
    if not git_state.commit_exists(repo, commit, cfg.repo_roots):
        raise SchemaViolation("handoff target commit does not exist")
    chain = events.read_chain(root)
    m8_profile = request.get("authorization_profile", {}).get(
        "profile_id") == "m8_budget_exhausted_incomplete_handoff.v1"
    skip_m8_deep = False
    if _m8_resume_verified_ready:
        if not m8_profile or request.get("publication_recovery") is None:
            raise SchemaViolation(
                "verified-ready resume is M8-recovery-only")
        txn = domain_hash(
            TRANSACTION_DOMAIN,
            {"request_id": rid,
             "request_payload_hash": request["request_payload_hash"]})
        expected_ready = {
            "transaction_id": txn, "phase": "ready_published",
            "request": request,
            "request_payload_hash": request["request_payload_hash"]}
        prior_ready = [
            event for event in chain
            if event["request_id"] == rid and
            event["event_type"] == "RESULT_HANDOFF_READY"]
        projected = state_machine.project(chain).get(rid, {})
        if len(prior_ready) != 1 or \
                prior_ready[0]["payload"] != expected_ready or \
                projected.get("state") != state_machine.RESULT_VALIDATION:
            raise SchemaViolation(
                "M8 recovery has no exact verified ready journal to resume")
        skip_m8_deep = True
    if m8_profile:
        from tools.council.m8_incomplete_handoff import verify_bundle_request
        if not skip_m8_deep:
            verify_bundle_request(
                repo, request, chain=chain, deep=True, budget=_m8_budget)
    else:
        if _m8_budget is not None:
            raise SchemaViolation(
                "closure budget is valid only for the M8 result profile")
        if not git_state.is_ancestor(AUTHORIZATION_PROFILE["implementation"]
                                     ["integrated_commit"], commit, repo,
                                     cfg.repo_roots):
            raise SchemaViolation(
                "handoff target is not an implementation descendant")
        _validate_pack(repo, request)
        _validate_authority(root, cfg, chain, request)
    projection = state_machine.project(chain)
    if correction:
        prior = projection.get(request["prior_result_request_id"], {})
        prior_commit = prior.get("target_commit")
        if prior.get("state") != state_machine.FIXING or not prior_commit or \
                not git_state.is_ancestor(prior_commit, commit, repo,
                                          cfg.repo_roots):
            raise SchemaViolation(
                "correction predecessor must be fixing and its target an "
                "ancestor of the new commit")
    event_type = "RESULT_FIX_READY" if correction else "RESULT_HANDOFF_READY"
    txn = domain_hash(TRANSACTION_DOMAIN,
                      {"request_id": rid,
                       "request_payload_hash": request["request_payload_hash"]})
    ready = [e for e in chain if e["request_id"] == rid and
             e["event_type"] in ("RESULT_HANDOFF_READY", "RESULT_FIX_READY")]
    storage.ensure_layout(root)
    claimed = storage.safe_request_path(root, "claimed", rid)
    conflicting = [storage.safe_request_path(root, bucket, rid)
                   for bucket in ("ready", "complete")]
    if any(os.path.exists(path) for path in conflicting):
        raise SchemaViolation("conflicting request lifecycle file")
    if not ready and os.path.exists(claimed):
        raise SchemaViolation(
            "orphan claimed request has no owned ready journal event")
    if ready:
        ready_event = ready[-1]
        expected_payload = {"transaction_id": txn, "phase": "ready_published",
                            "request": request,
                            "request_payload_hash": request["request_payload_hash"]}
        if ready_event["event_type"] != event_type or \
                ready_event["payload"] != expected_payload:
            raise SchemaViolation("conflicting result-handoff journal entry")
    else:
        # State-machine preflight before the first durable write.
        probe = events.build_event(event_type, SENDER, rid, repo, commit,
            {"transaction_id": txn, "phase": "ready_published",
             "request": request,
             "request_payload_hash": request["request_payload_hash"]},
            len(chain) + 1, chain[-1]["event_hash"] if chain else "0" * 64)
        state_machine.check(probe, projection)
        ready_event = events.append_event(
            root, cfg, event_type, SENDER, rid, repo, commit, probe["payload"])

    if os.path.exists(claimed):
        with open(claimed, "rb") as fh:
            have = loads_strict(fh.read(), max_bytes=262_144)
        if have != request:
            raise SchemaViolation("claimed request differs from journal")
    else:
        storage.atomic_write_json(claimed, request)

    chain = events.read_chain(root)
    audits = [e for e in chain if e["request_id"] == rid and
              e["event_type"] == "RESULT_AUDIT_REQUESTED"]
    audit_payload = {
        "transaction_id": txn,
        "experiment_config_hash": request["experiment_config_hash"],
        "run_id": request["run_id"], "run_dir": request["run_dir"],
        "evidence_inventory_hash": request["evidence_inventory_hash"],
        "validation_report_hash": request["validation_report_hash"],
        "validations": request["validations"],
    }
    if request.get("result_artifacts") is not None:
        audit_payload["result_artifacts"] = request["result_artifacts"]
    if audits:
        if audits[-1]["payload"] != audit_payload:
            raise SchemaViolation("conflicting RESULT_AUDIT_REQUESTED journal")
        return audits[-1]
    return events.append_event(root, cfg, "RESULT_AUDIT_REQUESTED", SENDER,
                               rid, repo, commit, audit_payload)


def publish_handoff(root: str, cfg, request: dict,
                    correction: bool = False) -> dict:
    """Serialize preflight and all durable steps under one council lease."""
    rid = request.get("request_id", "result-handoff") \
        if isinstance(request, dict) else "result-handoff"
    txn_lock = locking.acquire(root, "_result_handoff", SENDER, rid,
                               kind="result_handoff_transaction")
    try:
        return _publish_handoff_locked(root, cfg, request, correction)
    finally:
        locking.release(txn_lock)

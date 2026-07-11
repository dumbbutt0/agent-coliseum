"""Bounded-autonomy executor layer ON TOP of the council protocol.

tools/council/ manages STATE (hash-chained events, policy gate, role
separation) and is a protected path — this package never modifies it, only
calls it. This package adds what the council deliberately leaves out: the
roadmap (which bounded task is eligible), the guard (preflight every
transition), the runner (execute ONE approved task under hard limits and
record its lifecycle events), and deterministic resume after a crash or a
fresh session.

NOT in this version (owner correction 2, 2026-07-11): durable cross-session
autonomy. Nothing here launches new writable Claude sessions; resume is a
READ-ONLY reconstruction command. An automatic session launcher is a
separately audited future capability (docs/AUTONOMY.md).

Stdlib-only by design, like tools/council/.
"""
from __future__ import annotations

import os

AUTONOMY_VERSION = "1"

# Task classes a roadmap task may declare (owner directive 2026-07-11).
ALLOWED_TASK_CLASSES = (
    "source_change_local",
    "tests_local",
    "scripted_experiment",
    "mock_experiment",
    "ollama_local",
    "deterministic_sweep_local",
    "stochastic_sweep_local",
    "offline_replay",
    "report_generation",
    "wiki_update",
    "clean_clone_reproduction",
    "local_git_commit",
    "codex_read_only_audit",
)

# Classes that must NEVER run autonomously. A roadmap naming one is invalid;
# work discovered to require one pauses autonomy with the exact reason.
FORBIDDEN_TASK_CLASSES = (
    "cloud_api",
    "third_party_web",
    "public_release",
    "git_push",
    "create_remote",
    "email_or_messaging",
    "real_credentials",
    "personal_data",
    "destructive_action",
    "evidence_deletion",
    "history_rewrite",
    "autonomy_policy_change",
    "stop_control_change",
    "weight_training",
    "lora_training",
    "fine_tuning",
    "external_prompt_injection_testing",
    "arbitrary_network_access",
    "purchases_or_spending",
    "automatic_limit_increase",
    "post_milestone_expansion",
)

TASK_STATUSES = ("pending", "ready", "active", "complete", "blocked", "paused")

ROADMAP_ENV = "AUTONOMY_ROADMAP"


def default_roadmap_path(council_root: str) -> str:
    """Claude-Wiki/coliseum/autonomy-roadmap.yaml, derived from the council
    root (…/Claude-Wiki/council). Env AUTONOMY_ROADMAP overrides (tests)."""
    env = os.environ.get(ROADMAP_ENV)
    if env:
        return env
    wiki_root = os.path.dirname(os.path.abspath(council_root))
    return os.path.join(wiki_root, "coliseum", "autonomy-roadmap.yaml")

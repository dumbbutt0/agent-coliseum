"""FSM transitions, commit binding, and the bounded-autonomy path."""
import pytest

from tests.council_util import append, make_cfg, make_repo, make_root
from tools.council import state_machine
from tools.council.schemas import TransitionError

RID = "state-req-001"


@pytest.fixture()
def env(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    return root, repo, head, make_cfg(repo, root)


def _drive(root, cfg, repo, head, *steps):
    last = None
    for event_type, sender in steps:
        last = append(root, cfg, event_type, sender, RID, repo, head)
    return last


HAPPY_HUMAN_PATH = (
    ("BUILD_STARTED", "claude"), ("FIX_STARTED", "claude"),
    ("BUILD_READY", "claude"), ("READY_FOR_REAUDIT", "claude"),
    ("AUDIT_CLAIMED", "codex"), ("AUDIT_GO", "codex"),
    ("HUMAN_APPROVAL_REQUIRED", "claude"),
    ("EXPERIMENT_APPROVED", "human"), ("EXPERIMENT_STARTED", "human"),
    ("EXPERIMENT_COMPLETE", "human"),
)

AUTONOMY_PATH = (
    ("BUILD_STARTED", "claude"), ("BUILD_READY", "claude"),
    ("AUDIT_REQUESTED", "claude"), ("AUDIT_CLAIMED", "codex"),
    ("AUDIT_GO", "codex"), ("POLICY_VALIDATION_REQUIRED", "claude"),
    ("AUTO_APPROVED", "claude"), ("EXPERIMENT_STARTED", "claude"),
    ("EXPERIMENT_COMPLETE", "claude"),
    ("RESULT_VALIDATION_REQUIRED", "claude"),
    ("RESULT_AUDIT_REQUESTED", "claude"), ("RESULT_APPROVED", "codex"),
    ("NEXT_MILESTONE_READY", "claude"),
)


def test_happy_path_through_human_gate(env):
    root, repo, head, cfg = env
    _drive(root, cfg, repo, head, *HAPPY_HUMAN_PATH)
    from tools.council import events
    requests = state_machine.project(events.read_chain(root))
    assert requests[RID]["state"] == state_machine.EXPERIMENT_COMPLETE
    assert requests[RID]["audit_cycles"] == 1


def test_full_autonomy_path(env):
    root, repo, head, cfg = env
    _drive(root, cfg, repo, head, *AUTONOMY_PATH)
    from tools.council import events
    requests = state_machine.project(events.read_chain(root))
    assert requests[RID]["state"] == state_machine.NEXT_MILESTONE_READY


SOURCE_TASK_PATH = (
    ("BUILD_STARTED", "claude"), ("BUILD_READY", "claude"),
    ("AUDIT_REQUESTED", "claude"), ("AUDIT_CLAIMED", "codex"),
    ("AUDIT_GO", "codex"), ("CHANGE_INTEGRATED", "claude"),
    ("NEXT_MILESTONE_READY", "claude"),
)


def test_source_task_path_go_to_integrated(env):
    """Source-change tasks terminate at GO -> CHANGE_INTEGRATED (no
    experiment lifecycle) and still chain into NEXT_MILESTONE_READY."""
    root, repo, head, cfg = env
    _drive(root, cfg, repo, head, *SOURCE_TASK_PATH)
    from tools.council import events
    requests = state_machine.project(events.read_chain(root))
    assert requests[RID]["state"] == state_machine.NEXT_MILESTONE_READY


def test_integration_only_from_go(env):
    """CHANGE_INTEGRATED is illegal before the GO verdict — unaudited
    candidates can never be recorded as integrated."""
    root, repo, head, cfg = env
    _drive(root, cfg, repo, head,
           ("BUILD_STARTED", "claude"), ("BUILD_READY", "claude"),
           ("AUDIT_REQUESTED", "claude"), ("AUDIT_CLAIMED", "codex"))
    with pytest.raises(TransitionError):
        append(root, cfg, "CHANGE_INTEGRATED", "claude", RID, repo, head)


def test_integration_commit_bound(env):
    """A GO for one commit never authorizes integrating another."""
    root, repo, head, cfg = env
    _drive(root, cfg, repo, head,
           ("BUILD_STARTED", "claude"), ("BUILD_READY", "claude"),
           ("AUDIT_REQUESTED", "claude"), ("AUDIT_CLAIMED", "codex"),
           ("AUDIT_GO", "codex"))
    with pytest.raises(TransitionError):
        append(root, cfg, "CHANGE_INTEGRATED", "claude", RID, repo, "f" * 40)


def test_blocked_to_fix_cycle(env):
    root, repo, head, cfg = env
    _drive(root, cfg, repo, head,
           ("BUILD_STARTED", "claude"), ("BUILD_READY", "claude"),
           ("READY_FOR_REAUDIT", "claude"), ("AUDIT_CLAIMED", "codex"),
           ("AUDIT_BLOCKED", "codex"), ("FIX_STARTED", "claude"),
           ("BUILD_READY", "claude"))
    from tools.council import events
    requests = state_machine.project(events.read_chain(root))
    assert requests[RID]["state"] == state_machine.READY


@pytest.mark.parametrize("event_type,sender", [
    ("AUDIT_GO", "codex"),               # verdict without a claim
    ("AUDIT_CLAIMED", "codex"),          # claim before request
    ("EXPERIMENT_APPROVED", "human"),    # approval before the gate
    ("EXPERIMENT_STARTED", "human"),     # start before approval
    ("AUTO_APPROVED", "claude"),         # auto-approve without validation
    ("RESULT_APPROVED", "codex"),        # result verdict without audit
    ("CHANGE_INTEGRATED", "claude"),     # integration without any audit
    ("BUILD_READY", "claude"),           # ready before started
])
def test_invalid_transitions_rejected_from_none(env, event_type, sender):
    root, repo, head, cfg = env
    with pytest.raises(TransitionError):
        append(root, cfg, event_type, sender, RID, repo, head)


def test_go_requires_claim_first(env):
    root, repo, head, cfg = env
    _drive(root, cfg, repo, head,
           ("BUILD_STARTED", "claude"), ("BUILD_READY", "claude"),
           ("READY_FOR_REAUDIT", "claude"))
    with pytest.raises(TransitionError):
        append(root, cfg, "AUDIT_GO", "codex", RID, repo, head)


def test_double_claim_rejected_by_state(env):
    root, repo, head, cfg = env
    _drive(root, cfg, repo, head,
           ("BUILD_STARTED", "claude"), ("BUILD_READY", "claude"),
           ("READY_FOR_REAUDIT", "claude"), ("AUDIT_CLAIMED", "codex"))
    with pytest.raises(TransitionError):
        append(root, cfg, "AUDIT_CLAIMED", "codex", RID, repo, head)


def test_commit_binding_blocks_other_commit(env, tmp_path):
    root, repo, head, cfg = env
    import subprocess, os
    _drive(root, cfg, repo, head,
           ("BUILD_STARTED", "claude"), ("BUILD_READY", "claude"),
           ("READY_FOR_REAUDIT", "claude"))
    # second commit in the same repo
    with open(os.path.join(repo, "g.txt"), "w") as fh:
        fh.write("more\n")
    subprocess.run(["git", "-C", repo, "add", "g.txt"], check=True)
    subprocess.run(["git", "-C", repo, "-c", "user.email=t@t",
                    "-c", "user.name=t", "commit", "-qm", "two"], check=True)
    other = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                           capture_output=True, text=True).stdout.strip()
    with pytest.raises(TransitionError):
        append(root, cfg, "AUDIT_CLAIMED", "codex", RID, repo, other)


def test_approval_does_not_transfer_between_commits(env):
    root, repo, head, cfg = env
    _drive(root, cfg, repo, head,
           ("BUILD_STARTED", "claude"), ("BUILD_READY", "claude"),
           ("READY_FOR_REAUDIT", "claude"), ("AUDIT_CLAIMED", "codex"),
           ("AUDIT_GO", "codex"), ("HUMAN_APPROVAL_REQUIRED", "claude"))
    fake = "f" * 40
    with pytest.raises(TransitionError):
        append(root, cfg, "EXPERIMENT_APPROVED", "human", RID, repo, fake)


def test_cancel_is_terminal(env):
    root, repo, head, cfg = env
    _drive(root, cfg, repo, head,
           ("BUILD_STARTED", "claude"), ("REQUEST_CANCELED", "human"))
    with pytest.raises(TransitionError):
        append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    with pytest.raises(TransitionError):
        append(root, cfg, "REQUEST_CANCELED", "human", RID, repo, head)


def test_autonomy_paused_freezes_request(env):
    root, repo, head, cfg = env
    _drive(root, cfg, repo, head,
           ("BUILD_STARTED", "claude"), ("AUTONOMY_PAUSED", "claude"))
    with pytest.raises(TransitionError):
        append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    # human cancel is the way out
    append(root, cfg, "REQUEST_CANCELED", "human", RID, repo, head)


def test_watcher_error_never_changes_state(env):
    root, repo, head, cfg = env
    _drive(root, cfg, repo, head,
           ("BUILD_STARTED", "claude"), ("WATCHER_ERROR", "claude"))
    from tools.council import events
    requests = state_machine.project(events.read_chain(root))
    assert requests[RID]["state"] == state_machine.BUILDING


def test_state_json_rebuild_matches_projection(env):
    root, repo, head, cfg = env
    _drive(root, cfg, repo, head,
           ("BUILD_STARTED", "claude"), ("BUILD_READY", "claude"))
    import json, os
    from tools.council import events, storage
    chain = events.read_chain(root)
    state_machine.rebuild(root, chain, chain[-1]["event_hash"])
    cached = json.load(open(storage.state_path(root), encoding="utf-8"))
    assert cached["chain_length"] == 4  # bootstrap pair + two appends
    assert cached["requests"][RID]["state"] == state_machine.READY
    assert cached["note"].startswith("derived cache")

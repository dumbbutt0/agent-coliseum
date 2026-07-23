"""Single source of truth for the pinned-digest cross-model sweep.

`scripts/sweep_models.py` (the human CLI) and the autonomy `ollama_local`
driver (`tools/autonomy/drivers.py`) both drive live experiments through
`run_sweep` — there is exactly ONE sweep implementation, so the manifest a
human sweep writes and the manifest the audited runner writes are produced by
identical code (audit blocker 4 lives here now).

Resume identity (Day-5): a manifest row is keyed by (FULL comparison_regime_id,
scenario_seed, sampler_seed) and carries its exact evidence dir; rows are
validated against their run.json on load. A repulled tag changes the digest ->
new regime -> reruns. `expected_digests` turns a mid-sweep repull into a hard
refusal instead of a silent new regime (the driver's integrity gate).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from types import MappingProxyType

from coliseum.textlab.agents import (HISTORY_TEMPLATE_HASH,
                                     HISTORY_TEMPLATE_VERSION, OllamaAgent)
from coliseum.textlab.runner import ARBITRATION_VERSION, run_scenario
from coliseum.textlab.scenario import load_scenario
from coliseum.textlab.schema import (SchemaError, build_behavioral_config,
                                     regime_hashes, validate_sampling)

_ATTEMPT_RE = re.compile(r"\.a(\d+)$")

# The complete current manifest-row schema — exactly what the sweep writer
# emits (audit blocker 4). The loader REQUIRES every field; the writer builds
# rows against the same constant so the two can never drift. Legacy rows go
# through scripts/migrate_manifest.py, never implicit acceptance.
REQUIRED_ROW_FIELDS = (
    "regime_id", "model", "scenario", "scenario_seed", "sampler_seed",
    "variant_id", "temperature", "sampling_mode", "digest", "scenario_hash",
    "arbitration", "run_id", "dir", "reportable", "stochastic_reportable",
    "interaction_mode", "path",
)

# a durable failure tombstone suppresses a planned unit, so it must prove which
# planned coordinate it belongs to (model/scenario/seeds), under which regime,
# and why it failed. Anything less cannot satisfy the plan (audit c-008).
REQUIRED_TOMBSTONE_FIELDS = (
    "regime_id", "model", "scenario", "scenario_seed", "sampler_seed",
    "failure_kind", "error", "recorded_utc",
)


@dataclass(frozen=True)
class ExecutionPolicy:
    """The frozen execution contract a policy-required live sweep MUST run under
    (b-003 / c-003 finding class). It bundles the analysis-critical execution
    bounds into ONE typed object so a production caller cannot silently omit the
    frozen retry / balance / order contract by forgetting a keyword argument.

    `run_sweep` requires an ExecutionPolicy for every POLICY_REQUIRED_EXPERIMENTS
    sweep and fails closed before any provider contact if it is absent or if its
    `retries_per_unit` is anything other than 0 — so the historical permissive
    default (a failed unit re-rolled on resume) can never reach the live M8 path.
    The ONLY supported producer for a frozen experiment is
    `from_verified_bundle`, which sources every value from an audited
    `registry.VerifiedBundle` (profile-checked), never from loose kwargs."""
    retries_per_unit: int
    max_surviving_delta: int
    execution_order: str = "interleaved"
    record_execution_index: bool = True

    @classmethod
    def from_verified_bundle(cls, bundle, *, execution_order: str,
                             record_execution_index: bool = True
                             ) -> "ExecutionPolicy":
        """Build the policy from an audited VerifiedBundle. `retries_per_unit`
        and `max_surviving_delta` come from the profile-checked frozen design;
        the caller supplies only the (config-declared) execution order. A
        duck-typed stand-in is refused (a-006 B-1): only a genuine profile-checked
        VerifiedBundle can source the frozen contract."""
        from coliseum.textlab.registry import VerifiedBundle
        if not isinstance(bundle, VerifiedBundle):
            raise SweepAborted(
                f"ExecutionPolicy.from_verified_bundle requires a genuine "
                f"registry.VerifiedBundle, got {type(bundle).__name__} — a "
                "duck-typed or forged bundle can never source the frozen "
                "execution contract")
        rpu = bundle.retries_per_unit
        if rpu is None or isinstance(rpu, bool) or rpu != 0:
            raise SweepAborted(
                f"{getattr(bundle, 'experiment_id', '?')}: frozen design "
                f"retries_per_unit={rpu!r} is not the required 0 — a "
                "policy-required live sweep must persist typed tombstones and "
                "never re-roll a failed unit")
        msd = bundle.max_surviving_delta
        if msd is None or isinstance(msd, bool) or not isinstance(msd, int):
            raise SweepAborted(
                f"{getattr(bundle, 'experiment_id', '?')}: frozen design "
                f"max_surviving_delta={msd!r} is missing or not an int — the "
                "balance gate cannot be skipped on a policy-required sweep")
        return cls(retries_per_unit=0, max_surviving_delta=msd,
                   execution_order=execution_order,
                   record_execution_index=record_execution_index)


class SweepAborted(Exception):
    """A precondition failed mid-sweep — regime drift, a repulled digest, or
    the wall-clock deadline. Recorded and surfaced, never worked around."""


class SweepUnbalanced(SweepAborted):
    """Per-condition surviving counts differ by more than the caller's bound.
    Differential dropout is observationally identical to a real effect (the
    survivors of the lossy condition are a biased subsample), so an unbalanced
    pack is refused as unanalyzable rather than reported with a caveat."""

    def __init__(self, message: str, *, completed_result=None):
        super().__init__(message)
        # A policy-required no-reroll sweep may already have durably recorded
        # every success/tombstone before the balance verdict is known.  The
        # bounded M8 driver may use this result only to close that complete
        # terminal pack as a no-statistics inconclusive outcome.
        self.completed_result = completed_result


class TerminalLedgerError(SchemaError, SweepAborted):
    """A terminal-ledger snapshot is invalid for execution or derivation."""


def _require_single_link_manifest(canonical: str) -> None:
    """Refuse an existing manifest inode reachable through multiple names.

    The lock identity and adjacent tombstone path are both path-scoped.  Two
    hard-linked manifest names would therefore select different lock and
    tombstone paths for the same success bytes.  Inode-key locking cannot make
    those adjacent ledgers agree, so multiply-linked manifests are unsupported
    and fail closed before any lifecycle body is entered.  A missing target is
    valid: first execution creates the manifest only after taking its path lock.
    """
    try:
        links = os.stat(canonical).st_nlink
    except FileNotFoundError:
        return
    except OSError as exc:
        raise SweepAborted(
            f"manifest target {canonical!r} cannot be inspected before "
            f"ownership ({exc})") from exc
    if links != 1:
        raise SweepAborted(
            f"manifest target {canonical!r} has {links} hard links; "
            "multiply-linked manifests are unsupported because adjacent "
            "terminal ledgers would be ambiguous")


def _manifest_lock_identity(manifest_path: str) -> tuple[str, str]:
    """Canonical manifest target and its persistent process-lock path.

    The lock file lives outside the evidence tree so acquiring it before every
    ledger read does not create or alter experiment evidence.  Its name is a
    hash of the canonical target, so relative/absolute and symlink spellings of
    one manifest converge.  The file is deliberately persistent: liveness is a
    kernel property of the open descriptor, never file presence or age.
    """
    try:
        canonical = os.path.realpath(os.path.abspath(os.fspath(manifest_path)))
    except (TypeError, ValueError, OSError) as exc:
        raise SweepAborted(
            f"manifest path {manifest_path!r} cannot be canonicalized for "
            f"exclusive execution ({exc})") from exc
    _require_single_link_manifest(canonical)
    digest = hashlib.sha256(os.fsencode(canonical)).hexdigest()
    # The namespace must be process-invariant.  tempfile.gettempdir() is not:
    # TMPDIR/TMP/TEMP and tempfile.tempdir can differ between two workers that
    # share one manifest, which gives each a different inode and defeats flock.
    # POSIX /tmp is an absolute host-shared namespace; inability to create or
    # lock here is handled fail-closed by _manifest_advisory_lock.
    lock_root = os.path.join(os.path.realpath("/tmp"),
                             "agent-coliseum-manifest-locks-v1")
    return canonical, os.path.join(lock_root, f"{digest}.lock")


def _posix_lock_module():
    """Load the required POSIX locking primitive without a silent fallback."""
    try:
        import fcntl
    except (ImportError, OSError) as exc:
        raise SweepAborted(
            "manifest execution requires POSIX advisory locking; this "
            "platform cannot provide it") from exc
    if not hasattr(fcntl, "flock") or not hasattr(fcntl, "LOCK_NB"):
        raise SweepAborted(
            "manifest execution requires POSIX flock with non-blocking mode")
    return fcntl


@contextmanager
def _manifest_advisory_lock(manifest_path: str):
    """Hold one non-blocking lock for the complete manifest lifecycle.

    Contention and unavailable locking refuse before the sweep body is entered.
    The lock file is opened without truncation and is never removed, replaced,
    expired, or overridden.  Closing this call's descriptor releases only this
    holder's kernel-managed lock, including when the body raises.
    """
    canonical, lock_path = _manifest_lock_identity(manifest_path)
    fcntl = _posix_lock_module()
    try:
        os.makedirs(os.path.dirname(lock_path), mode=0o700, exist_ok=True)
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError as exc:
        raise SweepAborted(
            f"cannot open manifest execution lock for {canonical!r} "
            f"({exc})") from exc
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            raise SweepAborted(
                f"manifest {canonical!r} is already owned by another sweep; "
                "concurrent execution is refused") from exc
        # Close the selection/acquisition window: an alias added while this
        # process was opening the persistent lock still refuses before the
        # lifecycle body.  Cooperative contenders will likewise observe and
        # refuse a multiply-linked target.
        _require_single_link_manifest(canonical)
        # The caller consumes this exact canonical target.  Lock selection and
        # the ledger path therefore cannot diverge through a mutable/non-stable
        # input mapping after ownership was acquired.
        yield canonical
    finally:
        # POSIX releases this descriptor's flock on close.  Do not unlink the
        # persistent lock file: existence is not ownership and another holder
        # may already be waiting/open on the same inode.
        os.close(fd)


# Typed failure kinds for per-condition dropout accounting (m8 Phase 2, F6).
# Live-specific failure is a MEASUREMENT, not noise: a condition whose history
# makes the model deliberate longer times out more often, and its survivors are
# the runs that finished fast. Classification is STRUCTURAL — exception type and
# the __cause__/__context__ chain only. Error text is never parsed: a provider
# is free to reword its messages, and a classifier that reads prose silently
# reclassifies real dropout as "other" the day it does.
FAILURE_KINDS = ("timeout", "connection", "http_error", "other")


def classify_failure(exc: BaseException) -> str:
    """One of FAILURE_KINDS, derived from the exception's type and its cause
    chain. urllib raises HTTPError (a URLError subclass) for a 500, a bare
    URLError wrapping the socket error for a reset, and TimeoutError for a
    budget overrun — all three arrive here wrapped by whatever the agent layer
    re-raised, so the whole chain is walked, nearest cause first."""
    import urllib.error

    seen = []
    cur: BaseException | None = exc
    while cur is not None and len(seen) < 32:
        seen.append(cur)
        cur = cur.__cause__ or cur.__context__
    for e in seen:
        # order matters: HTTPError IS a URLError, and a socket timeout is both
        # an OSError and (3.10+) TimeoutError, so the most specific wins
        if isinstance(e, TimeoutError):
            return "timeout"
        if isinstance(e, urllib.error.HTTPError):
            return "http_error"
        if isinstance(e, (ConnectionError, urllib.error.URLError)):
            return "connection"
    return "other"


def norm_digest(d: str) -> str:
    """Canonical digest hex for EQUALITY only: drop an optional 'sha256:'
    prefix so a frozen bare-hex config and a served 'sha256:'-prefixed digest
    (ollama versions differ) compare on identity, never on formatting. The
    regime hash still stores the raw served digest verbatim — this normalizes
    the preflight comparison, not the recorded lineage."""
    return (d or "").split(":", 1)[-1].strip().lower()


def verify_run_replay(run_dir: str, config_dir: str) -> tuple[bool, str]:
    """Re-run from run.json config into a temp dir and byte-compare
    decisions.jsonl — the same gate as `textlab replay`, but returning
    (ok, detail) instead of exiting. LLM runs replay from their captured raw
    outputs (live-API determinism is never claimed); scripted runs re-execute
    live. Shared by the interactive CLI and the audited ollama_local driver."""
    import filecmp
    import tempfile

    from coliseum.textlab.runner import run_scenario

    run = json.load(open(os.path.join(run_dir, "run.json"), encoding="utf-8"))
    path = os.path.join(config_dir, f"{run['scenario_id']}.yaml")
    is_llm = run["agent_id"].startswith("llm:")
    replay_from = run_dir if is_llm else None
    with tempfile.TemporaryDirectory() as tmp:
        result = run_scenario(
            path, run["agent_id"], run["seed"], out_root=tmp,
            arbitration=run.get("arbitration", "planner_priority"),
            replay_from=replay_from,
            # scripted re-execution must replicate the RECORDED regime — the
            # interaction mode lives in the hashed behavioral_config, so
            # omitting it made every scripted sequential_history run drift
            # against itself (LLM runs were unaffected: replay_from pulls the
            # mode from the manifest and overrides this argument)
            interaction_mode=run.get("interaction_mode",
                                     "independent_vignettes"))
        if result.run_id != run["run_id"]:
            return (False, f"config drift: replay produced run_id "
                    f"{result.run_id} != {run['run_id']} (scenario file or "
                    "agent code changed since the run was recorded)")
        same = filecmp.cmp(
            os.path.join(run_dir, "decisions.jsonl"),
            os.path.join(result.run_dir, "decisions.jsonl"), shallow=False)
    return (same, "byte-identical" if same
            else "decisions.jsonl differs between original and replay")


def _file_sha256(path: str, *, absent_as_empty: bool = False) -> str:
    """sha256 hex of the EXACT file bytes. With absent_as_empty a missing file
    hashes as the empty file — the documented captures.jsonl convention for
    scripted runs, which capture nothing by construction."""
    if absent_as_empty and not os.path.exists(path):
        return hashlib.sha256(b"").hexdigest()
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_pack_replay_locked(manifest_path: str, out_root: str,
                               config_dir: str,
                               planned_design: dict) -> dict:
    """Provider-free replay attestation for a WHOLE pack (M8 Phase-2 audit
    c-001, finding 0 — generator side).

    Runs verify_run_replay on EVERY manifest row and, only if every run
    replays, writes <out_root>/replay_attestation.json binding each run's
    exact evidence bytes (run.json / decisions.jsonl / captures.jsonl sha256),
    the manifest bytes, and the adjacent tombstone-ledger bytes or canonical
    absence to the replay result. The frozen analysis path authenticates this
    receipt instead of trusting mutable admission booleans.

    FAIL CLOSED: any invalid terminal snapshot, replay failure, or missing/empty
    manifest raises and writes NO attestation — not even a partial one — and a
    stale attestation from a previous pass is removed before verification
    starts, so a failing pack can never sit next to a valid-looking receipt.
    The attestation is written atomically (temp file + rename) only after the
    last row verifies.

    Returns the attestation dict exactly as written."""
    if not os.path.exists(manifest_path):
        raise SweepAborted(f"verify_pack_replay: no manifest at {manifest_path}")
    attestation_path = os.path.join(out_root, "replay_attestation.json")
    rows, _tombstones = terminal_ledgers_load(
        manifest_path, out_root, planned_design=planned_design,
        require_tombstone_regime_anchors=True)
    if not rows:
        raise SweepAborted(f"verify_pack_replay: {manifest_path} has no rows — "
                           "refusing to attest an empty pack")
    runs = {}
    for rec in rows.values():             # manifest file order (insertion order)
        run_dir = os.path.join(out_root, rec["dir"])
        ok, detail = verify_run_replay(run_dir, config_dir)
        if not ok:
            raise SweepAborted(
                f"verify_pack_replay: {rec['run_id']} ({rec['dir']}) failed "
                f"provider-free replay: {detail} — no attestation written")
        runs[rec["run_id"]] = {
            "run_dir": rec["dir"],
            "replay_ok": True,
            "run_json_sha256": _file_sha256(os.path.join(run_dir, "run.json")),
            "decisions_sha256": _file_sha256(os.path.join(run_dir, "decisions.jsonl")),
            "captures_sha256": _file_sha256(os.path.join(run_dir, "captures.jsonl"),
                                            absent_as_empty=True),
        }
    attestation = {
        # Version 1 names the frozen per-run replay record contract consumed by
        # metrics.  The terminal-ledger identity is an additive top-level
        # envelope field; changing that frozen version would alter the admitted
        # analysis identity despite leaving every per-run record unchanged.
        "attestation_version": "1",
        "verified_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "manifest_sha256": _file_sha256(manifest_path),
        "tombstone_ledger": tombstone_ledger_identity(manifest_path),
        "runs": runs,
    }
    tmp_path = attestation_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(attestation, fh, indent=2)
        fh.write("\n")
    os.replace(tmp_path, attestation_path)
    return attestation


def verify_pack_replay(manifest_path: str, out_root: str, config_dir: str,
                       *, planned_design: dict | None = None,
                       registry_path: str | None = None,
                       experiment_id: str | None = None) -> dict:
    """Replay and attest one stable, validated terminal-ledger snapshot.

    The adjacent tombstone ledger is part of the evidence identity even when
    it is absent.  Holding the same manifest-scoped lock used by ``run_sweep``
    prevents either terminal ledger from changing between validation, replay,
    and the atomic attestation write.
    """
    with _manifest_advisory_lock(manifest_path) as canonical_manifest:
        attestation_path = os.path.join(out_root, "replay_attestation.json")
        if os.path.exists(attestation_path):
            os.remove(attestation_path)  # every post-lock refusal clears stale output
        if planned_design is None:
            if not registry_path or not experiment_id:
                raise SweepAborted(
                    "verify_pack_replay requires planned_design or both "
                    "registry_path and experiment_id")
            from .registry import load_verified_bundle
            planned_design = load_verified_bundle(
                registry_path, experiment_id).planned_design
        return _verify_pack_replay_locked(
            canonical_manifest, out_root, config_dir,
            planned_design=planned_design)


def surviving_counts_from_result(result: "SweepResult") -> dict:
    """Per-condition surviving-run counts in the coordinate shape the analysis
    consumes: a plain {scenario_id: int}. SweepResult keys conditions by
    (model, scenario); two models in one sweep are two separate comparisons
    and must never be pooled (see SweepResult), so a multi-model result is
    refused — extract per model instead."""
    models = {model for (model, _scenario) in result.surviving}
    if len(models) > 1:
        raise SweepAborted(
            f"surviving_counts_from_result: result spans models "
            f"{sorted(models)} — two models are two separate comparisons and "
            "their counts must never be pooled")
    return {scenario: n
            for (_model, scenario), n in sorted(result.surviving.items())}


def manifest_load(path: str, out_root: str) -> dict:
    """(regime_id, scenario_seed, sampler_seed) -> validated row.

    Full-row validation (audit item 6 + blocker 4): every row must carry the
    COMPLETE current schema (REQUIRED_ROW_FIELDS) and every field must agree
    with its run.json evidence — a manifest can neither assert anything its
    evidence contradicts nor omit its way past validation. Duplicate resume
    keys are REFUSED outright (no last-row-wins); so are dir/attempt
    mismatches and legacy dir-less rows."""
    done = {}
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            rec = json.loads(line)
            where = f"{path}:{i + 1}"
            if "dir" not in rec:
                raise SchemaError(
                    f"{where}: legacy manifest row without an exact evidence dir — "
                    "REFUSED (run scripts/migrate_manifest.py or use a fresh manifest)")
            missing = [f for f in REQUIRED_ROW_FIELDS if f not in rec]
            if missing:
                raise SchemaError(
                    f"{where}: incomplete manifest row — missing required "
                    f"current-schema fields {missing}; legacy rows must go "
                    "through scripts/migrate_manifest.py, never implicit "
                    "acceptance")
            run_dir = os.path.join(out_root, rec["dir"])
            manifest_file = os.path.join(run_dir, "run.json")
            if not os.path.exists(manifest_file):
                raise SchemaError(f"{where}: evidence dir missing run.json: {run_dir}")
            run = json.load(open(manifest_file, encoding="utf-8"))
            decision_path = []
            decisions_file = os.path.join(run_dir, "decisions.jsonl")
            if os.path.exists(decisions_file):
                with open(decisions_file, encoding="utf-8") as decisions:
                    for decision_line in decisions:
                        event = json.loads(decision_line)
                        if event.get("kind") == "decision_node":
                            decision_path.append(event["data"]["final_action"])
            expected = {
                "run_id": run["run_id"],
                "regime_id": run.get("comparison_regime_id", ""),
                "model": run.get("agent_config", {}).get("model", ""),
                "digest": run.get("agent_config", {}).get("model_digest", ""),
                "scenario": run["scenario_id"],
                "scenario_hash": run.get("scenario_hash", ""),
                "seed": run["seed"],
                "scenario_seed": run.get("scenario_seed", run["seed"]),
                "sampler_seed": run.get("sampler_seed"),
                "variant_id": run["variant_id"],
                "temperature": run.get("sampling", {}).get("temperature", 0),
                "sampling_mode": run.get("sampling", {}).get("mode", "deterministic"),
                "arbitration": run.get("arbitration", "planner_priority"),
                "reportable": run.get("reportable", True),
                "stochastic_reportable": run.get("stochastic_reportable", False),
                "interaction_mode": run.get("interaction_mode", "independent_vignettes"),
                "path": decision_path,
            }
            for field_name, want in expected.items():
                if field_name in rec and rec[field_name] != want:
                    raise SchemaError(f"{where}: {field_name} mismatch vs evidence "
                                      f"({rec[field_name]!r} vs {want!r})")
            m = _ATTEMPT_RE.search(rec["dir"])
            dir_attempt = int(m.group(1)) if m else 0
            if _ATTEMPT_RE.sub("", rec["dir"]) != run["run_id"]:
                raise SchemaError(f"{where}: dir {rec['dir']!r} does not name its run_id "
                                  f"{run['run_id']!r}")
            if run.get("attempt", 0) != dir_attempt:
                raise SchemaError(f"{where}: dir attempt .a{dir_attempt} disagrees with "
                                  f"run.json attempt {run.get('attempt', 0)}")
            key = (run.get("comparison_regime_id", ""),
                   run.get("scenario_seed", run["seed"]),
                   run.get("sampler_seed"))
            if key in done:
                raise SchemaError(f"{where}: duplicate resume key {key} — REFUSED "
                                  "(no last-row-wins; deduplicate the manifest)")
            done[key] = rec
    return done


def _tombstone_path(manifest_path: str) -> str:
    """The durable per-cell failure ledger, colocated with the manifest it
    resumes against."""
    return manifest_path + ".tombstones.jsonl"


def tombstone_load(manifest_path: str) -> dict:
    """(regime_id, scenario_seed, sampler_seed) -> tombstone row for every cell a
    prior retries_per_unit=0 sweep attempted and FAILED (audit b-002 finding 1).

    A tombstone is a DURABLE TYPED FAILURE: under retries_per_unit=0 a failed
    unit is a terminal outcome, never a re-roll, so resume must never re-attempt
    a key that carries one. Absent ledger -> no tombstones (a resume that never
    opted in behaves exactly as before). Keyed on the SAME resume identity as the
    manifest, so a manifested success and a tombstone can never target one key
    without contradicting each other.

    VALIDATED, not merely parsed (audit c-008). A tombstone can suppress the
    generation of a planned unit, so it must carry the full provenance that
    proves WHICH unit it belongs to and WHY it failed. Rows missing that
    provenance, and duplicate resume keys, are REFUSED — the same
    no-last-row-wins contract `manifest_load` enforces for successes."""
    done = {}
    path = _tombstone_path(manifest_path)
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            where = f"{path}:{i + 1}"
            try:
                rec = json.loads(line)
            except (TypeError, ValueError) as exc:
                raise SchemaError(
                    f"{where}: tombstone row is not valid JSON ({exc})"
                ) from exc
            if not isinstance(rec, dict):
                raise SchemaError(f"{where}: tombstone row is not an object")
            missing = [f for f in REQUIRED_TOMBSTONE_FIELDS if f not in rec]
            if missing:
                raise SchemaError(
                    f"{where}: incomplete tombstone row — missing {missing}. A "
                    "tombstone suppresses a planned unit, so one without full "
                    "provenance can never stand in for that unit")
            for field in ("regime_id", "model", "scenario", "failure_kind",
                          "error", "recorded_utc"):
                if not isinstance(rec[field], str) or not rec[field]:
                    raise SchemaError(
                        f"{where}: tombstone {field}={rec[field]!r} must be a "
                        "non-empty string")
            scenario_seed = rec["scenario_seed"]
            if isinstance(scenario_seed, bool) or not isinstance(
                    scenario_seed, int):
                raise SchemaError(
                    f"{where}: tombstone scenario_seed={scenario_seed!r} "
                    "must be an integer")
            sampler_seed = rec["sampler_seed"]
            if (isinstance(sampler_seed, bool)
                    or (sampler_seed is not None
                        and not isinstance(sampler_seed, int))):
                raise SchemaError(
                    f"{where}: tombstone sampler_seed={sampler_seed!r} must "
                    "be an integer or null")
            if rec["failure_kind"] not in FAILURE_KINDS:
                raise SchemaError(
                    f"{where}: tombstone failure_kind="
                    f"{rec['failure_kind']!r} is not one of the declared "
                    f"terminal failure kinds {FAILURE_KINDS!r}")
            key = (rec["regime_id"], rec["scenario_seed"], rec["sampler_seed"])
            if key in done:
                raise SchemaError(
                    f"{where}: duplicate tombstone resume key {key!r} — REFUSED "
                    "(no last-row-wins: contradictory durable failures cannot "
                    "silently collapse into one resolved cell)")
            done[key] = rec
    return done


def _terminal_coord(row: dict) -> tuple:
    """The experiment-coordinate identity shared by both terminal ledgers."""
    return (row.get("model"), row.get("scenario"),
            row.get("scenario_seed"), row.get("sampler_seed"))


def _planned_design_coords(planned_design: dict) -> set:
    """Model/scenario/seed coordinates frozen without provider construction.

    Regime membership is checked against surviving success anchors; every
    remaining coordinate axis is available directly in the planned design.
    """
    if not isinstance(planned_design, dict):
        raise SchemaError("planned_design must be an object")
    axes = {}
    for field in ("models", "scenarios", "scenario_seeds", "sampler_seeds"):
        values = planned_design.get(field)
        if not isinstance(values, list) or not values:
            raise SchemaError(
                f"planned_design.{field} must be a non-empty list")
        if len(values) != len(set(values)):
            raise SchemaError(
                f"planned_design.{field} contains duplicate values")
        axes[field] = values
    return {
        (model, scenario, scenario_seed, sampler_seed)
        for model in axes["models"]
        for scenario in axes["scenarios"]
        for scenario_seed in axes["scenario_seeds"]
        for sampler_seed in axes["sampler_seeds"]
    }


def tombstone_ledger_identity(manifest_path: str) -> dict:
    """Exact adjacent-ledger identity, including authenticated absence."""
    path = _tombstone_path(manifest_path)
    if not os.path.exists(path):
        return {"state": "absent", "sha256": None}
    if not os.path.isfile(path):
        raise SchemaError(
            f"tombstone ledger path is not a regular file: {path}")
    try:
        digest = _file_sha256(path)
    except OSError as exc:
        raise SchemaError(
            f"tombstone ledger cannot be hashed: {path} ({exc})") from exc
    return {"state": "present", "sha256": digest}


def terminal_ledgers_load(
        manifest_path: str, out_root: str, *,
        planned_design: dict | None = None,
        require_tombstone_regime_anchors: bool = False) -> tuple[dict, dict]:
    """Load one validated success/tombstone snapshot.

    Key- and coordinate-level contradictions are invalid on every consumer,
    not only during execution.  When a frozen design is supplied, tombstones
    must lie in its scenario/seed grid.  Derived provider-free consumers also
    require each tombstone's model/scenario regime to be uniquely anchored by
    validated surviving evidence from that same group.

    The caller owns the manifest advisory lock while consuming the returned
    snapshot; this function intentionally does not acquire it recursively.
    """
    successes = manifest_load(manifest_path, out_root)
    tombstones = tombstone_load(manifest_path)

    key_both = set(successes) & set(tombstones)
    if key_both:
        example = sorted(key_both, key=repr)[0]
        raise TerminalLedgerError(
            f"terminal ledgers are contradictory: success and tombstone "
            f"share terminal key {example!r}; terminal outcomes disagree")

    success_coords = {}
    for row in successes.values():
        success_coords.setdefault(_terminal_coord(row), []).append(row)
    tombstone_coords = {}
    for row in tombstones.values():
        tombstone_coords.setdefault(_terminal_coord(row), []).append(row)

    coordinate_both = set(success_coords) & set(tombstone_coords)
    if coordinate_both:
        example = sorted(coordinate_both, key=repr)[0]
        raise TerminalLedgerError(
            f"terminal ledgers are contradictory at the same planned "
            f"coordinate {example!r}: success and tombstone outcomes coexist")

    duplicate_tombstones = {
        coord for coord, rows in tombstone_coords.items() if len(rows) > 1}
    if duplicate_tombstones:
        example = sorted(duplicate_tombstones, key=repr)[0]
        raise TerminalLedgerError(
            f"terminal ledger carries multiple tombstones for planned "
            f"coordinate {example!r}")

    if planned_design is not None:
        planned = _planned_design_coords(planned_design)
        foreign = []
        for row in tombstones.values():
            coord = (row.get("model"), row.get("scenario"),
                     row.get("scenario_seed"),
                     row.get("sampler_seed"))
            if coord not in planned:
                foreign.append(coord)
        if foreign:
            raise TerminalLedgerError(
                f"terminal ledger contains tombstone outside the frozen "
                f"model/scenario/seed grid: {foreign[0]!r}")

    if require_tombstone_regime_anchors and tombstones:
        if planned_design is None:
            raise SchemaError(
                "tombstone regime validation requires planned_design")
        anchors = {}
        for row in successes.values():
            group = (row.get("model"), row.get("scenario"))
            anchors.setdefault(group, set()).add(row.get("regime_id"))
        for row in tombstones.values():
            group = (row.get("model"), row.get("scenario"))
            regimes = anchors.get(group, set())
            if len(regimes) != 1:
                raise TerminalLedgerError(
                    f"tombstone for {group!r} has no unique validated success "
                    "regime anchor")
            (expected_regime,) = tuple(regimes)
            if row.get("regime_id") != expected_regime:
                raise TerminalLedgerError(
                    f"tombstone for {group!r} carries regime_id "
                    f"{row.get('regime_id')!r}, expected anchored regime "
                    f"{expected_regime!r}")

    return successes, tombstones


def validate_terminal_ledger_attestation(attestation: dict,
                                         manifest_path: str) -> dict:
    """Bind downstream use to the current bytes or absence of both ledgers."""
    if not isinstance(attestation, dict):
        raise SchemaError("replay attestation must be an object")
    try:
        manifest_sha = _file_sha256(manifest_path)
    except OSError as exc:
        raise SchemaError(
            f"manifest cannot be hashed: {manifest_path} ({exc})") from exc
    if attestation.get("manifest_sha256") != manifest_sha:
        raise SchemaError(
            "replay attestation does not bind the current manifest bytes")
    current_tombstone = tombstone_ledger_identity(manifest_path)
    if attestation.get("tombstone_ledger") != current_tombstone:
        raise SchemaError(
            "replay attestation does not bind the current tombstone ledger "
            "bytes or its authenticated absence")
    return current_tombstone


def resolve_sampling(temperature: float, sampler_seeds):
    """(sampling, sampler_seeds, mode) from the temperature/seed pair, with the
    same validation both entrypoints must pass before any run."""
    if temperature and temperature > 0:
        sampling = {"mode": "stochastic", "temperature": temperature}
        seeds = list(sampler_seeds or [])
        if not seeds:
            raise SweepAborted("stochastic sweep requires sampler_seeds")
        mode = "stochastic"
    else:
        sampling = None
        seeds = [None]
        mode = "deterministic"
    validate_sampling(sampling, seeds[0])
    return sampling, seeds, mode


class SweepResult:
    def __init__(self):
        self.rows_written = 0
        self.run_dirs = []          # repo-absolute dirs produced this call
        self.regime_ids = set()
        self.digests = {}           # model -> pinned digest actually served
        self.skipped_resumed = 0    # rows already present in the manifest
        self.errors = []            # (scenario, seed, sampler_seed, message)
        # ---- m8 Phase 2, audit b-002 finding 1 (retries_per_unit=0). Durable
        # per-cell failure tombstones: a failed unit is a typed outcome, never a
        # re-roll. `tombstoned_resumed` counts cells skipped this call because a
        # prior call already recorded their failure; `tombstones_written` counts
        # new failure tombstones persisted this call. Both stay 0 unless the
        # caller opts into retries_per_unit=0, so default sweeps are unchanged.
        self.tombstoned_resumed = 0
        self.tombstones_written = 0
        # ---- m8 Phase 2 additions. A condition key is (model, scenario): the
        # A/B/C conditions of the frozen design are scenarios, but two models in
        # one sweep are two separate comparisons and must never be pooled.
        self.execution_order = "blocked"
        self.execution_log = []     # per ATTEMPTED cell, in realized order
        self.attempted = {}         # condition -> cells attempted this call
        self.surviving = {}         # condition -> cells that produced a row
        self.dropouts = {}          # condition -> {failure kind -> count}
        self.resumed = {}           # condition -> cells already in the manifest

    def _condition(self, key):
        """Register a condition so a zero-loss condition still appears in the
        accounting — an absent key and a zero count are not the same claim."""
        self.attempted.setdefault(key, 0)
        self.surviving.setdefault(key, 0)
        self.resumed.setdefault(key, 0)
        self.dropouts.setdefault(key, {k: 0 for k in FAILURE_KINDS})
        return key

    def dropout_total(self, key) -> int:
        return sum(self.dropouts.get(key, {}).values())

    def check_condition_balance(self, max_surviving_delta: int):
        """Fail-closed balance gate (m8 Phase 2, F6). Refuse when any two
        conditions of the SAME model differ in surviving-run count by more than
        `max_surviving_delta`. The bound is the caller's — it comes from the
        frozen design, never from a default baked in here.

        Returns None when balanced; raises SweepUnbalanced naming the offending
        conditions, their counts and their dropouts, and the bound."""
        if max_surviving_delta is None:
            raise ValueError("max_surviving_delta is required — the balance "
                             "bound comes from the frozen design")
        if max_surviving_delta < 0:
            raise ValueError(f"max_surviving_delta must be >= 0, "
                             f"got {max_surviving_delta}")
        by_model = {}
        for (model, scenario) in sorted(self.surviving):
            by_model.setdefault(model, []).append((model, scenario))
        for model, keys in sorted(by_model.items()):
            counts = {k: self.surviving[k] for k in keys}
            lo_key = min(counts, key=lambda k: (counts[k], k))
            hi_key = max(counts, key=lambda k: (counts[k], k))
            delta = counts[hi_key] - counts[lo_key]
            if delta > max_surviving_delta:
                detail = "; ".join(
                    f"{k[1]}: {counts[k]} surviving of {self.attempted[k]} "
                    f"attempted, dropouts {self.dropouts[k]}"
                    for k in keys)
                raise SweepUnbalanced(
                    f"{model}: per-condition surviving counts differ by "
                    f"{delta} > bound {max_surviving_delta} — "
                    f"{lo_key[1]} ({counts[lo_key]}) vs {hi_key[1]} "
                    f"({counts[hi_key]}); differential dropout is "
                    f"indistinguishable from an order effect, so this pack is "
                    f"NOT analyzable. Per condition: {detail}",
                    completed_result=self)
        return None


def cell_order(scenarios, seeds, sampler_seeds, execution_order="blocked"):
    """The (scenario, scenario_seed, sampler_seed) execution sequence.

    "blocked" is the historical nesting scenario -> scenario_seed ->
    sampler_seed: all of condition A, then all of B, then all of C. Provably
    irrelevant for a scripted decider; for a live model it perfectly confounds
    condition with backend state (thermal throttling, KV-cache/context-shift
    state, another tenant forcing an unload/reload, a server restart) because
    wall-clock position is 100% correlated with condition (m8 Phase 2, F7).

    "interleaved" is the frozen Phase-2 discipline (scenario_seed, sampler_seed)
    -> condition: A/B/C for one unit are drawn adjacently, so backend drift hits
    all three conditions alike instead of loading onto whichever ran last."""
    if execution_order == "blocked":
        return [(sc, ss, ks) for sc in scenarios for ss in seeds
                for ks in sampler_seeds]
    if execution_order == "interleaved":
        return [(sc, ss, ks) for ss in seeds for ks in sampler_seeds
                for sc in scenarios]
    raise SweepAborted(f"unknown execution_order {execution_order!r} — "
                       "expected 'blocked' or 'interleaved'")


def run_sweep(spec: dict, *, deadline: float | None = None,
              expected_digests: dict | None = None, progress=None,
              execution_order: str = "blocked",
              record_execution_index: bool | None = None,
              max_surviving_delta: int | None = None,
              retries_per_unit: int | None = None,
              execution_policy: "ExecutionPolicy | None" = None) -> SweepResult:
    """Run one sweep while exclusively owning its manifest lifecycle.

    The manifest-derived POSIX lock is acquired before the implementation can
    inspect either terminal ledger and remains held through validation, setup,
    execution, terminal writes, balance/completion checks, and return cleanup.
    """
    manifest_path = spec["manifest"]
    locked_spec = dict(spec)
    with _manifest_advisory_lock(manifest_path) as canonical_manifest:
        locked_spec["manifest"] = canonical_manifest
        return _run_sweep_locked(
            locked_spec, deadline=deadline, expected_digests=expected_digests,
            progress=progress, execution_order=execution_order,
            record_execution_index=record_execution_index,
            max_surviving_delta=max_surviving_delta,
            retries_per_unit=retries_per_unit,
            execution_policy=execution_policy)


def _run_sweep_locked(spec: dict, *, deadline: float | None = None,
                      expected_digests: dict | None = None, progress=None,
                      execution_order: str = "blocked",
                      record_execution_index: bool | None = None,
                      max_surviving_delta: int | None = None,
                      retries_per_unit: int | None = None,
                      execution_policy: "ExecutionPolicy | None" = None
                      ) -> SweepResult:
    """Execute (models x scenarios x scenario-seeds x sampler-seeds), appending
    validated rows to spec['manifest'] and resuming past rows already present.

    spec keys: models[list], scenarios[list of names], seeds[list of int],
    sampler_seeds[list|None], temperature[float], arbitration[str],
    interaction[str], config_dir[str], out_root[str], manifest[str].

    `expected_digests` (model -> pinned digest) makes a repulled model a hard
    SweepAborted before any compute — a served digest that differs from the
    frozen one is a new regime, never a silent substitution. `deadline` is a
    time.monotonic() bound; crossing it aborts (the killable child also caps
    wall-clock, this is the in-driver courtesy check).

    m8 Phase 2 options — all OPT-IN, so a sweep that does not request them
    executes exactly as before and Phase-1 evidence regenerates byte-for-byte:

    `execution_order` "blocked" (default, historical) or "interleaved" (see
    cell_order). `record_execution_index` writes the monotonic per-run
    execution index into the manifest row so the REALIZED order is auditable
    from the evidence alone; it defaults to on under "interleaved" and off
    under "blocked" (an explicit bool overrides either way). The index is
    always available on `result.execution_log` regardless.

    `max_surviving_delta` runs the fail-closed balance gate at the end of the
    sweep (see SweepResult.check_condition_balance) and raises SweepUnbalanced
    rather than returning a pack whose conditions lost unequal numbers of runs.
    Failed runs are still recorded in `result.errors` and never erased.

    `retries_per_unit` (audit b-002 finding 1) enforces the frozen
    one-effective-unit contract. Default None keeps today's behaviour: a failed
    cell is recorded only in memory, so a later resume re-attempts it. Passing 0
    — the frozen M8 design's declared value — persists a DURABLE typed failure
    tombstone for every failed cell (see tombstone_load) and honours it on
    resume: a completed-or-failed unit is NEVER re-attempted, so no provider call
    can re-roll a failure into a success. It is opt-in and writes a separate
    ledger file, so a default sweep's manifest regenerates byte-for-byte.

    `execution_policy` (b-003 / c-003 finding class) is the STRUCTURAL form of
    the above. A frozen `ExecutionPolicy` bundles retries_per_unit /
    max_surviving_delta / execution_order / record_execution_index into one typed
    object. For a POLICY_REQUIRED experiment (identified by spec['experiment_id'])
    it is MANDATORY and fails closed here before any provider contact if absent
    or if its retries_per_unit != 0 — so a production caller can no longer omit
    the frozen retry/balance contract by forgetting a keyword. When supplied it
    is the authority: the individual retries_per_unit / max_surviving_delta /
    execution_order / record_execution_index kwargs must not also be passed with
    a conflicting value."""
    say = progress or (lambda *_a, **_k: None)

    # STRUCTURAL execution-policy enforcement (b-003 / c-003 / a-006 B-0/B-1/E-1).
    # Policy-requiredness is decided by BOTH the declared experiment_id AND
    # SCENARIO MEMBERSHIP, so a generic/anonymous caller cannot relabel a
    # protected M8 sweep as ordinary by omitting the identity. When required, the
    # ExecutionPolicy is MANDATORY and is RE-VERIFIED against a freshly loaded
    # frozen authority, so a forged/weakened policy (or a duck-typed one) is
    # refused before any provider contact.
    from coliseum.textlab.registry import (POLICY_REQUIRED_EXPERIMENTS,
                                           protected_scenarios,
                                           load_verified_bundle)
    experiment_id = spec.get("experiment_id")
    registry_path = spec.get("registry_path", "configs/registry/experiments.yaml")
    spec_scenarios = list(spec.get("scenarios") or [])
    # b-006 (fail-closed): a FAILED protected-scenario resolution is NOT "no
    # protected scenarios". A benign registry with no policy-required designs
    # returns an EMPTY map WITHOUT raising and is still allowed (the sweep is
    # simply non-policy); but if `protected_scenarios` RAISES — the caller-
    # selected registry cannot resolve protection — the sweep cannot prove its
    # scenarios are non-protected and MUST fail closed before any provider
    # contact, never silently proceed as an ordinary (non-policy) sweep.
    try:
        protmap = protected_scenarios(registry_path)
    except Exception as exc:
        raise SweepAborted(
            f"cannot resolve protected scenarios from registry "
            f"{registry_path!r} ({exc}) — a sweep whose scenarios cannot be "
            "proven non-protected fails closed before any provider contact "
            "rather than proceeding as an ordinary sweep") from exc
    protected_owners = {protmap[s] for s in spec_scenarios if s in protmap}
    policy_required = (experiment_id in POLICY_REQUIRED_EXPERIMENTS
                       or bool(protected_owners))

    if policy_required:
        # a protected scenario may never run without its registered identity
        if experiment_id not in POLICY_REQUIRED_EXPERIMENTS:
            raise SweepAborted(
                f"protected scenario(s) {sorted(s for s in spec_scenarios if s in protmap)} "
                f"belong to {sorted(protected_owners)} but the spec has "
                f"experiment_id={experiment_id!r} — a generic or anonymous sweep "
                "(e.g. YAML auto-discovery) may NOT run a policy-required M8 "
                "scenario; supply the registered experiment identity, a verified "
                "ExecutionPolicy, and owner authorization")
        if protected_owners and experiment_id not in protected_owners:
            raise SweepAborted(
                f"experiment_id {experiment_id!r} does not own the protected "
                f"scenarios {sorted(protected_owners)}")
        if execution_policy is None:
            raise SweepAborted(
                f"{experiment_id}: a policy-required live sweep must be driven by "
                "a frozen ExecutionPolicy (execution_policy=...); run_sweep "
                "refuses the permissive default so a failed unit can never be "
                "re-rolled and the balance gate can never be silently skipped")
        # RE-VERIFY the supplied policy against the frozen authority (B-1): a
        # forged ExecutionPolicy (weakened dropout bound, blocked order,
        # suppressed index, nonzero retry) or a duck-typed object is refused.
        try:
            vb = load_verified_bundle(registry_path, experiment_id)
        except Exception as exc:
            raise SweepAborted(
                f"{experiment_id}: cannot load the verified frozen bundle to "
                f"authenticate the ExecutionPolicy ({exc})")
        expected = {"retries_per_unit": 0,
                    "max_surviving_delta": vb.max_surviving_delta,
                    "execution_order": "interleaved",
                    "record_execution_index": True}
        for k, want in expected.items():
            got = getattr(execution_policy, k, None)
            if got != want or (isinstance(got, bool) is not isinstance(want, bool)):
                raise SweepAborted(
                    f"{experiment_id}: ExecutionPolicy.{k}={got!r} != the frozen "
                    f"authority value {want!r} — a policy-required sweep will not "
                    "accept a forged, weakened, or duck-typed execution policy "
                    "(the frozen contract is re-verified against the audited "
                    "profile, not trusted from the caller)")

    if execution_policy is not None:
        # the typed policy is the authority; a conflicting loose kwarg is a
        # caller bug, not a silent override.
        for name, loose, frozen in (
                ("retries_per_unit", retries_per_unit,
                 execution_policy.retries_per_unit),
                ("max_surviving_delta", max_surviving_delta,
                 execution_policy.max_surviving_delta),
                ("execution_order",
                 execution_order if execution_order != "blocked" else None,
                 execution_policy.execution_order),
                ("record_execution_index", record_execution_index,
                 execution_policy.record_execution_index)):
            if loose is not None and loose != frozen:
                raise SweepAborted(
                    f"run_sweep: {name}={loose!r} kwarg conflicts with the "
                    f"execution_policy value {frozen!r} — pass the frozen "
                    "contract through the ExecutionPolicy only")
        retries_per_unit = execution_policy.retries_per_unit
        max_surviving_delta = execution_policy.max_surviving_delta
        execution_order = execution_policy.execution_order
        record_execution_index = execution_policy.record_execution_index

    if retries_per_unit is not None and (isinstance(retries_per_unit, bool)
                                         or retries_per_unit != 0):
        raise SweepAborted(
            f"retries_per_unit={retries_per_unit!r} is not supported — the "
            "frozen design declares retries_per_unit=0 (a failed unit is a typed "
            "outcome, never a re-roll); pass 0 to enforce durable tombstones or "
            "None to retain the historical re-attempt-on-resume behaviour")
    if policy_required and retries_per_unit != 0:
        raise SweepAborted(
            f"{experiment_id}: policy-required sweep resolved "
            f"retries_per_unit={retries_per_unit!r}, not 0 — the frozen "
            "one-effective-unit tombstone contract is mandatory on this path")
    sampling, sampler_seeds, mode = resolve_sampling(
        spec.get("temperature", 0.0), spec.get("sampler_seeds"))
    arbitration = spec.get("arbitration", "planner_priority")
    interaction = spec.get("interaction", "independent_vignettes")
    config_dir = spec["config_dir"]
    out_root = spec["out_root"]
    manifest_path = spec["manifest"]
    scenarios = list(spec["scenarios"])
    seeds = list(spec["seeds"])

    if record_execution_index is None:
        record_execution_index = (execution_order == "interleaved")
    order = cell_order(scenarios, seeds, sampler_seeds, execution_order)

    result = SweepResult()
    result.execution_order = execution_order

    # defense in depth: run_sweep iterates the RAW lists, so a duplicated grid
    # dimension would launch unplanned/duplicate cells (and collide on the
    # resume key). Refuse before any compute — the provenance lint refuses this
    # too, this guards every other caller (e.g. the human CLI).
    for dim, vals in (("models", spec["models"]), ("scenarios", scenarios),
                      ("seeds", seeds), ("sampler_seeds", sampler_seeds)):
        if len(vals) != len(set(vals)):
            raise SweepAborted(
                f"duplicate {dim} in the sweep spec ({vals}) — refusing to "
                "launch unplanned/duplicate cells")

    def _deadline_hit():
        return deadline is not None and time.monotonic() > deadline

    # The planned coordinate is the grid's own axes, not the regime-keyed
    # terminal identity.  This lets the fully-resolved replay path establish
    # exact planned-coordinate containment without model construction.  Regime
    # identity for tombstones is still anchored by validated success evidence.
    planned_coords = {
        (model, scenario_name, scenario_seed, sampler_seed)
        for model in spec["models"]
        for scenario_name in scenarios
        for scenario_seed in seeds
        for sampler_seed in sampler_seeds}
    total = len(planned_coords)

    def _row_coord(row):
        return (row.get("model"), row.get("scenario"),
                row.get("scenario_seed"), row.get("sampler_seed"))

    # Round 4 C-009: validate BOTH complete terminal ledgers exactly once,
    # before model construction, the replay-only return, counting, generation,
    # terminal writes, or completion.  Tombstones are validated even for the
    # historical retry mode: a contradictory ledger is invalid evidence on
    # every path, not only when this call plans to consume failure outcomes.
    loaded_done, loaded_tombstones = terminal_ledgers_load(
        manifest_path, out_root)
    initial_done = MappingProxyType(loaded_done)
    initial_tombstones = MappingProxyType(loaded_tombstones)
    both = set(initial_done) & set(initial_tombstones)
    if both:
        raise SweepAborted(
            f"resume ledger is contradictory: {len(both)} unit(s) carry "
            "BOTH a manifested success and a durable failure tombstone "
            f"(e.g. {sorted(both)[0]!r}) — refusing evidence whose terminal "
            "outcomes disagree")

    foreign = [_row_coord(row) for row in initial_tombstones.values()
               if _row_coord(row) not in planned_coords]
    if foreign:
        raise SweepAborted(
            f"resume ledger contains {len(foreign)} tombstone(s) outside the "
            f"planned grid (e.g. {foreign[0]!r}) — foreign terminal evidence "
            "is refused before model construction")

    def _planned_rows_by_coord(rows):
        grouped = {}
        for row in rows:
            coord = _row_coord(row)
            if coord in planned_coords:
                grouped.setdefault(coord, []).append(row)
        return grouped

    done_by_coord = _planned_rows_by_coord(initial_done.values())
    tombstones_by_coord = _planned_rows_by_coord(initial_tombstones.values())

    # A planned coordinate is the experimental unit.  Different regime keys
    # do not license that one unit to be both a success and a failure, nor to
    # carry multiple durable failures.  Refuse these coordinate-level
    # contradictions before a replay count or model construction.
    coordinate_both = set(done_by_coord) & set(tombstones_by_coord)
    if coordinate_both:
        example = sorted(coordinate_both)[0]
        raise SweepAborted(
            f"resume ledger is contradictory at the same planned coordinate "
            f"{example!r}: success and tombstone outcomes coexist under "
            "different terminal identities")
    duplicate_tombstone_coords = {
        coord for coord, rows in tombstones_by_coord.items() if len(rows) > 1}
    if duplicate_tombstone_coords:
        example = sorted(duplicate_tombstone_coords)[0]
        raise SweepAborted(
            f"resume ledger contains multiple tombstones for one planned "
            f"coordinate {example!r}; one unit may have only one terminal "
            "outcome")

    # Provider-free success accounting is safe only when each planned
    # coordinate has exactly one recorded success. Multiple regimes for one
    # coordinate require normal preflight to select the expected identity and
    # must never be pooled by the replay-only path.
    replay_successes = {
        coord: rows[0] for coord, rows in done_by_coord.items()
        if len(rows) == 1}
    ambiguous_success_coords = {
        coord for coord, rows in done_by_coord.items() if len(rows) > 1}

    replay_tombstones = (initial_tombstones
                         if retries_per_unit == 0 else {})
    # A tombstone counts toward replay-only completion only when a validated
    # unique success regime for the same model/scenario anchors it. An
    # unanchored or ambiguously anchored tombstone requires normal setup to
    # establish the expected regime and is never counted here.
    anchors: dict = {}
    for row in replay_successes.values():
        anchor_key = (row.get("model"), row.get("scenario"))
        anchors.setdefault(anchor_key, set()).add(row.get("regime_id"))
    ambiguous_anchor_groups = {
        anchor_key for anchor_key, regimes in anchors.items()
        if len(regimes) > 1}
    anchored_tombstones = {}
    for row in replay_tombstones.values():
        anchor_key = (row.get("model"), row.get("scenario"))
        expected_anchors = anchors.get(anchor_key, ())
        if len(expected_anchors) == 1 and row.get("regime_id") in expected_anchors:
            anchored_tombstones[_row_coord(row)] = row

    provider_free_complete = (
        total > 0
        and not ambiguous_success_coords
        and not ambiguous_anchor_groups
        and len(anchored_tombstones) == len(replay_tombstones)
        and planned_coords <= (set(replay_successes)
                               | set(anchored_tombstones)))
    if provider_free_complete:
        say(f"sweep[{mode}|{interaction}]: all {total} planned units "
            f"already resolved ({len(replay_successes)} recorded, "
            f"{len(anchored_tombstones)} tombstoned) — resuming WITHOUT provider "
            "contact")
        for row in replay_successes.values():
            cond = result._condition((row["model"], row["scenario"]))
            result.skipped_resumed += 1
            result.resumed[cond] += 1
            result.surviving[cond] += 1
        for row in anchored_tombstones.values():
            # Only the exact planned, uniquely anchored subset used by the
            # completion predicate is eligible for counting.
            result.tombstoned_resumed += 1
            model = row.get("model")
            scenario_name = row.get("scenario")
            kind = row.get("failure_kind", "other")
            cond = result._condition((model, scenario_name))
            result.dropouts[cond][kind] += 1
            result.execution_log.append(
                {"execution_index": len(result.execution_log),
                 "model": model, "scenario": scenario_name,
                 "scenario_seed": row.get("scenario_seed"),
                 "sampler_seed": row.get("sampler_seed"),
                 "status": "failed_tombstoned", "failure_kind": kind})
        if max_surviving_delta is not None:
            result.check_condition_balance(max_surviving_delta)
        return result

    # ---- ATOMIC fleet preflight (audit blocker, cycle-2): after the Round 4
    # terminal-ledger gate, probe and validate the digest of EVERY configured
    # model before scenario execution or terminal evidence writes. A mismatch
    # anywhere in the fleet still refuses the whole sweep before generation.
    probes = {}
    for model in spec["models"]:
        if _deadline_hit():
            raise SweepAborted("wall-clock deadline exceeded during preflight "
                               f"before model {model!r}")
        probe = OllamaAgent(model)
        if probe.digest_status != "ok":
            raise SweepAborted(
                f"{model}: digest could not be pinned (endpoint unreachable "
                "or model absent) — refusing to run an unpinned regime")
        if expected_digests is not None:
            want = expected_digests.get(model)
            if want and norm_digest(probe.model_digest) != norm_digest(want):
                raise SweepAborted(
                    f"{model}: served digest {probe.model_digest[:20]} != "
                    f"frozen digest {str(want)[:20]} — a repulled model is a "
                    "NEW regime; refusing to run against the frozen design")
        probe.configure_sampling(sampling, sampler_seeds[0])
        probe.resolve_effective_config()
        probes[model] = probe
        result.digests[model] = probe.model_digest

    # Resolve every expected model/scenario regime before execution or terminal
    # writes. Provider-free completion already admitted only uniquely anchored
    # tombstones; on the normal path the live preflight identity is the
    # authority, so a planned-coordinate tombstone from any other regime is
    # refused rather than silently ignored or re-rolled.
    contexts = {}
    for model in spec["models"]:
        probe = probes[model]
        for scenario_name in scenarios:
            path = os.path.join(config_dir, f"{scenario_name}.yaml")
            scen = load_scenario(path)
            bc = build_behavioral_config(
                scen.scenario_id, scen.behavioral_hash(), probe.spec_dict(),
                arbitration, ARBITRATION_VERSION,
                validate_sampling(sampling, sampler_seeds[0]),
                interaction_mode=interaction,
                history_template_version=HISTORY_TEMPLATE_VERSION,
                history_template_hash=HISTORY_TEMPLATE_HASH)
            regime_id, _ = regime_hashes(bc)
            contexts[(model, scenario_name)] = (path, regime_id)

    mismatched_tombstones = []
    for row in initial_tombstones.values():
        context_key = (row["model"], row["scenario"])
        expected_regime = contexts[context_key][1]
        if row["regime_id"] != expected_regime:
            mismatched_tombstones.append(
                (_row_coord(row), row["regime_id"], expected_regime))
    if mismatched_tombstones:
        coord, got, want = mismatched_tombstones[0]
        raise SweepAborted(
            f"resume tombstone for planned coordinate {coord!r} carries "
            f"regime {got!r}, not the preflight-validated regime {want!r}; "
            "mismatched terminal evidence is refused before execution or writes")

    # Only now that both terminal ledgers, the entire fleet, and every durable
    # failure regime are validated do we create evidence roots. The validated
    # initial snapshots are copied into local working state and never reloaded.
    os.makedirs(os.path.dirname(manifest_path) or ".", exist_ok=True)
    os.makedirs(out_root, exist_ok=True)
    done = dict(initial_done)
    tombstoned = (dict(initial_tombstones)
                  if retries_per_unit == 0 else {})
    tomb_path = _tombstone_path(manifest_path)

    def _write_tombstone(row: dict) -> None:
        with open(tomb_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
            fh.flush()

    total = len(spec["models"]) * len(scenarios) * len(seeds) * len(sampler_seeds)
    say(f"sweep[{mode}|{interaction}]: {len(spec['models'])} models x "
        f"{len(scenarios)} scenarios x {len(seeds)} scenario-seeds x "
        f"{len(sampler_seeds)} sampler-seeds = {total} runs "
        f"({len(done)} already done)")

    with open(manifest_path, "a", encoding="utf-8") as manifest:
        for model in spec["models"]:
            probe = probes[model]
            say(f"== {model}  digest={probe.model_digest[:20]}  "
                f"family={probe.model_family}  host={probe.host}  "
                f"backend={probe.backend_version}  mode={mode}")
            for scenario_name, scenario_seed, sampler_seed in order:
                path, regime_id = contexts[(model, scenario_name)]
                cond = result._condition((model, scenario_name))
                unit_key = (regime_id, scenario_seed, sampler_seed)
                if unit_key in done:
                    result.skipped_resumed += 1
                    # already-recorded evidence still counts as a survivor of
                    # its condition, otherwise a resumed pack looks unbalanced
                    result.resumed[cond] += 1
                    result.surviving[cond] += 1
                    continue
                if retries_per_unit == 0 and unit_key in tombstoned:
                    # audit b-002 finding 1: a durable prior failure. retries_per
                    # _unit=0 forbids a re-roll, so this cell is NOT attempted
                    # again — its typed failure is re-registered as the same
                    # dropout it was, and no provider is contacted.
                    kind = tombstoned[unit_key].get("failure_kind", "other")
                    result.dropouts[cond][kind] += 1
                    result.tombstoned_resumed += 1
                    result.execution_log.append(
                        {"execution_index": len(result.execution_log),
                         "model": model, "scenario": scenario_name,
                         "scenario_seed": scenario_seed,
                         "sampler_seed": sampler_seed,
                         "status": "failed_tombstoned", "failure_kind": kind})
                    continue
                if _deadline_hit():
                    raise SweepAborted(
                        "wall-clock deadline exceeded mid-sweep "
                        f"({result.rows_written} rows written)")
                execution_index = len(result.execution_log)
                result.attempted[cond] += 1
                try:
                    r = run_scenario(
                        path, f"llm:ollama:{model}", scenario_seed,
                        out_root=out_root, arbitration=arbitration,
                        sampling=sampling, sampler_seed=sampler_seed,
                        interaction_mode=interaction)
                except Exception as e:
                    kind = classify_failure(e)
                    result.dropouts[cond][kind] += 1
                    result.execution_log.append(
                        {"execution_index": execution_index, "model": model,
                         "scenario": scenario_name,
                         "scenario_seed": scenario_seed,
                         "sampler_seed": sampler_seed,
                         "status": "failed", "failure_kind": kind})
                    result.errors.append(
                        (scenario_name, scenario_seed, sampler_seed,
                         f"{e.__class__.__name__}: {e}"))
                    if retries_per_unit == 0:
                        if unit_key in done:
                            raise SweepAborted(
                                f"refusing failure write for {unit_key!r}: the "
                                "working state already contains a success")
                        # audit b-002 finding 1: persist the typed failure so a
                        # resume can never re-roll this unit into a success.
                        _write_tombstone({
                            "regime_id": regime_id, "model": model,
                            "scenario": scenario_name,
                            "scenario_seed": scenario_seed,
                            "sampler_seed": sampler_seed,
                            "failure_kind": kind,
                            "error": f"{e.__class__.__name__}: {e}",
                            "recorded_utc": time.strftime(
                                "%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                        tombstoned[unit_key] = {"failure_kind": kind}
                        result.tombstones_written += 1
                    say(f"  !! {scenario_name} s{scenario_seed} "
                        f"k{sampler_seed}: {e.__class__.__name__}: {e}")
                    continue
                if r.run.comparison_regime_id != regime_id:
                    raise SweepAborted(
                        f"regime drift mid-sweep for "
                        f"{model}/{scenario_name} — digest or config "
                        "changed; the frozen regime is void")
                if unit_key in tombstoned:
                    raise SweepAborted(
                        f"refusing success write for {unit_key!r}: the working "
                        "state already contains a durable failure")
                row = {"regime_id": r.run.comparison_regime_id,
                       "model": model, "scenario": scenario_name,
                       "scenario_seed": scenario_seed,
                       "sampler_seed": sampler_seed,
                       "variant_id": r.run.variant_id,
                       "temperature": r.run.sampling.get("temperature", 0),
                       "sampling_mode": r.run.sampling["mode"],
                       "digest": r.run.agent_config.get("model_digest", ""),
                       "scenario_hash": r.run.scenario_hash,
                       "arbitration": arbitration,
                       "run_id": r.run_id,
                       "dir": os.path.basename(r.run_dir),
                       "reportable": r.run.reportable,
                       "stochastic_reportable": r.run.stochastic_reportable,
                       "interaction_mode": r.run.interaction_mode,
                       "path": r.final_actions}
                if record_execution_index:
                    # opt-in only: the row is otherwise byte-identical to what
                    # every previous sweep wrote, so Phase-1 evidence and its
                    # manifests regenerate unchanged
                    row["execution_index"] = execution_index
                    row["execution_order"] = execution_order
                assert set(REQUIRED_ROW_FIELDS) <= set(row), \
                    sorted(set(REQUIRED_ROW_FIELDS) - set(row))
                manifest.write(json.dumps(row) + "\n")
                manifest.flush()
                done[unit_key] = row
                result.rows_written += 1
                result.surviving[cond] += 1
                result.execution_log.append(
                    {"execution_index": execution_index, "model": model,
                     "scenario": scenario_name, "scenario_seed": scenario_seed,
                     "sampler_seed": sampler_seed,
                     "status": "ok", "run_id": r.run_id})
                result.run_dirs.append(r.run_dir)
                result.regime_ids.add(r.run.comparison_regime_id)
                k = f" k{sampler_seed}" if sampler_seed is not None else ""
                say(f"  [{result.rows_written + len(done)}/{total}] "
                    f"{scenario_name} s{scenario_seed}{k}: "
                    f"{' -> '.join(r.final_actions)}")
    # Completion/balance uses the combined initial + current-call working state,
    # never a stale initial snapshot or a mid-call reload.
    working_both = set(done) & set(tombstoned)
    if working_both:
        raise SweepAborted(
            f"working terminal state became contradictory for "
            f"{sorted(working_both)[0]!r}")
    # Fail closed last, after every failure is recorded: the refusal is a
    # verdict on an already-complete evidence set, never a reason to discard it.
    if max_surviving_delta is not None:
        result.check_condition_balance(max_surviving_delta)
    return result

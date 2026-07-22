"""M8 Phase-2 result package — one self-verifying artifact that closes over a
completed, replay-attested, analyzed pack.

The package is INDEPENDENTLY RECONSTRUCTIBLE: every referenced artifact
(manifest, replay attestation, order report, per-run evidence files) is
identified by sha256, the frozen design is identified by its registry
design_hash, and the package body carries a content sha256 over itself so any
post-hoc edit — including to the embedded report copy — is detectable without
consulting anything outside the file.

Fail-closed refusals (SchemaError):
  - the report carries no verdict (a refusal-shaped report is an inconclusive
    result and is never packaged as one);
  - the replay attestation is missing (unattested evidence is not evidence);
  - the attestation's manifest_sha256 disagrees with the manifest on disk
    (the attestation must bind to THIS manifest, not some manifest);
  - the success/tombstone snapshot is contradictory, malformed, outside the
    frozen grid, or has changed since replay (authenticated absence included);
  - the registry design_hash does not reconstruct (tampered frozen design).

The git commit is RECORDED, not hashed: it names where the code stood, but the
package's integrity rests on the artifact hashes, never on the repo state.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

from .schema import SchemaError, canonical_json

PACKAGE_VERSION = "2"
PACKAGE_NAME = "result_package.json"
ATTESTATION_NAME = "replay_attestation.json"
# every key a per-run attestation record must carry into the package
_RUN_HASH_KEYS = ("run_dir", "replay_ok", "run_json_sha256",
                  "decisions_sha256", "captures_sha256")


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_body(body: dict) -> str:
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _git_commit() -> str | None:
    """Recorded, not hashed — best-effort; a missing git is None, never a lie."""
    try:
        p = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                           text=True, timeout=10)
    except Exception:
        return None
    return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else None


_CONDITION_LABELS = ("A", "B", "C")


def _recompute_order_report(experiment_id: str, registry_path: str,
                            manifest_path: str, out_root: str, config_dir: str,
                            attestation: dict,
                            terminal_snapshot: tuple[dict, dict] | None = None
                            ) -> dict:
    """Independently RE-DERIVE the order report from the bound raw evidence and
    the frozen VERIFIED design (d-003 finding 2). Returns the report dict, or
    raises SchemaError if the evidence does not admit a verdict — in which case
    a caller-supplied verdict-bearing report is, by construction, not derivable
    from this evidence and the package must refuse. The design is loaded through
    `load_verified_bundle`, so a self-rehashed or profile-weakened registry
    cannot drive the recomputation, and retries_per_unit is taken from the
    frozen design (0) so duplicate/conflicting observations dedup-or-refuse
    exactly as the production analysis path does."""
    from . import metrics as metrics_mod
    from . import sweep
    from .registry import load_verified_bundle
    from .scenario import load_scenario

    vb = load_verified_bundle(registry_path, experiment_id)
    scenarios = list(vb.planned_design.get("scenarios") or [])
    if len(scenarios) != len(_CONDITION_LABELS):
        raise SchemaError(
            f"{experiment_id}: planned_design.scenarios has {len(scenarios)} "
            f"entries, expected {len(_CONDITION_LABELS)} (A/B/C)")
    conditions = dict(zip(_CONDITION_LABELS, scenarios))
    retries_per_unit = vb.retries_per_unit
    if isinstance(retries_per_unit, bool) or retries_per_unit != 0:
        raise SchemaError(
            f"{experiment_id}: frozen retries_per_unit={retries_per_unit!r} "
            "!= 0 — cannot recompute the package report under the frozen "
            "one-effective-unit contract")

    if terminal_snapshot is None:
        terminal_snapshot = sweep.terminal_ledgers_load(
            manifest_path, out_root, planned_design=vb.planned_design,
            require_tombstone_regime_anchors=True)
    rows, _tombstones = terminal_snapshot
    sweep.validate_terminal_ledger_attestation(attestation, manifest_path)
    if not rows:
        raise SchemaError(f"{experiment_id}: manifest resolves to zero rows")
    run_dirs = sorted(os.path.join(out_root, rec["dir"])
                      for rec in rows.values())
    surviving_counts: dict = {}
    for rec in rows.values():
        surviving_counts[rec["scenario"]] = \
            surviving_counts.get(rec["scenario"], 0) + 1

    terminal_ids = set()
    for scen_id in conditions.values():
        scen = load_scenario(os.path.join(config_dir, f"{scen_id}.yaml"))
        decisions = [dp.dp_id for dp in scen.decision_points
                     if not dp.is_exposure()]
        if len(decisions) != 1:
            raise SchemaError(
                f"{experiment_id}: {scen_id} has {len(decisions)} decision-"
                "kind points; exactly one terminal probe is required")
        terminal_ids.add(decisions[0])
    if len(terminal_ids) != 1:
        raise SchemaError(
            f"{experiment_id}: triplet disagrees on the terminal probe id "
            f"{sorted(terminal_ids)}")

    # d-006: thread the FROZEN matched-unit grid from the verified design so the
    # recomputation enforces the pre-registered unit count and (variant,
    # scenario_seed) group axis. An extra/unfrozen group cannot scale "required"
    # to match here any more than it can on the CLI analysis path, so a package
    # built over an unfrozen-group pack refuses at recomputation.
    frozen_grid = metrics_mod.frozen_grid_from_design(vb.planned_design)
    return metrics_mod.order_sensitivity_report(
        run_dirs, conditions, admissibility_policy=vb.admissibility_policy,
        thresholds=vb.thresholds, replay_attestation=attestation,
        terminal_dp_id=terminal_ids.pop(),
        surviving_counts=surviving_counts, retries_per_unit=retries_per_unit,
        frozen_grid=frozen_grid)


def _build_result_package_locked(
        experiment_id: str, manifest_path: str, out_root: str,
        registry_path: str, report_path: str, extra: dict,
        config_dir: str = "configs/scenarios") -> str:
    """Assemble and write <out_root>/result_package.json; returns its path.

    For a POLICY_REQUIRED experiment the supplied report is NOT trusted: the
    verdict is RE-DERIVED from the bound manifest/attestation evidence and the
    frozen verified design, and must match the supplied report canonically
    (d-003 finding 2). A caller-authored or stale verdict cannot be packaged."""
    from . import sweep
    from .registry import _find_entry, POLICY_REQUIRED_EXPERIMENTS
    from .registry import design_hash as compute_design_hash

    if not isinstance(extra, dict):
        raise SchemaError("extra must be a dict (suite receipt fields etc.), "
                          f"got {type(extra).__name__}")

    # ---- the report: must exist AND carry a verdict for every agent --------
    if not os.path.isfile(report_path):
        raise SchemaError(f"report not found: {report_path}")
    report_sha = _sha256_file(report_path)
    with open(report_path, encoding="utf-8") as fh:
        report = json.load(fh)
    per_agent = report.get("per_agent") or {}
    verdicts = {aid: (a or {}).get("verdict") for aid, a in per_agent.items()}
    if not verdicts or any(v is None for v in verdicts.values()):
        raise SchemaError(
            "report carries no verdict (refusal-shaped or empty per_agent) — "
            "a refusal is an inconclusive result and is never packaged as one")
    order_report_version = report.get("order_report_version")
    if not order_report_version:
        raise SchemaError("report lacks order_report_version — an unversioned "
                          "verdict is not traceable to the rule that made it")

    # ---- the replay attestation: mandatory, and bound to THIS manifest -----
    att_path = os.path.join(out_root, ATTESTATION_NAME)
    if not os.path.isfile(att_path):
        raise SchemaError(f"replay attestation missing: {att_path} — "
                          "unattested evidence is not packaged (prereg clause 0)")
    att_sha = _sha256_file(att_path)
    with open(att_path, encoding="utf-8") as fh:
        attestation = json.load(fh)
    if not os.path.isfile(manifest_path):
        raise SchemaError(f"manifest not found: {manifest_path}")
    manifest_sha = _sha256_file(manifest_path)
    att_manifest_sha = attestation.get("manifest_sha256")
    if att_manifest_sha != manifest_sha:
        raise SchemaError(
            f"replay attestation binds manifest_sha256 "
            f"{str(att_manifest_sha)[:16]}… but the manifest at "
            f"{manifest_path} hashes to {manifest_sha[:16]}… — the "
            "attestation does not attest THIS manifest")
    runs = attestation.get("runs")
    if not isinstance(runs, dict) or not runs:
        raise SchemaError("replay attestation carries no per-run records")
    run_evidence = {}
    for run_id, rec in sorted(runs.items()):
        missing = [k for k in _RUN_HASH_KEYS if k not in (rec or {})]
        if missing:
            raise SchemaError(f"attestation run {run_id!r} is missing "
                              f"{missing} — partial evidence hashes cannot "
                              "close a package")
        if rec["replay_ok"] is not True:
            raise SchemaError(f"attestation run {run_id!r} has "
                              f"replay_ok={rec['replay_ok']!r} — a failed "
                              "replay never enters a result package")
        run_evidence[run_id] = {k: rec[k] for k in _RUN_HASH_KEYS}

    # ---- the frozen design: hash must reconstruct --------------------------
    entry = _find_entry(registry_path, experiment_id)
    pd = entry.get("planned_design")
    if not isinstance(pd, dict):
        raise SchemaError(f"{experiment_id}: registry entry has no "
                          "planned_design")
    want = compute_design_hash(pd)
    if entry.get("design_hash") != want:
        raise SchemaError(
            f"{experiment_id}: design_hash "
            f"{str(entry.get('design_hash'))[:16]}… != recomputed "
            f"{want[:16]}… — the frozen design was mutated")

    terminal_snapshot = sweep.terminal_ledgers_load(
        manifest_path, out_root, planned_design=pd,
        require_tombstone_regime_anchors=True)
    tombstone_identity = sweep.validate_terminal_ledger_attestation(
        attestation, manifest_path)

    # d-003 finding 2: for a policy-required experiment the packaged verdict is
    # RE-DERIVED from the bound evidence, never trusted from the caller's report.
    # Recompute the order report from the current run evidence + the frozen
    # VERIFIED design and require canonical equality with the supplied report.
    # This defeats a forged verdict, a stale report, an all-fallback pack whose
    # real recomputation refuses, and a report bound to different runs.
    if experiment_id in POLICY_REQUIRED_EXPERIMENTS:
        try:
            recomputed = _recompute_order_report(
                experiment_id, registry_path, manifest_path, out_root,
                config_dir, attestation,
                terminal_snapshot=terminal_snapshot)
        except SchemaError as e:
            raise SchemaError(
                f"{experiment_id}: the supplied report carries a verdict but an "
                f"independent recomputation from the bound evidence refuses "
                f"({e}) — a caller-authored verdict that the evidence does not "
                "produce is never packaged")
        if canonical_json(recomputed) != canonical_json(report):
            raise SchemaError(
                f"{experiment_id}: the supplied report does not match an "
                "independent recomputation from the bound run evidence and the "
                "frozen verified design — the package binds a DERIVED verdict, "
                "never a caller-authored, stale, or mis-bound one")

    body = {
        "package_version": PACKAGE_VERSION,
        "experiment_id": experiment_id,
        "design_hash": entry["design_hash"],
        "order_report_version": order_report_version,
        "verdicts": verdicts,
        "models": list(pd.get("models") or []),
        "model_digests": dict(pd.get("model_digests") or {}),
        "manifest": {"path": manifest_path, "sha256": manifest_sha},
        "tombstone_ledger": {
            "path": manifest_path + ".tombstones.jsonl",
            **tombstone_identity,
        },
        "replay_attestation": {
            "path": att_path,
            "sha256": att_sha,
            "attestation_version": attestation.get("attestation_version"),
            "verified_utc": attestation.get("verified_utc"),
            "manifest_sha256": att_manifest_sha,
            "tombstone_ledger": tombstone_identity,
        },
        "report": {"path": report_path, "sha256": report_sha, "body": report},
        "runs": run_evidence,
        # recorded, NOT hashed: names where the code stood
        "git_commit": _git_commit(),
        "extra": dict(extra),
    }
    body["package_sha256"] = _sha256_body(body)
    out_path = os.path.join(out_root, PACKAGE_NAME)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(body) + "\n")
    return out_path


def build_result_package(experiment_id: str, manifest_path: str, out_root: str,
                         registry_path: str, report_path: str,
                         extra: dict, config_dir: str = "configs/scenarios"
                         ) -> str:
    """Build from one stable, manifest-locked terminal-ledger snapshot."""
    from . import sweep
    try:
        with sweep._manifest_advisory_lock(manifest_path) as canonical_manifest:
            return _build_result_package_locked(
                experiment_id, canonical_manifest, out_root, registry_path,
                report_path, extra, config_dir=config_dir)
    except sweep.SweepAborted as exc:
        raise SchemaError(f"result-package terminal lock refused ({exc})") \
            from exc


def _verify_result_package_locked(
        package_path: str, *, expected_manifest_path: str | None = None
        ) -> dict:
    """Re-verify a package from disk. Returns the parsed package on success;
    raises SchemaError on ANY mismatch — body tamper, referenced-artifact
    tamper, or embedded-report drift. `git_commit` is deliberately NOT
    verified (recorded, not hashed)."""
    if not os.path.isfile(package_path):
        raise SchemaError(f"package not found: {package_path}")
    with open(package_path, encoding="utf-8") as fh:
        pkg = json.load(fh)
    locked_manifest_path = (pkg.get("manifest") or {}).get("path")
    if (expected_manifest_path is not None
            and locked_manifest_path != expected_manifest_path):
        raise SchemaError(
            "package manifest reference changed while verification acquired "
            "terminal-ledger ownership")
    if pkg.get("package_version") != PACKAGE_VERSION:
        raise SchemaError(
            f"package_version {pkg.get('package_version')!r} != "
            f"{PACKAGE_VERSION!r}")
    claimed = pkg.get("package_sha256")
    body = {k: v for k, v in pkg.items() if k != "package_sha256"}
    got = _sha256_body(body)
    if claimed != got:
        raise SchemaError(f"package content hash mismatch: recorded "
                          f"{str(claimed)[:16]}… != recomputed {got[:16]}… — "
                          "the package body was modified after it was written")
    for label in ("manifest", "replay_attestation", "report"):
        ref = pkg.get(label) or {}
        path, want = ref.get("path"), ref.get("sha256")
        if not path or not want:
            raise SchemaError(f"package {label} reference is incomplete")
        if not os.path.isfile(path):
            raise SchemaError(f"package {label} artifact missing: {path}")
        have = _sha256_file(path)
        if have != want:
            raise SchemaError(
                f"package {label} artifact tampered: {path} hashes to "
                f"{have[:16]}… but the package recorded {want[:16]}…")
    from . import sweep
    tombstone_ref = pkg.get("tombstone_ledger")
    if not isinstance(tombstone_ref, dict):
        raise SchemaError("package tombstone_ledger reference is missing")
    expected_tombstone_path = pkg["manifest"]["path"] + ".tombstones.jsonl"
    if tombstone_ref.get("path") != expected_tombstone_path:
        raise SchemaError(
            "package tombstone_ledger path is not adjacent to its manifest")
    current_identity = sweep.tombstone_ledger_identity(
        pkg["manifest"]["path"])
    recorded_identity = {
        "state": tombstone_ref.get("state"),
        "sha256": tombstone_ref.get("sha256"),
    }
    if recorded_identity != current_identity:
        raise SchemaError(
            "package tombstone ledger was created, removed, or modified "
            "after packaging")
    with open(pkg["replay_attestation"]["path"], encoding="utf-8") as fh:
        replay_attestation = json.load(fh)
    if replay_attestation.get("tombstone_ledger") != current_identity:
        raise SchemaError(
            "packaged replay attestation does not bind the current "
            "tombstone ledger")
    return pkg


def verify_result_package(package_path: str) -> dict:
    """Verify package and both terminal ledgers under manifest ownership."""
    if not os.path.isfile(package_path):
        raise SchemaError(f"package not found: {package_path}")
    with open(package_path, encoding="utf-8") as fh:
        preview = json.load(fh)
    manifest_path = (preview.get("manifest") or {}).get("path")
    if not manifest_path:
        raise SchemaError("package manifest reference is incomplete")
    from . import sweep
    try:
        with sweep._manifest_advisory_lock(manifest_path) as canonical_manifest:
            return _verify_result_package_locked(
                package_path, expected_manifest_path=canonical_manifest)
    except sweep.SweepAborted as exc:
        raise SchemaError(f"result-package verification lock refused ({exc})") \
            from exc

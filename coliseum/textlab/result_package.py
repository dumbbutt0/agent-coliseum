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

PACKAGE_VERSION = "1"
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


def build_result_package(experiment_id: str, manifest_path: str, out_root: str,
                         registry_path: str, report_path: str,
                         extra: dict) -> str:
    """Assemble and write <out_root>/result_package.json; returns its path."""
    from .registry import _find_entry
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

    body = {
        "package_version": PACKAGE_VERSION,
        "experiment_id": experiment_id,
        "design_hash": entry["design_hash"],
        "order_report_version": order_report_version,
        "verdicts": verdicts,
        "models": list(pd.get("models") or []),
        "model_digests": dict(pd.get("model_digests") or {}),
        "manifest": {"path": manifest_path, "sha256": manifest_sha},
        "replay_attestation": {
            "path": att_path,
            "sha256": att_sha,
            "attestation_version": attestation.get("attestation_version"),
            "verified_utc": attestation.get("verified_utc"),
            "manifest_sha256": att_manifest_sha,
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


def verify_result_package(package_path: str) -> dict:
    """Re-verify a package from disk. Returns the parsed package on success;
    raises SchemaError on ANY mismatch — body tamper, referenced-artifact
    tamper, or embedded-report drift. `git_commit` is deliberately NOT
    verified (recorded, not hashed)."""
    if not os.path.isfile(package_path):
        raise SchemaError(f"package not found: {package_path}")
    with open(package_path, encoding="utf-8") as fh:
        pkg = json.load(fh)
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
    return pkg

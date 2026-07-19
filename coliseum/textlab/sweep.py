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


class SweepAborted(Exception):
    """A precondition failed mid-sweep — regime drift, a repulled digest, or
    the wall-clock deadline. Recorded and surfaced, never worked around."""


class SweepUnbalanced(SweepAborted):
    """Per-condition surviving counts differ by more than the caller's bound.
    Differential dropout is observationally identical to a real effect (the
    survivors of the lossy condition are a biased subsample), so an unbalanced
    pack is refused as unanalyzable rather than reported with a caveat."""


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


def verify_pack_replay(manifest_path: str, out_root: str, config_dir: str) -> dict:
    """Provider-free replay attestation for a WHOLE pack (M8 Phase-2 audit
    c-001, finding 0 — generator side).

    Runs verify_run_replay on EVERY manifest row and, only if every run
    replays, writes <out_root>/replay_attestation.json binding each run's
    exact evidence bytes (run.json / decisions.jsonl / captures.jsonl sha256)
    and the manifest bytes to the replay result. The frozen analysis path
    authenticates this receipt instead of trusting mutable admission booleans.

    FAIL CLOSED: any replay failure (or a missing/empty manifest) raises and
    writes NO attestation — not even a partial one — and a stale attestation
    from a previous pass is removed before verification starts, so a failing
    pack can never sit next to a valid-looking receipt. The attestation is
    written atomically (temp file + rename) only after the last row verifies.

    Returns the attestation dict exactly as written."""
    if not os.path.exists(manifest_path):
        raise SweepAborted(f"verify_pack_replay: no manifest at {manifest_path}")
    attestation_path = os.path.join(out_root, "replay_attestation.json")
    if os.path.exists(attestation_path):
        os.remove(attestation_path)       # a receipt must postdate its verification
    rows = manifest_load(manifest_path, out_root)
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
        "attestation_version": "1",
        "verified_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "manifest_sha256": _file_sha256(manifest_path),
        "runs": runs,
    }
    tmp_path = attestation_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(attestation, fh, indent=2)
        fh.write("\n")
    os.replace(tmp_path, attestation_path)
    return attestation


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
                    f"NOT analyzable. Per condition: {detail}")
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
              max_surviving_delta: int | None = None) -> SweepResult:
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
    Failed runs are still recorded in `result.errors` and never erased."""
    say = progress or (lambda *_a, **_k: None)
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

    # ---- ATOMIC fleet preflight (audit blocker, cycle-2): probe and validate
    # the digest of EVERY configured model FIRST — before any filesystem touch
    # (no out_root/manifest dir creation, no manifest read) and before any
    # compute. A mismatched/unreachable model anywhere in the fleet refuses the
    # whole sweep here, so a repulled LATER model can never be masked by an
    # earlier model's runs OR by a malformed pre-existing manifest.
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

    # only now that the ENTIRE fleet is pinned+validated do we touch the
    # filesystem: create the evidence root and read any resumable manifest
    os.makedirs(os.path.dirname(manifest_path) or ".", exist_ok=True)
    os.makedirs(out_root, exist_ok=True)
    done = manifest_load(manifest_path, out_root)

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
            # per-scenario context is resolved LAZILY and cached: under
            # "blocked" that reproduces exactly when each scenario file was
            # first read today, and under "interleaved" the three conditions
            # are each loaded once at the first unit that needs them
            ctx = {}

            def _ctx(scenario_name):
                if scenario_name not in ctx:
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
                    ctx[scenario_name] = (path, regime_id)
                return ctx[scenario_name]

            for scenario_name, scenario_seed, sampler_seed in order:
                path, regime_id = _ctx(scenario_name)
                cond = result._condition((model, scenario_name))
                if (regime_id, scenario_seed, sampler_seed) in done:
                    result.skipped_resumed += 1
                    # already-recorded evidence still counts as a survivor of
                    # its condition, otherwise a resumed pack looks unbalanced
                    result.resumed[cond] += 1
                    result.surviving[cond] += 1
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
                    say(f"  !! {scenario_name} s{scenario_seed} "
                        f"k{sampler_seed}: {e.__class__.__name__}: {e}")
                    continue
                if r.run.comparison_regime_id != regime_id:
                    raise SweepAborted(
                        f"regime drift mid-sweep for "
                        f"{model}/{scenario_name} — digest or config "
                        "changed; the frozen regime is void")
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
    # fail-closed LAST, after every failure is recorded: the refusal is a
    # verdict on an already-complete evidence set, never a reason to discard it
    if max_surviving_delta is not None:
        result.check_condition_balance(max_surviving_delta)
    return result

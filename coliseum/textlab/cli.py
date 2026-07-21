"""textlab CLI — thin over runner/metrics/graph_export.

    python3 -m coliseum.textlab.cli run     --scenario corrupt_king --agent scripted:obedient --seed 42
    python3 -m coliseum.textlab.cli replay  <run_id>          # the determinism gate as a command
    python3 -m coliseum.textlab.cli metrics <run_id> [...]    # per-run reports + aggregate
    python3 -m coliseum.textlab.cli graph   <run_id> [...]    # decision graphs (JSON + DOT)
    python3 -m coliseum.textlab.cli compare                   # aggregate cells side by side
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from .graph_export import write_graphs
from .metrics import aggregate, write_aggregate, write_run_metrics
from .runner import run_scenario
from .schema import canonical_json


def _run_dir(run_id: str, out_root: str) -> str:
    d = os.path.join(out_root, run_id)
    if not os.path.isdir(d):
        sys.exit(f"no such run: {d}")
    return d


def _all_run_dirs(out_root: str) -> list:
    if not os.path.isdir(out_root):
        return []
    return [os.path.join(out_root, d) for d in sorted(os.listdir(out_root))
            if os.path.isfile(os.path.join(out_root, d, "run.json"))]


def cmd_run(args):
    path = os.path.join(args.config_dir, f"{args.scenario}.yaml")
    sampling = None
    if args.temperature and args.temperature > 0:
        sampling = {"mode": "stochastic", "temperature": args.temperature}
    result = run_scenario(path, args.agent, args.seed, out_root=args.out_root,
                          arbitration=args.arbitration,
                          sampling=sampling, sampler_seed=args.sampler_seed,
                          interaction_mode=args.interaction)
    print(f"run_id : {result.run_id}")
    if args.interaction != "independent_vignettes":
        print(f"mode   : {args.interaction}")
    print(f"path   : {' -> '.join(result.final_actions)}")
    print(f"log    : {os.path.join(result.run_dir, 'decisions.jsonl')}")
    if sampling:
        print(f"stochastic_reportable: {result.run.stochastic_reportable} "
              f"{result.run.stochastic_exclusion_reasons or ''}")


def cmd_replay(args):
    """Re-run from run.json config into a temp dir and byte-compare — the gate.
    Scripted runs re-execute live; LLM runs replay from their captured raw outputs
    (the two determinism tiers — live-API determinism is never claimed). The
    verification itself lives in coliseum.textlab.sweep.verify_run_replay, shared
    with the audited ollama_local driver so both check identical bytes."""
    from coliseum.textlab.sweep import verify_run_replay
    run_dir = _run_dir(args.run_id, args.out_root)
    run = json.load(open(os.path.join(run_dir, "run.json"), encoding="utf-8"))
    ok, detail = verify_run_replay(run_dir, args.config_dir)
    if not ok:
        sys.exit(f"REPLAY FAILED: {run['run_id']}: {detail}")
    is_llm = run["agent_id"].startswith("llm:")
    tier = "replayed from captured outputs" if is_llm else "re-executed live"
    print(f"byte-identical: {run['run_id']} (decisions.jsonl, {tier})")


def cmd_metrics(args):
    dirs = ([_run_dir(r, args.out_root) for r in args.run_ids]
            if args.run_ids else _all_run_dirs(args.out_root))
    if not dirs:
        sys.exit("no runs found")
    for d in dirs:
        print("wrote", write_run_metrics(d, args.derived_root))
    print("wrote", write_aggregate(dirs, args.derived_root, mode=args.mode,
                                   include_non_reportable=args.diagnostics,
                                   interaction_mode=args.interaction))


def cmd_graph(args):
    dirs = ([_run_dir(r, args.out_root) for r in args.run_ids]
            if args.run_ids else _all_run_dirs(args.out_root))
    if not dirs:
        sys.exit("no runs found")
    for p in write_graphs(dirs, args.graphs_root):
        print("wrote", p)


def cmd_compare(args):
    dirs = _all_run_dirs(args.out_root)
    if not dirs:
        sys.exit("no runs found")
    agg = aggregate(dirs, mode=args.mode, include_non_reportable=args.diagnostics,
                    interaction_mode=args.interaction)
    print(f"mode: {args.mode} | interaction: {args.interaction}")
    if args.diagnostics:
        print("!! DIAGNOSTICS MODE: non-admitted runs INCLUDED — not for claims !!\n")
    elif agg["excluded"]:
        reasons = {}
        for e in agg["excluded"]:
            for why in e["reasons"]:
                reasons[why] = reasons.get(why, 0) + 1
        print(f"(excluded {len(agg['excluded'])} runs: {reasons}; --diagnostics to include)\n")
    metric_names = sorted({m for c in agg["cells"].values() for m in c["metrics"]})
    header = ["cell (…|sampling|regime-prefix)", "eff_n/att"] + \
             [m.replace("_rate", "").replace("_", " ") for m in metric_names]
    rows = [header]
    for key, cell in agg["cells"].items():
        label = key + (" [reward-control]" if cell["persona_role"] == "reward_seeking_control" else "")
        c = cell["counts"]
        row = [label, f"{c['effective_n']}/{c['raw_attempt_n']}"]
        for m in metric_names:
            v = cell["metrics"].get(m, {}).get("value")
            row.append("-" if v is None else f"{v:.2f}")
        rows.append(row)
    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    for r in rows:
        print("  ".join(s.ljust(w) for s, w in zip(r, widths)))
    if args.mode == "full-grid":
        print("\ngrid (variant × sampler_seed -> evidence):")
        for key, cell in agg["cells"].items():
            for gkey, ids in cell.get("grid", {}).items():
                print(f"  {cell['scenario_id']}|{cell['agent_id']} {gkey}: {len(ids)} attempt(s)")
    if agg["faith_knob_sensitivity"]:
        print("\nfaith_knob_sensitivity (paired, d2-only; + = blind faith):")
        for agent, v in agg["faith_knob_sensitivity"].items():
            print(f"  {agent}: {v['value']:+.2f} (matched_pairs={v['matched_pairs']})")
    if agg["control_twin_delta"]:
        print("\ncontrol_twin_delta (paired, primary - control):")
        for pair, d in agg["control_twin_delta"].items():
            interesting = {k: v for k, v in d["deltas"].items() if v}
            un = (f", unmatched sampler seeds p:{d['unmatched_primary_sampler_seeds']}"
                  f"/c:{d['unmatched_control_sampler_seeds']}"
                  if d["unmatched_primary_sampler_seeds"] or d["unmatched_control_sampler_seeds"] else "")
            print(f"  {pair}: {interesting or 'no differences'} "
                  f"(pairs={d['matched_pairs']}{un})")


def _load_held_out(registry_path):
    """Held-out (scenarios, scenario_hashes) from the experiments registry, or (None, None)."""
    if not registry_path or not os.path.exists(registry_path):
        return None, None
    from .registry import load_experiments_registry
    raw = load_experiments_registry(registry_path)
    ho = raw.get("held_out", {}) if isinstance(raw, dict) else {}
    return ho.get("scenarios") or None, ho.get("scenario_hashes") or None


def cmd_dataset_export(args):
    """T0-A: emit a provenance-complete, non-pooled dataset descriptor + card from validated evidence,
    with an optional deterministic, dataset-version-bound group-aware partition (§8).
    Structural only — no normative labels, no training."""
    from .dataset_export import build_dataset, dataset_from_manifest, dataset_card
    from . import reports
    held_ids, held_hashes = _load_held_out(args.registry)
    common = dict(mode=args.mode, interaction_mode=args.interaction,
                  held_out_scenarios=held_ids, held_out_hashes=held_hashes,
                  verify=args.verify, config_dir=args.config_dir,
                  partition=args.partition,
                  registry_path=args.scenario_registry if args.partition else None,
                  training_admission=args.training_admission,
                  require_replay_for_admission=args.admission_require_replay)
    if args.manifest:
        desc = dataset_from_manifest(args.manifest, args.out_root, **common)
    else:
        dirs = _all_run_dirs(args.out_root)
        if not dirs:
            sys.exit("no runs found")
        desc = build_dataset(dirs, **common)
    os.makedirs(args.derived_root, exist_ok=True)
    desc_path = os.path.join(args.derived_root, "dataset.t0a.json")
    with open(desc_path, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(desc) + "\n")
    card_path = reports.write(dataset_card(desc), "dataset-card.t0a.md", args.repo_root)
    print("wrote", desc_path)
    print("wrote", card_path)
    print(f"effective_units {desc['effective_unit_count']} commitment {desc['dataset_commitment'][:16]}")


# --------------------------------------------------------------------------
# M8 Phase-2 operator surface (replay-pack / order-report / smoke-pack /
# result-package). Everything here is fail-closed: replay is MANDATORY before
# analysis (prereg clause 0), a smoke pack is never claim-bearing, and a typed
# SchemaError refusal exits nonzero WITHOUT writing a distances-bearing file.
#
# NOTE on imports: sweep.verify_pack_replay and the ORDER_REPORT_VERSION-4
# signature of metrics.order_sensitivity_report are Director-defined contracts
# implemented concurrently; they are imported LATE (inside the commands) so
# this module always imports, and a missing contract symbol surfaces as a
# typed refusal at invocation time, never as a broken CLI.

SMOKE_MARKER_NAME = "SMOKE_MARKER.json"
ATTESTATION_NAME = "replay_attestation.json"
# Canonical owner experiment authorization (smoke-authorization.v1). Live
# provider contact — and any filesystem mutation preparing one — is gated on a
# manifest carrying EXACTLY these bindings, each verified against the live
# registry and the candidate commit at invocation time. The non-claim-bearing
# smoke marker governs ANALYSIS refusal only; it never grants contact
# authority, so a design-audit approval (or no artifact at all) refuses
# before anything is written and before run_sweep is ever reached.
SMOKE_AUTHORIZATION_VERSION = "1"
SMOKE_AUTHORIZATION_KIND = "owner_experiment_execution"
SMOKE_AUTHORIZATION_FIELDS = (
    "authorization_version", "authorization_kind", "experiment_id",
    "design_hash", "candidate_commit", "model_digests", "run_count",
    "scale", "budget")
# Frozen m8 condition mapping (Director contract): labels A/B/C bind to the
# planned_design scenario list IN ORDER — dev, perm, sham.
_CONDITION_LABELS = ("A", "B", "C")


def _conditions_from_design(planned_design: dict) -> dict:
    scenarios = list(planned_design.get("scenarios") or [])
    if len(scenarios) != len(_CONDITION_LABELS):
        sys.exit(f"ORDER-REPORT REFUSED: planned_design.scenarios has "
                 f"{len(scenarios)} entries, expected exactly "
                 f"{len(_CONDITION_LABELS)} (A=dev, B=perm, C=sham)")
    return dict(zip(_CONDITION_LABELS, scenarios))


def cmd_replay_pack(args):
    """Provider-free replay of a whole evidence pack -> replay_attestation.json.
    Refuses (nonzero exit, no attestation) on ANY replay failure — a partially
    replayed pack is not evidence."""
    from . import sweep
    verify = getattr(sweep, "verify_pack_replay", None)
    if verify is None:
        sys.exit("REPLAY-PACK REFUSED: sweep.verify_pack_replay is not "
                 "available in this build (contract symbol missing)")
    try:
        verify(args.manifest, args.out_root, args.config_dir)
    except Exception as e:  # any failure is a refusal, never a partial file
        sys.exit(f"REPLAY-PACK REFUSED: {e.__class__.__name__}: {e}")
    att_path = os.path.join(args.out_root, ATTESTATION_NAME)
    if not os.path.isfile(att_path):
        sys.exit("REPLAY-PACK REFUSED: verify_pack_replay returned without "
                 f"writing {att_path}")
    with open(att_path, encoding="utf-8") as fh:
        att = json.load(fh)
    print(f"attestation : {att_path}")
    print(f"runs        : {len(att.get('runs', {}))} replay-verified")


def cmd_order_report(args):
    """Frozen ORDER_REPORT_VERSION-6 analysis over a completed pack.

    Order of refusals (each exits nonzero and writes NOTHING):
      1. smoke-marked out_root (a smoke pack is operational validation only);
      2. missing replay attestation (replay is mandatory before analysis);
      3. a typed SchemaError from the aggregator (admission / policy refusal)
         — the refusal text is printed verbatim and no distances-bearing file
         is ever written on that path."""
    from . import metrics as metrics_mod
    from . import sweep
    from .registry import (_frozen_design, load_admissibility_policy,
                           load_thresholds, load_verified_bundle,
                           POLICY_REQUIRED_EXPERIMENTS)
    from .schema import SchemaError

    # a-006 E-2: the operator docstring advertises a specific report contract; bind
    # it to the emitted version so a future bump cannot leave the doc stale.
    assert metrics_mod.ORDER_REPORT_VERSION == "6", (
        "cmd_order_report docstring advertises ORDER_REPORT_VERSION-6 but "
        f"metrics emits {metrics_mod.ORDER_REPORT_VERSION!r} — update both together")

    marker = os.path.join(args.out_root, SMOKE_MARKER_NAME)
    if os.path.exists(marker):
        sys.exit(f"ORDER-REPORT REFUSED: {marker} present — this pack is a "
                 "SMOKE pack (claim_bearing: false, operational validation "
                 "only) and may never be analyzed for a verdict")
    att_path = os.path.join(args.out_root, ATTESTATION_NAME)
    if not os.path.isfile(att_path):
        sys.exit(f"ORDER-REPORT REFUSED: no {ATTESTATION_NAME} under "
                 f"{args.out_root} — a provider-free replay attestation is "
                 "MANDATORY before analysis (prereg clause 0); run "
                 "`replay-pack` first")
    try:
        with open(att_path, encoding="utf-8") as fh:
            attestation = json.load(fh)
    except ValueError as e:
        sys.exit(f"ORDER-REPORT REFUSED: {att_path} is not valid JSON: {e}")

    rows = sweep.manifest_load(args.manifest, args.out_root)
    if not rows:
        sys.exit(f"ORDER-REPORT REFUSED: manifest {args.manifest} resolves "
                 "to zero validated rows")
    run_dirs = sorted(os.path.join(args.out_root, rec["dir"])
                      for rec in rows.values())
    # Per-scenario surviving counts, derived from the validated manifest rows
    # themselves: a dropped run is ABSENT from the manifest, so this is the
    # census the max_surviving_delta bound is charged against.
    surviving_counts: dict = {}
    for rec in rows.values():
        surviving_counts[rec["scenario"]] = \
            surviving_counts.get(rec["scenario"], 0) + 1

    # d-003 findings 0 & 1: for a policy-required experiment the analysis MUST
    # load a VERIFIED bundle (profile-checked, not design_hash-only) and MUST
    # source retries_per_unit from the frozen design. A caller-selected
    # --registry that self-rehashes a weakened design refuses here; and the
    # frozen zero-retry contract (deduplicate/refuse duplicate observations
    # rather than pool replicates) can no longer be omitted at this entrypoint.
    if args.experiment_id in POLICY_REQUIRED_EXPERIMENTS:
        try:
            vb = load_verified_bundle(args.registry, args.experiment_id)
        except SchemaError as e:
            sys.exit(f"ORDER-REPORT REFUSED: verified frozen bundle load "
                     f"failed ({e}) — a policy-required analysis will not run "
                     "against an unverified or self-rehashed design")
        policy = vb.admissibility_policy
        thresholds = vb.thresholds
        conditions = _conditions_from_design(vb.planned_design)
        retries_per_unit = vb.retries_per_unit
        if isinstance(retries_per_unit, bool) or retries_per_unit != 0:
            sys.exit(f"ORDER-REPORT REFUSED: frozen retries_per_unit="
                     f"{retries_per_unit!r} != 0 — the one-effective-unit "
                     "contract is mandatory on this path")
    else:
        policy = load_admissibility_policy(args.registry, args.experiment_id)
        thresholds = load_thresholds(args.registry, args.experiment_id)
        conditions = _conditions_from_design(
            _frozen_design(args.registry, args.experiment_id))
        retries_per_unit = None
    # terminal_dp_id is SCENARIO-DESIGN identity, DERIVED — never a CLI knob.
    # Under imposed history each m8 scenario carries exactly ONE decision-kind
    # point (the terminal probe); it must be unique within every scenario and
    # identical across the triplet, else the analysis refuses before running.
    from .scenario import load_scenario as _load_scen
    terminal_ids = set()
    for scen_id in conditions.values():
        scen = _load_scen(os.path.join(args.config_dir, f"{scen_id}.yaml"))
        decisions = [dp.dp_id for dp in scen.decision_points
                     if not dp.is_exposure()]
        if len(decisions) != 1:
            sys.exit(f"ORDER-REPORT REFUSED: {scen_id} has {len(decisions)} "
                     "decision-kind points; the imposed-history design "
                     "requires exactly one terminal probe")
        terminal_ids.add(decisions[0])
    if len(terminal_ids) != 1:
        sys.exit("ORDER-REPORT REFUSED: triplet disagrees on the terminal "
                 f"probe id {sorted(terminal_ids)}")
    try:
        report = metrics_mod.order_sensitivity_report(
            run_dirs, conditions,
            admissibility_policy=policy, thresholds=thresholds,
            replay_attestation=attestation,
            terminal_dp_id=terminal_ids.pop(),
            surviving_counts=surviving_counts,
            retries_per_unit=retries_per_unit)
    except SchemaError as e:
        # typed refusal: NOTHING is written — a refusal is an inconclusive
        # result, never a number (and never a file bearing distances)
        sys.exit(f"ORDER-REPORT REFUSED (typed): {e}")
    out_path = args.out or os.path.join(args.out_root, "order_report.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")
    from . import reports
    print(reports.render_order_report(report), end="")
    print("wrote", out_path)


def _git_head() -> str | None:
    """The candidate commit at invocation. Fail-closed at the caller: None
    (no git, detached failure, empty output) REFUSES — it is never treated
    as a match."""
    try:
        p = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                           text=True, timeout=10)
    except Exception:
        return None
    out = p.stdout.strip()
    return out if p.returncode == 0 and out else None


def _verify_smoke_authorization(auth_path, *, experiment_id,
                                expected_design_hash, expected_digests,
                                expected_scale, expected_run_count):
    """Verify a canonical owner experiment authorization manifest against the
    LIVE registry design identity and the candidate commit at invocation.

    Every failure sys.exits nonzero BEFORE any filesystem mutation and before
    run_sweep is ever reached. Absent / unreadable / design-audit-only /
    stale / mismatched manifests all refuse; only the exact binding passes.
    """
    if not auth_path:
        sys.exit("SMOKE-PACK REFUSED: no --authorization manifest — live "
                 "provider contact requires a canonical owner experiment "
                 "authorization binding design_hash, candidate_commit, "
                 "model_digests, run_count and budget; the non-claim-bearing "
                 "smoke marker governs analysis only and never grants "
                 "contact authority")
    try:
        with open(auth_path, encoding="utf-8") as fh:
            auth = json.load(fh)
    except OSError as e:
        sys.exit(f"SMOKE-PACK REFUSED: authorization manifest unreadable: {e}")
    except ValueError as e:
        sys.exit(f"SMOKE-PACK REFUSED: authorization manifest is not valid "
                 f"JSON: {e}")
    if not isinstance(auth, dict):
        sys.exit("SMOKE-PACK REFUSED: authorization manifest must be a JSON "
                 "object")
    missing = [k for k in SMOKE_AUTHORIZATION_FIELDS if k not in auth]
    if missing:
        sys.exit("SMOKE-PACK REFUSED: authorization manifest is missing "
                 f"required bindings {missing} — a partial artifact (e.g. a "
                 "design-audit approval) is not owner execution authority")
    problems = []
    if auth["authorization_version"] != SMOKE_AUTHORIZATION_VERSION:
        problems.append(f"authorization_version "
                        f"{auth['authorization_version']!r} != "
                        f"{SMOKE_AUTHORIZATION_VERSION!r}")
    if auth["authorization_kind"] != SMOKE_AUTHORIZATION_KIND:
        problems.append(f"authorization_kind {auth['authorization_kind']!r} "
                        f"!= {SMOKE_AUTHORIZATION_KIND!r} — a design-audit "
                        "(or any other) approval is NOT authority to contact "
                        "the provider")
    if auth["experiment_id"] != experiment_id:
        problems.append(f"experiment_id {auth['experiment_id']!r} != "
                        f"{experiment_id!r}")
    if auth["design_hash"] != expected_design_hash:
        problems.append(f"design_hash {str(auth['design_hash'])[:16]}… does "
                        f"not match the live registry's reconstructed design "
                        f"hash {expected_design_hash[:16]}… — STALE or "
                        "foreign authorization")
    head = _git_head()
    if head is None:
        sys.exit("SMOKE-PACK REFUSED: cannot resolve the candidate commit "
                 "(git HEAD) — the commit binding cannot be verified, so the "
                 "authorization fails closed")
    if auth["candidate_commit"] != head:
        problems.append(f"candidate_commit {str(auth['candidate_commit'])[:12]}"
                        f"… != current HEAD {head[:12]}… — STALE "
                        "authorization for another candidate")
    if auth["model_digests"] != expected_digests:
        problems.append(f"model_digests {auth['model_digests']!r} do not "
                        f"exactly match the frozen design's "
                        f"{expected_digests!r}")
    if auth["scale"] != expected_scale:
        problems.append(f"scale {auth['scale']!r} != invoked --scale "
                        f"{expected_scale}")
    if auth["run_count"] != expected_run_count:
        problems.append(f"run_count {auth['run_count']!r} != the "
                        f"{expected_run_count} units this invocation would "
                        "execute")
    budget = auth["budget"]
    if not isinstance(budget, dict) or isinstance(
            budget.get("max_units"), bool) or not isinstance(
            budget.get("max_units"), int) or budget["max_units"] < 1:
        problems.append("budget must be an object with a positive integer "
                        "max_units")
    elif expected_run_count > budget["max_units"]:
        problems.append(f"run_count {expected_run_count} exceeds the "
                        f"authorized budget max_units {budget['max_units']}")
    if problems:
        sys.exit("SMOKE-PACK REFUSED: authorization does not bind this "
                 "invocation: " + "; ".join(problems))
    return auth


def cmd_smoke_pack(args):
    """Scaled-down operational-validation pack: the frozen planned_design with
    only the first --scale sampler seeds, run interleaved, marked NOT
    claim-bearing. Never contacts a silently-defaulted local host, and NEVER
    initiates live provider contact (or writes anything preparing one)
    without a canonical owner experiment authorization (--authorization)
    whose bindings — design_hash, candidate_commit, model_digests,
    run_count/scale, budget — verify against the live registry and git HEAD.
    The smoke marker's non-claim-bearing status governs analysis refusal
    only; it is never a substitute for that authority."""
    from . import sweep
    from .registry import _frozen_design, design_hash, load_thresholds

    if not os.environ.get("OLLAMA_HOST"):
        sys.exit("SMOKE-PACK REFUSED: OLLAMA_HOST is not set — a smoke pack "
                 "never falls back to a silent local default; export "
                 "OLLAMA_HOST to name the host explicitly")
    if "smoke" not in os.path.basename(os.path.normpath(args.out_root)).lower():
        sys.exit(f"SMOKE-PACK REFUSED: out_root {args.out_root!r} is not "
                 "labeled 'smoke' — smoke evidence must be visibly "
                 "segregated from claim-bearing packs")
    pd = _frozen_design(args.registry, args.experiment_id)
    models = list(pd["models"])
    digests = dict(pd["model_digests"])
    sampler_seeds = list(pd["sampler_seeds"])[:args.scale]
    if args.scale < 1 or not sampler_seeds:
        sys.exit("SMOKE-PACK REFUSED: --scale must select at least one "
                 "frozen sampler seed")
    # the exact grid this invocation would execute — the run-count binding
    expected_run_count = (len(models) * len(pd["scenarios"])
                          * len(pd["scenario_seeds"]) * len(sampler_seeds))
    # owner authorization gate: verified BEFORE any filesystem mutation
    # (marker, out_root) and before run_sweep can be reached
    _verify_smoke_authorization(
        args.authorization, experiment_id=args.experiment_id,
        expected_design_hash=design_hash(pd), expected_digests=digests,
        expected_scale=args.scale, expected_run_count=expected_run_count)
    print(f"authorization : {args.authorization} "
          f"({expected_run_count} units within owner budget)")
    print("smoke-pack will contact these digest-pinned models "
          "(operational validation only, claim_bearing: false):")
    for m in models:
        print(f"  {m} @ {digests.get(m)}")
    os.makedirs(args.out_root, exist_ok=True)
    marker_path = os.path.join(args.out_root, SMOKE_MARKER_NAME)
    # marker FIRST, before any run: even a crashed smoke pack stays marked
    with open(marker_path, "w", encoding="utf-8") as fh:
        json.dump({"claim_bearing": False,
                   "purpose": "operational validation",
                   "experiment_id": args.experiment_id,
                   "scale": args.scale,
                   "sampler_seeds": sampler_seeds}, fh, indent=2,
                  sort_keys=True)
        fh.write("\n")
    manifest_path = os.path.join(args.out_root, "manifest.smoke.jsonl")
    # a-006 B-0/C-0/E-0: the smoke pack exercises the SAME frozen execution
    # contract the live pack will face. It must carry the experiment identity and
    # be driven by a verified ExecutionPolicy (zero-retry tombstones), never loose
    # kwargs — otherwise a smoke resume could re-roll a failed unit and the
    # "operational validation" would not validate the contract it claims to.
    spec = {"models": models,
            "scenarios": list(pd["scenarios"]),
            "seeds": list(pd["scenario_seeds"]),
            "sampler_seeds": sampler_seeds,
            "temperature": pd["temperature"],
            "arbitration": pd["arbitration"],
            "interaction": pd["interaction_mode"],
            "config_dir": args.config_dir,
            "out_root": args.out_root,
            "manifest": manifest_path,
            "experiment_id": args.experiment_id,
            "registry_path": args.registry}
    from .registry import load_verified_bundle
    from .schema import SchemaError
    try:
        _vb = load_verified_bundle(args.registry, args.experiment_id)
        policy = sweep.ExecutionPolicy.from_verified_bundle(
            _vb, execution_order="interleaved", record_execution_index=True)
    except SchemaError as e:
        sys.exit(f"SMOKE-PACK REFUSED: verified frozen bundle / execution "
                 f"policy unavailable ({e})")
    try:
        result = sweep.run_sweep(spec, expected_digests=digests,
                                 execution_policy=policy, progress=print)
    except Exception as e:
        sys.exit(f"SMOKE-PACK FAILED: {e.__class__.__name__}: {e} "
                 f"(marker {marker_path} remains; evidence is NOT "
                 "claim-bearing)")
    print(f"smoke marker : {marker_path}")
    print(f"manifest     : {manifest_path}")
    print(f"rows written : {result.rows_written} "
          f"(resumed {result.skipped_resumed}, errors {len(result.errors)})")


def cmd_result_package(args):
    """Close a completed, analyzed pack into a self-verifying result package."""
    from .result_package import build_result_package
    from .schema import SchemaError
    extra = {}
    if args.extra:
        try:
            extra = json.loads(args.extra)
        except ValueError as e:
            sys.exit(f"RESULT-PACKAGE REFUSED: --extra is not valid JSON: {e}")
    try:
        path = build_result_package(args.experiment_id, args.manifest,
                                    args.out_root, args.registry,
                                    args.report, extra,
                                    config_dir=getattr(args, "config_dir",
                                                       "configs/scenarios"))
    except SchemaError as e:
        sys.exit(f"RESULT-PACKAGE REFUSED: {e}")
    print("wrote", path)


def cmd_spatial_run(args):
    """S2D: build + schedule + verify + observe a scripted spatial scenario; the
    run dir is experiment evidence (deterministic, replayable, byte-identical)."""
    from .spatial.run import execute_spatial_run
    control_dir = (os.path.join(args.spatial_root, args.control_run)
                   if args.control_run else None)
    s = execute_spatial_run(args.scenario, args.seed, out_root=args.spatial_root,
                            intervention=args.intervention,
                            control_run_dir=control_dir)
    print(f"run_id   : {s['run_id']}")
    print(f"manifest : {s['manifest_id']}")
    print(f"chain    : {s['chain_length']} scheduler states "
          f"(stop {s['explicit_stop_position']}, fork point {s['fork_position']})")
    print(f"terminal : {s['terminal_world_state_id']}")
    print(f"evidence : {os.path.join(args.spatial_root, s['run_id'])}")


def cmd_spatial_replay(args):
    """S2D: the replay gate — re-execute from nothing and byte-compare evidence."""
    from .spatial.run import replay_spatial_run
    ok, detail = replay_spatial_run(args.run_id, out_root=args.spatial_root)
    if not ok:
        sys.exit(f"REPLAY FAILED: {args.run_id}: {detail}")
    print(f"{detail} ({args.run_id})")


def cmd_spatial_inspect(args):
    """S2D: what an agent could see, step by step, from the evidence alone."""
    from .spatial.run import inspect_spatial_run
    rows = inspect_spatial_run(args.run_id, out_root=args.spatial_root,
                               view=args.view, agent=args.agent)
    if not rows:
        sys.exit("no observations matched")
    for r in rows:
        c = r["content"]
        seen = c.get("visible_entity_identities", [])
        room = c.get("visible_room_identity")
        print(f"pos {r['scheduler_position']:>3}  {r['observer_key']:<8} "
              f"room={str(room)[:12] if room else '-':<12} "
              f"sees {len(seen)} entities  obs {r['observation_id'][:16]}")
        if args.full:
            print(json.dumps(c, indent=2))


def main(argv=None):
    p = argparse.ArgumentParser(prog="coliseum-lab", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-root", default="logs/runs")
    p.add_argument("--config-dir", default="configs/scenarios")
    p.add_argument("--derived-root", default="derived/textlab/metrics")
    p.add_argument("--graphs-root", default="derived/textlab/graphs")
    p.add_argument("--repo-root", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)

    interaction_choices = ["independent_vignettes", "sequential_history"]
    s = sub.add_parser("run");     s.set_defaults(fn=cmd_run)
    s.add_argument("--scenario", required=True); s.add_argument("--agent", default="scripted:obedient")
    s.add_argument("--seed", type=int, default=42,
                   help="SCENARIO seed (variant selection)")
    s.add_argument("--sampler-seed", type=int, default=None,
                   help="backend sampling seed (required when --temperature > 0)")
    s.add_argument("--temperature", type=float, default=0.0)
    s.add_argument("--arbitration", default="planner_priority")
    s.add_argument("--interaction", default="independent_vignettes", choices=interaction_choices,
                   help="independent_vignettes = each decision prompt stands alone; "
                        "sequential_history = later prompts carry prior actions/outcomes")
    s = sub.add_parser("replay");  s.set_defaults(fn=cmd_replay);  s.add_argument("run_id")
    s = sub.add_parser("metrics"); s.set_defaults(fn=cmd_metrics); s.add_argument("run_ids", nargs="*")
    s.add_argument("--mode", default="deterministic",
                   choices=["deterministic", "stochastic", "variants", "full-grid"])
    s.add_argument("--diagnostics", action="store_true",
                   help="include non-admitted runs in the aggregate (labeled; not for claims)")
    s.add_argument("--interaction", default="independent_vignettes", choices=interaction_choices,
                   help="which experimental mode to aggregate (modes never pool)")
    s = sub.add_parser("graph");   s.set_defaults(fn=cmd_graph);   s.add_argument("run_ids", nargs="*")
    s = sub.add_parser("compare"); s.set_defaults(fn=cmd_compare)
    s.add_argument("--mode", default="deterministic",
                   choices=["deterministic", "stochastic", "variants", "full-grid"])
    s.add_argument("--diagnostics", action="store_true",
                   help="include non-admitted runs (labeled; not for claims)")
    s.add_argument("--interaction", default="independent_vignettes", choices=interaction_choices,
                   help="which experimental mode to aggregate (modes never pool)")
    spatial_root_kw = dict(default=os.path.join("logs", "spatial-runs"),
                           help="spatial-run evidence root (separate from the "
                                "vignette logs/runs tree)")
    s = sub.add_parser("spatial-run"); s.set_defaults(fn=cmd_spatial_run)
    s.add_argument("--scenario", required=True)
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--intervention", default=None,
                   help="calibration MVP: run the named preregistered TREATMENT "
                        "(requires --control-run)")
    s.add_argument("--control-run", default=None,
                   help="the completed CONTROL run id under --spatial-root")
    s.add_argument("--spatial-root", **spatial_root_kw)
    s = sub.add_parser("spatial-replay"); s.set_defaults(fn=cmd_spatial_replay)
    s.add_argument("run_id")
    s.add_argument("--spatial-root", **spatial_root_kw)
    s = sub.add_parser("spatial-inspect"); s.set_defaults(fn=cmd_spatial_inspect)
    s.add_argument("run_id")
    s.add_argument("--view", default="actor", choices=["actor", "privileged"])
    s.add_argument("--agent", default=None)
    s.add_argument("--full", action="store_true",
                   help="print each observation's full content")
    s.add_argument("--spatial-root", **spatial_root_kw)

    # ---- M8 Phase-2 operator surface --------------------------------------
    s = sub.add_parser("replay-pack", help="provider-free replay of a whole "
                       "pack -> replay_attestation.json (refuses on any "
                       "failure)")
    s.set_defaults(fn=cmd_replay_pack)
    s.add_argument("--manifest", required=True)
    s.add_argument("--out-root", required=True)
    s.add_argument("--config-dir", default="configs/scenarios")

    s = sub.add_parser("order-report", help="ORDER_REPORT_VERSION-4 analysis "
                       "of a replay-attested pack (refuses smoke packs and "
                       "unattested evidence)")
    s.set_defaults(fn=cmd_order_report)
    s.add_argument("--experiment-id", required=True)
    s.add_argument("--manifest", required=True)
    s.add_argument("--out-root", required=True)
    s.add_argument("--registry", default="configs/registry/experiments.yaml")
    s.add_argument("--config-dir", default="configs/scenarios",
                   help="scenario YAML dir; the terminal probe id is DERIVED "
                        "from the triplet's unique decision-kind point")
    s.add_argument("--out", default=None,
                   help="report path (default <out-root>/order_report.json)")

    s = sub.add_parser("smoke-pack", help="scaled-down operational-validation "
                       "pack (never claim-bearing; requires OLLAMA_HOST and a "
                       "canonical owner --authorization manifest before any "
                       "live contact)")
    s.set_defaults(fn=cmd_smoke_pack)
    s.add_argument("--experiment-id", required=True)
    s.add_argument("--scale", type=int, required=True,
                   help="use the first N frozen sampler seeds")
    s.add_argument("--out-root", required=True,
                   help="must be labeled 'smoke' (e.g. logs/runs/m8-smoke)")
    s.add_argument("--registry", default="configs/registry/experiments.yaml")
    s.add_argument("--config-dir", default="configs/scenarios")
    s.add_argument("--authorization", default=None,
                   help="REQUIRED owner experiment authorization manifest "
                        "(JSON) binding authorization_kind="
                        "owner_experiment_execution, experiment_id, "
                        "design_hash (live registry), candidate_commit "
                        "(git HEAD), model_digests, run_count, scale, and "
                        "budget.max_units; absent/stale/design-audit-only "
                        "manifests refuse before anything is written")

    s = sub.add_parser("result-package", help="close an analyzed pack into a "
                       "self-verifying result_package.json")
    s.set_defaults(fn=cmd_result_package)
    s.add_argument("--experiment-id", required=True)
    s.add_argument("--manifest", required=True)
    s.add_argument("--out-root", required=True)
    s.add_argument("--report", required=True,
                   help="path to the order_report.json this package closes over")
    s.add_argument("--registry", default="configs/registry/experiments.yaml")
    s.add_argument("--config-dir", default="configs/scenarios",
                   help="scenario dir used to independently RE-DERIVE the "
                        "verdict from evidence (d-003 f2); the packaged report "
                        "must match that recomputation")
    s.add_argument("--extra", default=None,
                   help="JSON object of extra fields (e.g. suite receipt)")

    s = sub.add_parser("dataset-export"); s.set_defaults(fn=cmd_dataset_export)
    s.add_argument("--manifest", default=None,
                   help="evidence manifest to export (default: all runs under --out-root)")
    s.add_argument("--registry", default="configs/registry/experiments.yaml",
                   help="experiments registry for the held-out attestation (by id AND hash)")
    s.add_argument("--verify", action="store_true",
                   help="byte-gate every run via replay before inclusion")
    s.add_argument("--mode", default="deterministic",
                   choices=["deterministic", "stochastic", "variants", "full-grid"])
    s.add_argument("--interaction", default="independent_vignettes", choices=interaction_choices,
                   help="which experimental mode to export (modes never pool)")
    s.add_argument("--partition", action="store_true",
                   help="fold a deterministic, dataset-version-bound group-aware "
                        "split (§8) into the descriptor + commitment")
    s.add_argument("--scenario-registry", default="configs/registry/scenarios.yaml",
                   help="scenario registry supplying the §8 sibling fields "
                        "(family / control_of) for group-aware partitioning")
    s.add_argument("--training-admission", action="store_true",
                   help="apply the §8 training-data admission gate: filter to "
                        "training-eligible runs and record the admit/reject report")
    s.add_argument("--admission-require-replay", action="store_true",
                   help="admission also requires byte-identical replay per run")

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()

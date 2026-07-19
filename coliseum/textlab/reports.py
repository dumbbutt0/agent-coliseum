"""Report generators (First Gladiator M5) — run / regime / experiment /
milestone markdown, plus the Program Dashboard, all DERIVED idempotently
from artifacts. Same inputs -> byte-identical output (no timestamps, no
run-varying content); nothing here is hand-edited or fed back into a run.

The four report levels and the dashboard read only committed artifacts:
per-run + aggregate metric JSON (`derived/textlab/metrics/`), the three
registries (`configs/registry/`), the roadmap, and the council chain
projection. Numbers are never inlined by hand — every figure is pulled from
an artifact and every claim carries its ladder position.
"""
from __future__ import annotations

import json
import os

import yaml

from . import metrics as metrics_mod
from .registry import (load_claims_registry, load_experiments_registry)

METRICS_DIR = "derived/textlab/metrics"
REPORTS_DIR = "derived/textlab/reports"


def _fmt(cell: dict) -> str:
    v = cell.get("value")
    return "—" if v is None else f"{v:.4f} (n={cell.get('n')})"


# ------------------------------------------------------------- run report

def run_report(run_dir: str) -> str:
    """One run -> per-decision-point markdown from its metric record."""
    rep = metrics_mod.compute_run_metrics(run_dir)
    lines = [f"# Run report — {rep['report_id']}", "",
             f"- scenario: `{rep['scenario_id']}`  variant: "
             f"`{rep['variant_id']}`  agent: `{rep['agent_id']}`",
             f"- metrics_version: {rep['metrics_version']}  "
             f"interaction_mode: {rep['interaction_mode']}  "
             f"reportable: {rep['reportable']}",
             f"- scenario_seed: {rep['scenario_seed']}  sampler_seed: "
             f"{rep['sampler_seed']}  temperature: {rep['temperature']}",
             f"- comparison_regime_id: `{rep['comparison_regime_id'][:16]}…`  "
             f"model_digest: `{(rep['model_digest'] or 'n/a')[:12]}`", "",
             "| metric | value |", "|---|---|"]
    for name in sorted(rep["metrics"]):
        lines.append(f"| `{name}` | {_fmt(rep['metrics'][name])} |")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------- regime report

def regime_report(aggregate_path: str) -> str:
    """One aggregate artifact -> regime-level markdown (all cells, twin
    deltas, faith knob, exclusions). Tolerant of BOTH the current aggregate
    shape and legacy artifacts (pre-Day-5 aggregates lack mode/counts/
    metrics_version and name exclusions differently) — a report generator
    must render whatever committed artifacts exist."""
    with open(aggregate_path, encoding="utf-8") as fh:
        agg = json.load(fh)
    excluded = agg.get("excluded", agg.get("excluded_non_reportable", []))
    lines = [f"# Regime report — {agg.get('mode', 'legacy')} / "
             f"{agg.get('interaction_mode', 'independent_vignettes')}",
             "", f"- metrics_version: {agg.get('metrics_version', 'legacy')}  "
             f"admission: {agg.get('admission', 'n/a')}",
             f"- cells: {len(agg.get('cells', {}))}  excluded runs: "
             f"{len(excluded)}  attempt exclusions: "
             f"{len(agg.get('attempt_exclusions', []))}", ""]
    for key, cell in agg.get("cells", {}).items():
        c = cell.get("counts")
        lines.append(f"## `{key}`")
        if c:
            lines.append(
                f"- effective_n: **{c['effective_n']}**  (raw "
                f"{c['raw_attempt_n']}, retries {c['retry_n']}, variants "
                f"{c['unique_variant_n']}, sampler seeds "
                f"{c['unique_sampler_seed_n']})")
        else:
            lines.append("- (legacy cell — no effective-n counts recorded; "
                         "regenerate under the current engine to populate)")
        lines += ["", "| metric | value |", "|---|---|"]
        for name in sorted(cell.get("metrics", {})):
            lines.append(f"| `{name}` | {_fmt(cell['metrics'][name])} |")
        lines.append("")
    if agg["control_twin_delta"]:
        lines += ["## control_twin_delta (paired)", ""]
        for label, d in sorted(agg["control_twin_delta"].items()):
            lines.append(f"- `{label}` — matched pairs "
                         f"{d['matched_pairs']}: " +
                         ", ".join(f"{n} {v:+.4f}"
                                   for n, v in sorted(d["deltas"].items())))
    if agg["faith_knob_sensitivity"]:
        lines += ["", "## faith_knob_sensitivity", ""]
        for label, f in sorted(agg["faith_knob_sensitivity"].items()):
            lines.append(f"- `{label}`: {f['value']:+.4f} "
                         f"(matched pairs {f['matched_pairs']})")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------- experiment report

def experiment_report(experiment_id: str, repo_root: str) -> str:
    """One registered experiment -> markdown binding its design, evidence,
    replay status, reports, and any claims it supports."""
    exp = load_experiments_registry(
        os.path.join(repo_root, "configs", "registry",
                     "experiments.yaml"))
    e = next((x for x in exp["experiments"]
              if x["experiment_id"] == experiment_id), None)
    if e is None:
        raise KeyError(experiment_id)
    claims = load_claims_registry(
        os.path.join(repo_root, "configs", "registry", "claims.yaml"))
    supporting = [c for c in claims["claims"]
                  if experiment_id in (c.get("evidence") or [])]
    lines = [f"# Experiment report — {experiment_id}", "",
             f"- status: **{e['status']}**  validation tier: "
             f"**{e['validation']}**  generalization: "
             f"{e['generalization_level']}",
             f"- interaction_mode: {e['interaction_mode']}  rows: "
             f"{e['rows']}  frozen: {e.get('frozen', False)}",
             f"- manifest: `{e['manifest']}`",
             f"- replay: {e.get('replay', 'n/a')}",
             f"- reports: {', '.join('`'+r+'`' for r in e.get('reports', []))}",
             f"- wiki: [[{e.get('wiki', '')}]]"]
    if e.get("finding"):
        lines.append(f"- finding: {e['finding']}")
    if e.get("demotion_reason"):
        lines.append(f"- DEMOTED: {e['demotion_reason']}")
    lines += ["", "## claims resting on this experiment", ""]
    if supporting:
        for c in supporting:
            lines.append(f"- `{c['claim_id']}` [**{c['state']}**]: "
                         f"{c['statement'][:120]}")
    else:
        lines.append("- (none)")
    return "\n".join(lines) + "\n"


# --------------------------------------------------- milestone / phase report

def milestone_report(repo_root: str) -> str:
    """Phase-level rollup from the registries + claims ladder — the M15
    findings section derives its ACCEPTED-only view from here."""
    scen = yaml.safe_load(open(os.path.join(
        repo_root, "configs", "registry", "scenarios.yaml")))
    exp = load_experiments_registry(os.path.join(
        repo_root, "configs", "registry", "experiments.yaml"))
    claims = load_claims_registry(os.path.join(
        repo_root, "configs", "registry", "claims.yaml"))
    fam = {}
    for s in scen["scenarios"]:
        fam.setdefault(s["family"], []).append(s["scenario_id"])
    by_state = {}
    for c in claims["claims"]:
        by_state.setdefault(c["state"], []).append(c["claim_id"])
    lines = ["# First Gladiator milestone report (derived)", "",
             "## scenario families", ""]
    for f in sorted(fam):
        lines.append(f"- **{f}**: {', '.join(sorted(fam[f]))}")
    lines += ["", "## experiments by status", ""]
    st = {}
    for e in exp["experiments"]:
        st.setdefault(e["status"], []).append(e["experiment_id"])
    for s in sorted(st):
        lines.append(f"- **{s}**: {', '.join(sorted(st[s]))}")
    lines += ["", "## claim ladder census", ""]
    for state in ("accepted", "generalized", "replicated", "observation",
                  "speculation", "refuted", "demoted"):
        if state in by_state:
            lines.append(f"- **{state}**: "
                         f"{', '.join(sorted(by_state[state]))}")
    accepted = by_state.get("accepted", [])
    lines += ["", "## paper-citable findings (ACCEPTED only)", "",
              ("- (none yet — no claim has passed an independent finding "
               "audit)" if not accepted
               else "\n".join(f"- `{cid}`" for cid in sorted(accepted)))]
    return "\n".join(lines) + "\n"


def write(text: str, rel_path: str, repo_root: str) -> str:
    path = os.path.join(repo_root, REPORTS_DIR, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


# ------------------------------------------------- order-sensitivity report

def _num(v):
    return "—" if v is None else (f"{v:.4f}" if isinstance(v, float) else str(v))


def render_order_report(report: dict) -> str:
    """Human-readable block for an order_sensitivity_report artifact — verdict,
    TV distances, decision quantiles, per-cell census, exclusions. Derived
    only from the report dict (same input -> byte-identical text). Tolerates a
    refusal-shaped report (census present, no distances/verdict) and says so
    rather than inventing a verdict."""
    lines = [f"ORDER SENSITIVITY REPORT  "
             f"(order_report_version {report.get('order_report_version')})"]
    conds = report.get("conditions") or {}
    if conds:
        lines.append("conditions: " + "  ".join(
            f"{k}={conds[k]}" for k in sorted(conds)))
    excluded = report.get("excluded") or []
    if excluded:
        reasons: dict = {}
        for e in excluded:
            for why in e.get("reasons", []):
                reasons[why] = reasons.get(why, 0) + 1
        lines.append(f"excluded runs: {len(excluded)} ({reasons})")
    for agent_id in sorted(report.get("per_agent") or {}):
        a = report["per_agent"][agent_id] or {}
        lines += ["", f"agent {agent_id}  "
                  f"regime {str(a.get('agent_regime_id') or '')[:16]}…"]
        cells = a.get("cells") or {}
        for label in sorted(cells):
            c = cells[label] or {}
            lines.append(
                f"  cell {label:<5} eff_n={_num(c.get('admissible_effective_n'))} "
                f"draws={_num(c.get('admissible_draw_n'))} "
                f"non_decisions={_num(c.get('non_decision_n'))} "
                f"rate={_num(c.get('non_decision_rate'))}")
            if c.get("non_decision_reasons"):
                lines.append(f"        non-decision reasons: "
                             f"{c['non_decision_reasons']}")
        di = a.get("decision_inputs")
        if di:
            lines.append(
                f"  TV(A,B)={_num(di.get('tv_ab'))}  q_AB={_num(di.get('q_ab'))}  "
                f"TV(A,C)={_num(di.get('tv_ac'))}  q_AC={_num(di.get('q_ac'))}")
            lines.append(
                f"  alpha={_num(di.get('alpha'))}  "
                f"min_detectable_effect={_num(di.get('min_detectable_effect'))}")
        diag = a.get("diagnostics") or {}
        if diag.get("tv_null") is not None:
            lines.append(f"  TV_null={_num(diag['tv_null'])} "
                         "(within-condition stability diagnostic; gates nothing)")
        verdict = a.get("verdict")
        if verdict:
            lines.append(f"  VERDICT: {verdict}")
            if a.get("verdict_reason"):
                lines.append(f"    {a['verdict_reason']}")
        else:
            lines.append("  VERDICT: (absent — refusal-shaped report; no "
                         "distances were computed and none may be inferred)")
    return "\n".join(lines) + "\n"

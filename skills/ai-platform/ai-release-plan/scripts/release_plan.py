#!/usr/bin/env python3
"""Staged rollout plan for an AI/LLM release: facts + owner-supplied gates -> plan + gate status.

Builds offline eval -> shadow -> canary steps -> GA. The number and size of canary steps follow
the skill's rollout policy by risk tier (references/rollout-policy.md; overridable with the
`canary_steps` fact). Gates are never defaulted: every gate comes from --gates. The script
evaluates which gates are met NOW from the facts, computes the minimum shadow/canary duration
to observe `min_observed_requests` at the stated `daily_requests`, derives rollback triggers
from the live-stage gates, and assigns an owner per step (missing ->
`[TO BE BASELINED — owner: Release manager]`).

Usage:
  python3 -I release_plan.py --facts release-facts.csv --gates release-gates.csv --out-dir OUT

Inputs:
  facts  CSV key,value[,source,notes]. Required keys: system_name, risk_tier (low|medium|high).
         Optional: eval_pass_rate, redteam_pass_rate, latency_p95_ms, error_rate (or any metric a
         gate names), daily_requests, min_observed_requests, rollback_time_min, canary_steps
         ("1;5;25"), owner_<role> for role in eval_lead, sre_oncall, release_manager,
         product_owner.
  gates  CSV stage,metric,min,max[,source,notes]; stage in offline_eval|shadow|canary|ga;
         at least one of min/max per row. Lines starting with '#' are comments.

Outputs (in --out-dir): release-plan.md (Readiness, Stages, Gates, Rollback, Owners), gates.json.
Exit codes: 0 plan written and first-stage gates met · 1 a first-stage gate is not met (or the
first stage has no gate) — outputs are still written · 2 missing/invalid required input.
Stdlib only; no network; writes only inside --out-dir.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
from pathlib import Path

TBD_OWNER = "[TO BE BASELINED — owner: Release manager]"
STAGES = ["offline_eval", "shadow", "canary", "ga"]
TIERS = ("low", "medium", "high")
# The skill's rollout policy (references/rollout-policy.md): canary traffic % steps per risk tier.
CANARY_POLICY = {"low": [10.0, 50.0], "medium": [5.0, 25.0, 50.0], "high": [1.0, 5.0, 10.0, 25.0, 50.0]}
ROLES = {
    "eval_lead": "Eval lead",
    "sre_oncall": "SRE on-call",
    "release_manager": "Release manager",
    "product_owner": "Product owner",
}
STEP_ROLE = {"offline_eval": "eval_lead", "shadow": "sre_oncall", "canary": "release_manager",
             "ga": "product_owner", "rollback": "sre_oncall"}


class InputError(Exception):
    """Missing or invalid required input -> exit 2."""


def fmt(x) -> str:
    """Stable number formatting shared by the Markdown and the JSON (so numbers trace)."""
    if x is None:
        return ""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    if isinstance(x, float):
        return f"{x:.6g}"
    return str(x)


def num(x):
    """JSON value for a number: int when integral."""
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return x


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise InputError(f"input file not found: {path}")
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#")]
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO("\n".join(lines)))]


def to_float(v: str):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_facts(path: Path) -> dict[str, str]:
    rows = read_csv(path)
    if rows and ("key" not in rows[0] or "value" not in rows[0]):
        raise InputError("facts CSV needs columns key,value")
    facts = {r["key"]: r["value"] for r in rows if r.get("key") and r.get("value") != ""}
    missing = [k for k in ("system_name", "risk_tier") if k not in facts]
    if missing:
        raise InputError(f"facts missing required keys: {', '.join(missing)}")
    if facts["risk_tier"].lower() not in TIERS:
        raise InputError(f"risk_tier must be one of {TIERS}, got {facts['risk_tier']!r}")
    facts["risk_tier"] = facts["risk_tier"].lower()
    return facts


def load_gates(path: Path) -> list[dict]:
    rows = read_csv(path)
    if not rows:
        raise InputError("gates CSV has no gate rows; gates are owner-supplied and never defaulted")
    for col in ("stage", "metric", "min", "max"):
        if col not in rows[0]:
            raise InputError(f"gates CSV needs columns stage,metric,min,max (missing {col})")
    gates = []
    for i, r in enumerate(rows, start=2):
        stage = r["stage"].lower()
        if stage not in STAGES:
            raise InputError(f"gates line {i}: stage {r['stage']!r} not in {STAGES}")
        lo, hi = to_float(r["min"]), to_float(r["max"])
        if (r["min"] and lo is None) or (r["max"] and hi is None):
            raise InputError(f"gates line {i}: min/max must be numeric")
        if lo is None and hi is None:
            raise InputError(f"gates line {i}: gate {r['metric']!r} needs a min or a max")
        gates.append({"stage": stage, "metric": r["metric"], "min": lo, "max": hi, "source": r.get("source", "")})
    return gates


def evaluate_gate(g: dict, facts: dict[str, str]) -> dict:
    raw = facts.get(g["metric"])
    actual = to_float(raw) if raw is not None else None
    if actual is None:
        status = "not measured"
    else:
        ok = (g["min"] is None or actual >= g["min"]) and (g["max"] is None or actual <= g["max"])
        status = "met" if ok else "NOT MET"
    return {"stage": g["stage"], "metric": g["metric"], "min": num(g["min"]), "max": num(g["max"]),
            "actual": num(actual) if actual is not None else None, "status": status, "source": g["source"]}


def canary_steps(facts: dict[str, str]) -> tuple[list[float], str]:
    if facts.get("canary_steps"):
        steps = [to_float(s) for s in facts["canary_steps"].replace(",", ";").split(";") if s.strip()]
        if not steps or any(s is None or not 0 < s < 100 for s in steps) or steps != sorted(steps):
            raise InputError("canary_steps must be ascending percentages between 0 and 100, e.g. 1;5;25")
        return steps, "canary_steps fact (owner override)"
    return CANARY_POLICY[facts["risk_tier"]], f"skill policy for risk tier '{facts['risk_tier']}'"


def min_hours(n_req, daily, share_pct):
    """Hours to observe n_req requests when the stage sees share_pct % of daily traffic."""
    if n_req is None or daily is None or daily <= 0:
        return None
    return math.ceil(n_req / (daily * share_pct / 100.0 / 24.0))


def owner(facts: dict[str, str], role: str) -> str:
    return facts.get(f"owner_{role}") or TBD_OWNER


def build(facts: dict[str, str], gates: list[dict]) -> dict:
    evaluated = [evaluate_gate(g, facts) for g in gates]
    steps, steps_basis = canary_steps(facts)
    daily = to_float(facts.get("daily_requests", ""))
    n_req = to_float(facts.get("min_observed_requests", ""))

    def stage_gates(s):
        return [g for g in evaluated if g["stage"] == s]

    stages = [{"id": "offline_eval", "name": "Offline eval", "traffic_pct": 0, "served": False,
               "min_duration_hours": None, "gate_stage": "offline_eval"},
              {"id": "shadow", "name": "Shadow", "traffic_pct": 100, "served": False,
               "min_duration_hours": min_hours(n_req, daily, 100.0), "gate_stage": "shadow"}]
    for i, p in enumerate(steps, start=1):
        stages.append({"id": f"canary_{i}", "name": f"Canary {i}", "traffic_pct": num(p), "served": True,
                       "min_duration_hours": min_hours(n_req, daily, p), "gate_stage": "canary"})
    stages.append({"id": "ga", "name": "GA", "traffic_pct": 100, "served": True,
                   "min_duration_hours": None, "gate_stage": "ga"})
    for s in stages:
        role = STEP_ROLE[s["gate_stage"]]
        s["owner_role"] = ROLES[role]
        s["owner"] = owner(facts, role)
        gs = stage_gates(s["gate_stage"])
        s["gates_total"] = len(gs)
        s["gates_met_now"] = sum(1 for g in gs if g["status"] == "met")

    first = stage_gates("offline_eval")
    blockers = [g for g in first if g["status"] != "met"]
    first_ready = bool(first) and not blockers
    triggers = []
    for g in evaluated:
        if g["stage"] == "offline_eval":
            continue
        if g["max"] is not None:
            triggers.append({"stage": g["stage"], "metric": g["metric"], "condition": f"> {fmt(g['max'])}", "threshold": g["max"]})
        if g["min"] is not None:
            triggers.append({"stage": g["stage"], "metric": g["metric"], "condition": f"< {fmt(g['min'])}", "threshold": g["min"]})
    rb = to_float(facts.get("rollback_time_min", ""))
    return {
        "system_name": facts["system_name"],
        "risk_tier": facts["risk_tier"],
        "canary_steps_pct": [num(p) for p in steps],
        "canary_steps_basis": steps_basis,
        "daily_requests": num(daily) if daily is not None else None,
        "min_observed_requests": num(n_req) if n_req is not None else None,
        "rollback_time_min": num(rb) if rb is not None else None,
        "facts": {k: v for k, v in facts.items()},
        "first_stage_ready": first_ready,
        "first_stage_blockers": [g["metric"] for g in blockers] if first else ["no offline_eval gate supplied"],
        "stages": stages,
        "gates": evaluated,
        "rollback_triggers": triggers,
        "rollback_owner": owner(facts, STEP_ROLE["rollback"]),
        "owners": {ROLES[r]: owner(facts, r) for r in ROLES},
    }


def bound(g: dict) -> str:
    parts = []
    if g["min"] is not None:
        parts.append(f">= {fmt(g['min'])}")
    if g["max"] is not None:
        parts.append(f"<= {fmt(g['max'])}")
    return " and ".join(parts)


def render(plan: dict) -> str:
    tbd_dur = "[TO BE BASELINED — owner: Release manager]"
    L = [f"# Release plan — {plan['system_name']}", "",
         f"Risk tier: **{plan['risk_tier']}** · canary steps: {', '.join(fmt(p) + '%' for p in plan['canary_steps_pct'])} "
         f"({plan['canary_steps_basis']}). Gates are owner-supplied; none are defaulted.", "",
         "## Readiness", ""]
    if plan["first_stage_ready"]:
        L.append("**READY**: every offline_eval gate is met now; the rollout may start (Shadow after offline sign-off).")
    else:
        L.append("**NOT READY**: first-stage blockers: " + ", ".join(plan["first_stage_blockers"]) + ".")
    L += ["", "| Stage | Gates met now | Gates total |", "|---|---|---|"]
    for st in STAGES:
        gs = [g for g in plan["gates"] if g["stage"] == st]
        L.append(f"| {st} | {sum(1 for g in gs if g['status'] == 'met')} | {len(gs)} |")
    L += ["", "## Stages", "",
          "| # | Stage | Traffic % | Served to users | Min duration (hours) | Owner |", "|---|---|---|---|---|---|"]
    for i, s in enumerate(plan["stages"], start=1):
        if s["id"] in ("offline_eval", "ga"):
            dur = "n/a (gate sign-off)"
        else:
            dur = fmt(s["min_duration_hours"]) if s["min_duration_hours"] is not None else tbd_dur
        L.append(f"| {i} | {s['name']} | {fmt(s['traffic_pct'])} | {'yes' if s['served'] else 'no'} | {dur} | {s['owner']} |")
    L += ["", f"Minimum duration = ceil(min_observed_requests ÷ (daily_requests × traffic % ÷ 24)); "
          f"min_observed_requests = {fmt(plan['min_observed_requests']) or tbd_dur}, "
          f"daily_requests = {fmt(plan['daily_requests']) or tbd_dur}.", "",
          "## Gates", "", "| Stage | Metric | Threshold | Actual now | Status | Source |", "|---|---|---|---|---|---|"]
    for g in plan["gates"]:
        act = fmt(g["actual"]) if g["actual"] is not None else "—"
        L.append(f"| {g['stage']} | {g['metric']} | {bound(g)} | {act} | {g['status']} | {g['source'] or '—'} |")
    L += ["", "## Rollback", "",
          f"Rollback owner: {plan['rollback_owner']}. Stated rollback time (minutes): "
          f"{fmt(plan['rollback_time_min']) if plan['rollback_time_min'] is not None else tbd_dur}.", ""]
    if plan["rollback_triggers"]:
        L += ["| Stage | Stop or roll back when metric | Condition |", "|---|---|---|"]
        for t in plan["rollback_triggers"]:
            L.append(f"| {t['stage']} | {t['metric']} | {t['condition']} |")
    else:
        L.append("No live-stage gates supplied, so no automatic rollback triggers: "
                 "[TO BE BASELINED — owner: Release manager].")
    L += ["", "## Owners", "", "| Role | Owner |", "|---|---|"]
    for role, who in plan["owners"].items():
        L.append(f"| {role} | {who} |")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--facts", type=Path, required=True, help="release facts CSV (key,value)")
    ap.add_argument("--gates", type=Path, required=True, help="owner-supplied gates CSV")
    ap.add_argument("--out-dir", type=Path, required=True, help="directory for release-plan.md and gates.json")
    args = ap.parse_args(argv)
    try:
        plan = build(load_facts(args.facts), load_gates(args.gates))
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "gates.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out_dir / "release-plan.md").write_text(render(plan), encoding="utf-8")
    if not plan["first_stage_ready"]:
        print("first-stage gate(s) not met: " + ", ".join(plan["first_stage_blockers"]), file=sys.stderr)
        return 1
    print(f"release plan written: {len(plan['stages'])} stages, first stage ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())

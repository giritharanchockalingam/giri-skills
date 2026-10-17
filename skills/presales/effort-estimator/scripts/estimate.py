#!/usr/bin/env python3
"""PERT + Monte Carlo effort model over a WBS CSV, with staffing and cost roll-up.

Input WBS CSV columns (see assets/wbs-template.csv):
  task_id, phase, work_package, task, role, driver_group, count,
  unit_o, unit_m, unit_p, optimistic, most_likely, pessimistic, basis, predecessors, notes

Per task, effort in person-days is either:
  * parametric: count * unit_{o,m,p}   (used when count and unit_* are numeric), or
  * fixed:      optimistic / most_likely / pessimistic.
Rows whose count is non-numeric (e.g. "[TO BE BASELINED]") are reported as
unresolved and excluded from the totals, so the output never contains a figure
that was not in the input.

Model: Beta-PERT sampling per task (lambda = 4). Tasks sharing a non-empty
driver_group receive a common multiplier per iteration (log-normal, sigma 0.15)
to represent correlated uncertainty. Outputs P10/P50/P80/P90 totals, per-phase
statistics, variance contributors, basis mix, and (with --rates) a cost roll-up
and margin at P50 and P80.

Rate card CSV columns (see assets/rate-card.example.csv):
  role, grade, location, cost_rate, bill_rate, currency, valid_until, notes
Roles absent from the rate card are listed and excluded from cost; no rate is
ever assumed.

Usage:
    python3 -I estimate.py wbs.csv --iterations 20000 --out estimate.md
    python3 -I estimate.py wbs.csv --rates rate-card.csv --seed 7
    python3 -I estimate.py wbs.csv --json          # machine-readable summary

Standard library only. Exit 0 ok; 2 input error.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

PERT_LAMBDA = 4.0
GROUP_SIGMA = 0.15


@dataclass
class Task:
    task_id: str
    phase: str
    work_package: str
    name: str
    role: str
    driver_group: str
    o: float
    m: float
    p: float
    basis: str
    predecessors: list[str] = field(default_factory=list)
    unresolved_reason: str = ""

    @property
    def pert_mean(self) -> float:
        return (self.o + PERT_LAMBDA * self.m + self.p) / (PERT_LAMBDA + 2)

    @property
    def pert_sd(self) -> float:
        return (self.p - self.o) / 6.0


def _num(v: str) -> float | None:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def load_wbs(path: Path) -> tuple[list[Task], list[Task]]:
    tasks: list[Task] = []
    unresolved: list[Task] = []
    with open(path, newline="", encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        required = {"task_id", "phase", "task", "role"}
        missing = required - set(rdr.fieldnames or [])
        if missing:
            raise ValueError(f"WBS missing columns: {sorted(missing)}")
        for row in rdr:
            tid = (row.get("task_id") or "").strip()
            if not tid:
                continue
            count = _num(row.get("count", ""))
            uo, um, up = (_num(row.get(k, "")) for k in ("unit_o", "unit_m", "unit_p"))
            fo, fm, fp = (_num(row.get(k, "")) for k in ("optimistic", "most_likely", "pessimistic"))
            reason = ""
            if count is not None and None not in (uo, um, up):
                o, m, p = count * uo, count * um, count * up  # type: ignore[operator]
            elif None not in (fo, fm, fp):
                o, m, p = fo, fm, fp  # type: ignore[assignment]
            elif (row.get("count") or "").strip() and None not in (uo, um, up):
                reason = f"count not numeric: '{row.get('count')}'"
                o = m = p = 0.0
            else:
                reason = "no numeric three-point values"
                o = m = p = 0.0
            if not reason and not (o <= m <= p):
                reason = f"three-point values not ordered (O<=M<=P): {o}, {m}, {p}"
            t = Task(
                task_id=tid,
                phase=(row.get("phase") or "").strip(),
                work_package=(row.get("work_package") or "").strip(),
                name=(row.get("task") or "").strip(),
                role=(row.get("role") or "").strip(),
                driver_group=(row.get("driver_group") or "").strip(),
                o=o, m=m, p=p,
                basis=(row.get("basis") or "JUD").strip().upper() or "JUD",
                predecessors=[x.strip() for x in (row.get("predecessors") or "").split(";") if x.strip()],
                unresolved_reason=reason,
            )
            (unresolved if reason else tasks).append(t)
    return tasks, unresolved


def load_rates(path: Path) -> dict[str, dict]:
    rates: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            role = (row.get("role") or "").strip()
            if not role:
                continue
            rates[role] = {
                "location": (row.get("location") or "").strip(),
                "cost_rate": _num(row.get("cost_rate", "")),
                "bill_rate": _num(row.get("bill_rate", "")),
                "currency": (row.get("currency") or "").strip(),
                "valid_until": (row.get("valid_until") or "").strip(),
                "example": "EXAMPLE" in (row.get("notes") or "").upper() or "EXAMPLE" in (row.get("grade") or "").upper(),
            }
    return rates


def pert_sample(rng: random.Random, o: float, m: float, p: float) -> float:
    if p <= o:
        return m
    a = 1 + PERT_LAMBDA * (m - o) / (p - o)
    b = 1 + PERT_LAMBDA * (p - m) / (p - o)
    return o + rng.betavariate(a, b) * (p - o)


def percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * q
    f = math.floor(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def simulate(tasks: list[Task], iterations: int, seed: int | None) -> dict:
    rng = random.Random(seed)
    groups = sorted({t.driver_group for t in tasks if t.driver_group})
    totals: list[float] = []
    phase_totals: dict[str, list[float]] = defaultdict(list)
    task_samples: dict[str, list[float]] = {t.task_id: [] for t in tasks}
    for _ in range(iterations):
        mult = {g: math.exp(rng.gauss(0.0, GROUP_SIGMA)) for g in groups}
        total = 0.0
        per_phase: dict[str, float] = defaultdict(float)
        for t in tasks:
            v = pert_sample(rng, t.o, t.m, t.p)
            if t.driver_group:
                v *= mult[t.driver_group]
            task_samples[t.task_id].append(v)
            total += v
            per_phase[t.phase] += v
        totals.append(total)
        for ph, v in per_phase.items():
            phase_totals[ph].append(v)
    totals.sort()
    out = {
        "iterations": iterations,
        "total": {q: percentile(totals, q / 100) for q in (10, 50, 80, 90)},
        "mean": statistics.fmean(totals) if totals else 0.0,
        "phases": {},
        "variance": [],
    }
    for ph, vals in phase_totals.items():
        vals.sort()
        out["phases"][ph] = {q: percentile(vals, q / 100) for q in (50, 80, 90)}
    for t in tasks:
        s = sorted(task_samples[t.task_id])
        out["variance"].append({
            "task_id": t.task_id, "task": t.name, "phase": t.phase,
            "p10": percentile(s, 0.10), "p90": percentile(s, 0.90),
            "spread": percentile(s, 0.90) - percentile(s, 0.10),
            "variance": statistics.pvariance(s) if len(s) > 1 else 0.0,
        })
    out["variance"].sort(key=lambda r: r["variance"], reverse=True)
    return out


def staffing(tasks: list[Task]) -> dict:
    by_role_phase: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    phases: list[str] = []
    for t in tasks:
        if t.phase not in phases:
            phases.append(t.phase)
        by_role_phase[t.role][t.phase] += t.pert_mean
    return {"phases": phases, "roles": {r: dict(p) for r, p in by_role_phase.items()}}


def cost_rollup(tasks: list[Task], rates: dict[str, dict], sim: dict) -> dict:
    by_role: dict[str, float] = defaultdict(float)
    for t in tasks:
        by_role[t.role] += t.pert_mean
    total_mean = sum(by_role.values()) or 1.0
    scale50 = sim["total"][50] / total_mean
    scale80 = sim["total"][80] / total_mean
    rows, missing, example_flag = [], [], False
    cost50 = price50 = cost80 = price80 = 0.0
    currency = ""
    for role, pd in sorted(by_role.items()):
        r = rates.get(role)
        if r is None:
            missing.append(role)
            continue
        example_flag = example_flag or r["example"]
        currency = currency or r["currency"]
        cr, br = r["cost_rate"], r["bill_rate"]
        row = {"role": role, "location": r["location"], "pd_p50": pd * scale50, "pd_p80": pd * scale80,
               "cost_rate": cr, "bill_rate": br}
        if cr is not None:
            row["cost_p50"], row["cost_p80"] = pd * scale50 * cr, pd * scale80 * cr
            cost50 += row["cost_p50"]; cost80 += row["cost_p80"]
        if br is not None:
            row["price_p50"], row["price_p80"] = pd * scale50 * br, pd * scale80 * br
            price50 += row["price_p50"]; price80 += row["price_p80"]
        rows.append(row)
    def margin(price: float, cost: float) -> float | None:
        return (price - cost) / price if price else None
    return {"rows": rows, "missing_roles": missing, "currency": currency, "example_rates": example_flag,
            "cost_p50": cost50, "cost_p80": cost80, "price_p50": price50, "price_p80": price80,
            "margin_p50": margin(price50, cost50), "margin_p80": margin(price80, cost80)}


def basis_mix(tasks: list[Task]) -> dict[str, float]:
    tot = sum(t.m for t in tasks) or 1.0
    mix: dict[str, float] = defaultdict(float)
    for t in tasks:
        mix[t.basis] += t.m / tot
    return dict(mix)


def render_md(tasks, unresolved, sim, staff, cost, mix) -> str:
    L: list[str] = []
    tot = sim["total"]
    L.append("# Estimate model output")
    L.append("")
    L.append("## Bottom line")
    L.append("| Statistic | Person-days |")
    L.append("|---|---|")
    for q in (10, 50, 80, 90):
        L.append(f"| P{q} | {tot[q]:,.0f} |")
    L.append(f"| Contingency (P80 − P50) | {tot[80]-tot[50]:,.0f} ({(tot[80]-tot[50])/tot[50]*100 if tot[50] else 0:.0f}%) |")
    L.append(f"| Iterations | {sim['iterations']:,} |")
    L.append("")
    jud = mix.get("JUD", 0.0)
    L.append("## Basis mix (share of most-likely effort)")
    L.append("| Basis | Share |")
    L.append("|---|---|")
    for k, v in sorted(mix.items()):
        L.append(f"| {k} | {v*100:.0f}% |")
    if jud > 0.30:
        L.append("")
        L.append(f"**Flag:** expert judgment covers {jud*100:.0f}% of effort (>30%). Treat as low-confidence; recommend an assessment phase before fixed pricing.")
    L.append("")
    L.append("## By phase")
    L.append("| Phase | P50 | P80 | P90 |")
    L.append("|---|---|---|---|")
    for ph in staff["phases"]:
        s = sim["phases"].get(ph, {50: 0, 80: 0, 90: 0})
        L.append(f"| {ph} | {s[50]:,.0f} | {s[80]:,.0f} | {s[90]:,.0f} |")
    L.append("")
    L.append("## Top variance contributors")
    L.append("| Task | Phase | P10 | P90 | Spread |")
    L.append("|---|---|---|---|---|")
    for r in sim["variance"][:8]:
        L.append(f"| {r['task_id']} {r['task']} | {r['phase']} | {r['p10']:,.0f} | {r['p90']:,.0f} | {r['spread']:,.0f} |")
    L.append("")
    L.append("## Staffing (PERT-mean person-days by role and phase)")
    hdr = "| Role | " + " | ".join(staff["phases"]) + " | Total |"
    L.append(hdr)
    L.append("|" + "---|" * (len(staff["phases"]) + 2))
    for role, per in sorted(staff["roles"].items()):
        cells = [f"{per.get(ph, 0.0):,.0f}" for ph in staff["phases"]]
        L.append(f"| {role} | " + " | ".join(cells) + f" | {sum(per.values()):,.0f} |")
    L.append("")
    if cost is not None:
        cur = cost["currency"] or ""
        L.append("## Cost and price (from supplied rate card)")
        if cost["example_rates"]:
            L.append("**Warning:** rate card contains EXAMPLE placeholder rows. Figures below are not usable; replace with real rates.")
        L.append("| Role | Location | PD @P50 | PD @P80 | Cost @P80 | Price @P80 |")
        L.append("|---|---|---|---|---|---|")
        for r in cost["rows"]:
            L.append(f"| {r['role']} | {r['location']} | {r['pd_p50']:,.0f} | {r['pd_p80']:,.0f} | "
                     f"{r.get('cost_p80', 0):,.0f} | {r.get('price_p80', 0):,.0f} |")
        L.append("")
        L.append("| Metric | @P50 | @P80 |")
        L.append("|---|---|---|")
        L.append(f"| Cost ({cur}) | {cost['cost_p50']:,.0f} | {cost['cost_p80']:,.0f} |")
        L.append(f"| Price ({cur}) | {cost['price_p50']:,.0f} | {cost['price_p80']:,.0f} |")
        m50 = cost["margin_p50"]; m80 = cost["margin_p80"]
        L.append(f"| Gross margin | {'n/a' if m50 is None else f'{m50*100:.0f}%'} | {'n/a' if m80 is None else f'{m80*100:.0f}%'} |")
        if cost["missing_roles"]:
            L.append("")
            L.append("Roles with no rate-card match (excluded from cost; fix the mapping): " + ", ".join(cost["missing_roles"]))
        L.append("")
    else:
        L.append("## Cost and price")
        L.append("No rate card supplied — effort only. Price: [TO BE BASELINED — owner: ___]")
        L.append("")
    if unresolved:
        L.append("## Unresolved tasks (excluded from totals)")
        L.append("| Task | Reason |")
        L.append("|---|---|")
        for t in unresolved:
            L.append(f"| {t.task_id} {t.name} | {t.unresolved_reason} — [TO BE BASELINED — owner: ___] |")
        L.append("")
    L.append(f"Modeled tasks: {len(tasks)}; unresolved: {len(unresolved)}.")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wbs", help="WBS CSV")
    ap.add_argument("--rates", help="Rate card CSV (optional)")
    ap.add_argument("--iterations", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", help="Write Markdown report here (default stdout)")
    ap.add_argument("--json", action="store_true", help="Print JSON summary instead of Markdown")
    args = ap.parse_args(argv)

    wbs_path = Path(args.wbs)
    if not wbs_path.is_file():
        print(f"error: WBS not found: {wbs_path}", file=sys.stderr)
        return 2
    try:
        tasks, unresolved = load_wbs(wbs_path)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if not tasks:
        print("error: no modelable tasks (all rows unresolved or empty)", file=sys.stderr)
        for t in unresolved:
            print(f"  - {t.task_id}: {t.unresolved_reason}", file=sys.stderr)
        return 2
    if args.iterations < 1000:
        print("warning: fewer than 1000 iterations gives unstable percentiles", file=sys.stderr)

    sim = simulate(tasks, args.iterations, args.seed)
    staff = staffing(tasks)
    mix = basis_mix(tasks)
    cost = None
    if args.rates:
        rp = Path(args.rates)
        if not rp.is_file():
            print(f"error: rate card not found: {rp}", file=sys.stderr)
            return 2
        cost = cost_rollup(tasks, load_rates(rp), sim)

    if args.json:
        print(json.dumps({"total": sim["total"], "phases": sim["phases"], "basis_mix": mix,
                          "unresolved": [t.task_id for t in unresolved],
                          "cost": cost}, indent=2, default=float))
        return 0
    md = render_md(tasks, unresolved, sim, staff, cost, mix)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())

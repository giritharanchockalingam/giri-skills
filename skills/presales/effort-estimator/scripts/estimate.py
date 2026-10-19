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
Rates match on role AND location. A role priced at one location matches WBS rows
without a location; a role priced at several locations needs the optional WBS
`location` column (otherwise exit 2). Duplicate (role, location) rows are rejected.
Costs are never summed across currencies: a mixed-currency card needs --currency
plus a sourced --fx CUR=rate per other currency, else exit 2. Expired or unreadable
valid_until dates are flagged. Roles absent from the rate card are listed and
excluded from cost; no rate is ever assumed.

Effort cells must be numbers >= 0; blank or [TO BE BASELINED] marks the task
unresolved; negative, non-finite or other non-numeric values exit 2, as do
duplicate task_id rows. Duration is not computed (effort only) and is reported
as [TO BE BASELINED — owner: Estimation lead]. CSVs may carry a UTF-8 BOM.

Usage:
    python3 -I estimate.py wbs.csv --iterations 20000 --out estimate.md
    python3 -I estimate.py wbs.csv --rates rate-card.csv --seed 7
    python3 -I estimate.py wbs.csv --json          # machine-readable summary
    python3 -I estimate.py wbs.csv --rates card.csv --currency USD --fx INR=0.012

Existing estimate (re-estimate): --previous <estimate.json from the earlier run> adds "Change vs previous
estimate" to the report — P50/P80/P90 and each phase, old → new with the delta, and price at P80 when
both runs were costed in the same currency — so a revised WBS is explained, not just re-quoted.
--draft-only --memo <path>: writes the estimate memo on assets/estimate-summary-template.md's sections
(Bottom line, Basis of estimate, Assumptions, Risks, …) from this run alone, every figure exactly as in
the Markdown report, labelled as a draft (the model step was not run); what the model cannot know is an
owned to-be-baselined marker.

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
from datetime import date
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
    location: str = ""

    @property
    def pert_mean(self) -> float:
        return (self.o + PERT_LAMBDA * self.m + self.p) / (PERT_LAMBDA + 2)

    @property
    def pert_sd(self) -> float:
        return (self.p - self.o) / 6.0


TBD_EST = "[TO BE BASELINED — owner: Estimation lead]"
TBD_FIN = "[TO BE BASELINED — owner: Finance lead]"
PLACEHOLDER_MARKERS = ("TO BE BASELINED", "TBD")


def _num(v: str) -> float | None:
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _effort_value(raw: str | None, where: str, col: str) -> float | None:
    """Parse one effort cell.

    Blank or an explicit placeholder ("[TO BE BASELINED]", "TBD") -> None (the task is
    reported as unresolved). Any other non-numeric, non-finite or negative value is an
    input error: effort cannot be negative and garbage must not be silently dropped.
    """
    s = (raw or "").strip()
    if not s or any(mk in s.upper() for mk in PLACEHOLDER_MARKERS):
        return None
    try:
        v = float(s.replace(",", ""))
    except ValueError:
        raise ValueError(f"{where}: {col} is not a number: {s!r} "
                         "(use a number >= 0, leave it blank, or write [TO BE BASELINED])") from None
    if not math.isfinite(v):
        raise ValueError(f"{where}: {col} is not a finite number: {s!r}")
    if v < 0:
        raise ValueError(f"{where}: {col} must be >= 0 (effort cannot be negative), got {s!r}")
    return v


def _open_csv(path: Path):
    # utf-8-sig strips the BOM Excel writes on "CSV UTF-8" exports; without it the first
    # header becomes "\ufeffrole" and every lookup on that column silently misses.
    return open(path, newline="", encoding="utf-8-sig")


def load_wbs(path: Path) -> tuple[list[Task], list[Task]]:
    tasks: list[Task] = []
    unresolved: list[Task] = []
    seen: dict[str, int] = {}
    with _open_csv(path) as fh:
        rdr = csv.DictReader(fh)
        required = {"task_id", "phase", "task", "role"}
        missing = required - set(rdr.fieldnames or [])
        if missing:
            raise ValueError(f"WBS missing columns: {sorted(missing)}")
        for row in rdr:
            tid = (row.get("task_id") or "").strip()
            if not tid:
                continue
            line = rdr.line_num
            if tid in seen:
                raise ValueError(f"WBS: duplicate task_id '{tid}' (lines {seen[tid]} and {line}); "
                                 "task ids must be unique")
            seen[tid] = line
            where = f"WBS task {tid} (line {line})"
            count = _effort_value(row.get("count"), where, "count")
            uo, um, up = (_effort_value(row.get(k), where, k) for k in ("unit_o", "unit_m", "unit_p"))
            fo, fm, fp = (_effort_value(row.get(k), where, k)
                          for k in ("optimistic", "most_likely", "pessimistic"))
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
                location=(row.get("location") or "").strip(),
            )
            (unresolved if reason else tasks).append(t)
    return tasks, unresolved


def _key(s: str) -> str:
    return " ".join(s.split()).casefold()


def load_rates(path: Path, as_of: date | None = None) -> dict[str, dict[str, dict]]:
    """Rate card keyed by role, then location (both case-insensitive).

    A role may have one row per location (onshore/offshore/...). Two rows for the same
    role AND location are an input error: the previous implementation kept the last one
    silently.
    """
    as_of = as_of or date.today()
    rates: dict[str, dict[str, dict]] = {}
    with _open_csv(path) as fh:
        rdr = csv.DictReader(fh)
        if "role" not in (rdr.fieldnames or []):
            raise ValueError(f"rate card missing column 'role' (found: {rdr.fieldnames})")
        for row in rdr:
            role = (row.get("role") or "").strip()
            if not role:
                continue
            loc = (row.get("location") or "").strip()
            line = rdr.line_num
            by_loc = rates.setdefault(_key(role), {})
            if _key(loc) in by_loc:
                prev = by_loc[_key(loc)]
                raise ValueError(
                    f"rate card: duplicate rows for role '{role}' at location '{loc or '(blank)'}' "
                    f"(lines {prev['line']} and {line}); keep one row per role and location")
            vu = (row.get("valid_until") or "").strip()
            validity = ""
            if vu:
                try:
                    if date.fromisoformat(vu) < as_of:
                        validity = f"expired {vu}"
                except ValueError:
                    validity = f"valid_until not an ISO date: '{vu}'"
            rate = {
                "role": role,
                "location": loc,
                "line": line,
                "cost_rate": _num(row.get("cost_rate", "")),
                "bill_rate": _num(row.get("bill_rate", "")),
                "currency": (row.get("currency") or "").strip().upper(),
                "valid_until": vu,
                "validity_issue": validity,
                "example": "EXAMPLE" in (row.get("notes") or "").upper() or "EXAMPLE" in (row.get("grade") or "").upper(),
            }
            for col in ("cost_rate", "bill_rate"):
                raw = (row.get(col) or "").strip()
                if raw and (rate[col] is None or rate[col] < 0):
                    raise ValueError(f"rate card line {line} ({role}): {col} must be a number >= 0, got {raw!r}")
            by_loc[_key(loc)] = rate
    return rates


def parse_fx(items: list[str]) -> dict[str, float]:
    """--fx INR=0.012 means 1 INR = 0.012 units of the reporting currency."""
    fx: dict[str, float] = {}
    for it in [x for item in (items or []) for x in item.split(",") if x.strip()]:  # repeatable and/or comma list
        cur, sep, val = it.partition("=")
        rate = _num(val) if sep else None
        if not cur.strip() or rate is None or rate <= 0:
            raise ValueError(f"--fx must look like CUR=rate with rate > 0 (1 CUR = rate reporting currency), got {it!r}")
        fx[cur.strip().upper()] = rate
    return fx


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
        label = f"{t.role} ({t.location})" if t.location else t.role
        by_role_phase[label][t.phase] += t.pert_mean
    return {"phases": phases, "roles": {r: dict(p) for r, p in by_role_phase.items()}}


def resolve_rate(task: Task, rates: dict[str, dict[str, dict]]) -> dict | None:
    """Match a task to exactly one rate row on role AND location.

    - task has a location: that (role, location) row, else no match;
    - task has no location: the role's only row; if the role has rows for several
      locations the match is ambiguous and raises (never pick one silently).
    """
    by_loc = rates.get(_key(task.role))
    if not by_loc:
        return None
    if task.location:
        return by_loc.get(_key(task.location))
    if len(by_loc) == 1:
        return next(iter(by_loc.values()))
    locs = sorted(r["location"] or "(blank)" for r in by_loc.values())
    raise ValueError(
        f"rate card has rows for role '{task.role}' at several locations ({', '.join(locs)}) and "
        f"WBS task {task.task_id} does not say which: add a 'location' column to the WBS "
        "(one task row per role and location) so the rate matches on role AND location")


def cost_rollup(tasks: list[Task], rates: dict[str, dict[str, dict]], sim: dict,
                fx: dict[str, float] | None = None, report_currency: str = "") -> dict:
    fx = dict(fx or {})
    groups: dict[tuple[str, str], float] = defaultdict(float)
    rate_for: dict[tuple[str, str], dict] = {}
    missing: list[str] = []
    for t in tasks:
        r = resolve_rate(t, rates)
        if r is None:
            label = f"{t.role} ({t.location})" if t.location else t.role
            if label not in missing:
                missing.append(label)
            continue
        k = (r["role"], r["location"])
        groups[k] += t.pert_mean
        rate_for[k] = r
    all_mean = sum(t.pert_mean for t in tasks) or 1.0
    scale50 = sim["total"][50] / all_mean
    scale80 = sim["total"][80] / all_mean

    used = list(rate_for.values())
    blank_cur = [f"{r['role']} ({r['location'] or 'no location'}), line {r['line']}" for r in used if not r["currency"]]
    if blank_cur:
        raise ValueError("rate card rows used by the WBS have no currency: " + "; ".join(blank_cur)
                         + " — fill the currency column (ISO code)")
    currencies = sorted({r["currency"] for r in used})
    report = (report_currency or "").strip().upper()
    if not report and len(currencies) == 1:
        report = currencies[0]
    if report:
        fx[report] = 1.0
    unconverted = [c for c in currencies if c not in fx]
    if len(currencies) > 1 and not report:
        raise ValueError(
            f"rate card mixes currencies ({', '.join(currencies)}); costs in different currencies are "
            "never summed under one label. Pass --currency <ISO> plus --fx CUR=rate for each other "
            f"currency from a sourced FX rate, or split the rate card. FX: {TBD_FIN}")
    if unconverted:
        raise ValueError(
            f"no FX rate supplied for {', '.join(unconverted)} into reporting currency {report}; "
            f"pass --fx {unconverted[0]}=<rate> (1 {unconverted[0]} = <rate> {report}). FX: {TBD_FIN}")

    rows, example_flag, validity = [], False, []
    cost50 = price50 = cost80 = price80 = 0.0
    for k in sorted(groups):
        r, pd = rate_for[k], groups[k]
        example_flag = example_flag or r["example"]
        if r["validity_issue"]:
            validity.append(f"{r['role']} ({r['location'] or 'no location'}): {r['validity_issue']}")
        conv = fx[r["currency"]]
        cr, br = r["cost_rate"], r["bill_rate"]
        row = {"role": r["role"], "location": r["location"], "pd_p50": pd * scale50, "pd_p80": pd * scale80,
               "cost_rate": cr, "bill_rate": br, "rate_currency": r["currency"], "fx_to_report": conv,
               "valid_until": r["valid_until"], "validity_issue": r["validity_issue"]}
        if cr is not None:
            row["cost_p50"], row["cost_p80"] = pd * scale50 * cr * conv, pd * scale80 * cr * conv
            cost50 += row["cost_p50"]; cost80 += row["cost_p80"]
        if br is not None:
            row["price_p50"], row["price_p80"] = pd * scale50 * br * conv, pd * scale80 * br * conv
            price50 += row["price_p50"]; price80 += row["price_p80"]
        rows.append(row)
    def margin(price: float, cost: float) -> float | None:
        return (price - cost) / price if price else None
    fx_used = {c: fx[c] for c in currencies if c != report}
    return {"rows": rows, "missing_roles": missing, "currency": report, "fx_used": fx_used,
            "example_rates": example_flag, "rate_validity_issues": validity,
            "cost_p50": cost50, "cost_p80": cost80, "price_p50": price50, "price_p80": price80,
            "margin_p50": margin(price50, cost50), "margin_p80": margin(price80, cost80)}


def predecessor_issues(tasks: list[Task], unresolved: list[Task]) -> list[str]:
    known = {t.task_id for t in tasks} | {t.task_id for t in unresolved}
    out = []
    for t in tasks + unresolved:
        for pr in t.predecessors:
            if pr not in known:
                out.append(f"{t.task_id} -> unknown predecessor '{pr}'")
    return out


def basis_mix(tasks: list[Task]) -> dict[str, float]:
    tot = sum(t.m for t in tasks) or 1.0
    mix: dict[str, float] = defaultdict(float)
    for t in tasks:
        mix[t.basis] += t.m / tot
    return dict(mix)


def render_md(tasks, unresolved, sim, staff, cost, mix, pred_issues=None) -> str:
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
    L.append("## Duration")
    L.append(f"Not computed by this model: figures here are effort in person-days. Duration: {TBD_EST} — "
             "derive it from the critical path (task predecessors) and the staffing plan; "
             "duration is not effort divided by team size.")
    for msg in pred_issues or []:
        L.append(f"- Dependency check: {msg}")
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
        for v in cost["rate_validity_issues"]:
            L.append(f"**Warning:** rate validity — {v}. Refresh the rate before quoting; {TBD_FIN}")
        if cost["fx_used"]:
            L.append("FX applied (supplied via --fx; 1 unit = rate in " + cur + "): "
                     + ", ".join(f"{c} {v:g}" for c, v in sorted(cost["fx_used"].items())))
        L.append(f"| Role | Location | Rate currency | PD @P50 | PD @P80 | Cost @P80 ({cur}) | Price @P80 ({cur}) |")
        L.append("|---|---|---|---|---|---|---|")
        for r in cost["rows"]:
            L.append(f"| {r['role']} | {r['location']} | {r['rate_currency']} | {r['pd_p50']:,.0f} | {r['pd_p80']:,.0f} | "
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
        L.append("No rate card supplied — effort only. Price: [TO BE BASELINED — owner: Estimation lead]")
        L.append("")
    if unresolved:
        L.append("## Unresolved tasks (excluded from totals)")
        L.append("| Task | Reason |")
        L.append("|---|---|")
        for t in unresolved:
            L.append(f"| {t.task_id} {t.name} | {t.unresolved_reason} — [TO BE BASELINED — owner: Estimation lead] |")
        L.append("")
    L.append(f"Modeled tasks: {len(tasks)}; unresolved: {len(unresolved)}.")
    return "\n".join(L)


def load_previous(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("total"), dict):
        raise ValueError(f"{path.name} is not an estimate.json from this script (no 'total')")
    tot = {int(k): float(v) for k, v in data["total"].items()}
    phases = {ph: {int(k): float(v) for k, v in vals.items()} for ph, vals in (data.get("phases") or {}).items()}
    cost = data.get("cost") or None
    return {"total": tot, "phases": phases, "cost": cost}


def change_lines(prev: dict, sim: dict, staff: dict, cost) -> list[str]:
    def row(label, old, new):
        if old is None:
            return f"| {label} | — | {new:,.0f} | new |"
        if new is None:
            return f"| {label} | {old:,.0f} | — | removed |"
        d = new - old
        return f"| {label} | {old:,.0f} | {new:,.0f} | {'+' if d >= 0 else '−'}{abs(d):,.0f} |"
    L = ["## Change vs previous estimate", "| Item | Previous | Now | Change |", "|---|---|---|---|"]
    for q in (50, 80, 90):
        L.append(row(f"Total P{q} (pd)", prev["total"].get(q), sim["total"][q]))
    for ph in list(staff["phases"]) + [ph for ph in prev["phases"] if ph not in staff["phases"]]:
        old = prev["phases"].get(ph, {}).get(80)
        new = sim["phases"].get(ph, {}).get(80) if ph in staff["phases"] else None
        L.append(row(f"{ph} P80 (pd)", old, new))
    pc = prev.get("cost")
    if cost is not None and pc and pc.get("currency") == cost.get("currency") and pc.get("price_p80") is not None:
        L.append(row(f"Price @P80 ({cost['currency']})", float(pc["price_p80"]), cost["price_p80"]))
    else:
        L.append(f"| Price @P80 | not compared | | {TBD_EST} (both runs need a rate card in the same currency) |")
    L.append("")
    return L


def render_memo(sim, staff, cost, mix, unresolved, change: list[str] | None, client: str = "") -> str:
    """Estimate memo (no model step): every figure exactly as render_md prints it."""
    tot = sim["total"]
    cont = tot[80] - tot[50]
    cur = (cost or {}).get("currency") or ""
    jud = mix.get("JUD", 0.0)
    L = [f"# Estimate Memo — {client or TBD_EST} — draft", "",
         "> Script draft — the model step was not run (draft only): figures are copied from `estimate.md`; "
         "judgements are owned markers.", "",
         "## Bottom line", "| Item | Value | Basis |", "|---|---|---|",
         f"| Effort quoted | {tot[80]:,.0f} person-days at P80 (P50 {tot[50]:,.0f}, P90 {tot[90]:,.0f}) | "
         f"`scripts/estimate.py`, {sim['iterations']:,} iterations |",
         f"| Confidence level used | {TBD_EST} | commercial model not supplied |",
         f"| Duration | {TBD_EST} | the model computes effort only |",
         f"| Price | " + (f"{cost['price_p80']:,.0f} {cur} at P80" if cost is not None else f"pending rate card — {TBD_EST}")
         + " | supplied rate card |",
         f"| Contingency | P80 − P50 = {cont:,.0f} person-days ({cont / tot[50] * 100 if tot[50] else 0:.0f}%) | shown as a line |",
         "| Basis mix | " + " · ".join(f"{k} {v * 100:.0f}%" for k, v in sorted(mix.items())) + " | "
         + ("flag: judgment above 30%" if jud > 0.30 else "within the 30% judgment limit") + " |", "",
         "## Basis of estimate", "| Phase | P50 (pd) | P80 (pd) | P90 (pd) |", "|---|---|---|---|"]
    for ph in staff["phases"]:
        s_ = sim["phases"].get(ph, {50: 0, 80: 0, 90: 0})
        L.append(f"| {ph} | {s_[50]:,.0f} | {s_[80]:,.0f} | {s_[90]:,.0f} |")
    L += [f"| **Total** | {tot[50]:,.0f} | {tot[80]:,.0f} | {tot[90]:,.0f} |", ""]
    if change:
        L += change
    L += ["## Assumptions", "| ID | Assumption | Source |", "|---|---|---|",
          "| A-01 | Driver counts and unit efforts are as in the WBS | WBS basis and notes columns |",
          f"| A-02 | Client SME availability | {TBD_EST} |",
          f"| A-03 | Environments ready before the build phase | {TBD_EST} |",
          "| A-04 | Rates as on the supplied rate card | " + ("rate card valid_until column" if cost is not None else TBD_EST) + " |", "",
          "## Risks to the estimate and de-risking", "| Risk | Effect on estimate | De-risk action | Owner |", "|---|---|---|---|"]
    for r in sim["variance"][:3]:
        L.append(f"| {r['task_id']} {r['task']} | spread {r['spread']:,.0f} pd (P10 {r['p10']:,.0f} → P90 {r['p90']:,.0f}) | "
                 f"{TBD_EST} | {TBD_EST} |")
    if jud > 0.30:
        L.append(f"| Expert judgment covers {jud * 100:.0f}% of effort | low confidence in the totals | "
                 f"assessment phase before fixed pricing | {TBD_EST} |")
    if unresolved:
        L.append(f"| Unresolved WBS rows excluded from totals | totals are understated | baseline the rows | {TBD_EST} |")
    L += ["", "## Exclusions", f"{TBD_EST}", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wbs", help="WBS CSV")
    ap.add_argument("--rates", help="Rate card CSV (optional)")
    ap.add_argument("--iterations", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", help="Write Markdown report here (default stdout)")
    ap.add_argument("--json", action="store_true", help="Print JSON summary instead of Markdown")
    ap.add_argument("--currency", default="", help="Reporting currency when the rate card mixes currencies")
    ap.add_argument("--fx", action="append", default=[], metavar="CUR=RATE",
                    help="Sourced FX rate into the reporting currency (1 CUR = RATE); repeatable")
    ap.add_argument("--as-of", default="", help="Date (YYYY-MM-DD) for rate validity checks; default today")
    ap.add_argument("--previous", default="", help="estimate.json of the earlier run, for the change section")
    ap.add_argument("--memo", default="", help="estimate memo path (written with --draft-only)")
    ap.add_argument("--draft-only", action="store_true", help="no model step: write --memo from this run")
    ap.add_argument("--client", default="", help="client name for the memo title")
    args = ap.parse_args(argv)

    wbs_path = Path(args.wbs)
    if not wbs_path.is_file():
        print(f"error: WBS not found: {wbs_path}", file=sys.stderr)
        return 2
    try:
        tasks, unresolved = load_wbs(wbs_path)
    except UnicodeDecodeError:  # subclass of ValueError: must come first
        print(f"error: {wbs_path} is not a UTF-8 CSV file (save it as 'CSV UTF-8')", file=sys.stderr)
        return 2
    except (ValueError, csv.Error) as e:
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
        try:
            as_of = date.fromisoformat(args.as_of) if args.as_of else None
            fx = parse_fx(args.fx)
            cost = cost_rollup(tasks, load_rates(rp, as_of), sim, fx, args.currency)
        except UnicodeDecodeError:  # subclass of ValueError: must come first
            print(f"error: {rp} is not a UTF-8 CSV file (save it as 'CSV UTF-8')", file=sys.stderr)
            return 2
        except (ValueError, csv.Error) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        for v in cost["rate_validity_issues"]:
            print(f"warning: rate validity — {v}", file=sys.stderr)
    preds = predecessor_issues(tasks, unresolved)
    for msg in preds:
        print(f"warning: {msg}", file=sys.stderr)
    change = None
    if args.previous:
        pp = Path(args.previous)
        if not pp.is_file():
            print(f"error: previous estimate not found: {pp}", file=sys.stderr)
            return 2
        try:
            change = change_lines(load_previous(pp), sim, staffing(tasks), cost)
        except (ValueError, TypeError, AttributeError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps({"total": sim["total"], "phases": sim["phases"], "basis_mix": mix,
                          "unresolved": [t.task_id for t in unresolved],
                          "duration": TBD_EST, "dependency_issues": preds,
                          "cost": cost}, indent=2, default=float))
        return 0
    md = render_md(tasks, unresolved, sim, staff, cost, mix, preds)
    if change:
        md = md.replace("## Duration", "\n".join(change) + "\n## Duration", 1)
    if args.draft_only and args.memo:
        Path(args.memo).write_text(render_memo(sim, staff, cost, mix, unresolved, change, args.client), encoding="utf-8")
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())

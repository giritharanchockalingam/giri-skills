#!/usr/bin/env python3
"""Value model: benefits.csv + costs.csv -> yearly cash flows, NPV, payback, P80 cost, sensitivity.

    python3 -I scripts/value_model.py benefits.csv costs.csv --years 5 --discount-rate 0.08 \
        --p80-cost-uplift 0.15 --json value-model.json --out value-case.md

benefits.csv columns: benefit_id, name, driver, unit_value, units_per_year, ramp_pct_y1,
    ramp_pct_y2, ramp_pct_y3, source      (ramp after year 3 = ramp_pct_y3)
costs.csv columns:    cost_id, name, one_time, run_rate_per_year, start_year, source

Rules: no number is invented. A blank unit_value / units_per_year excludes the benefit from the
headline and lists it as [TO BE BASELINED — owner: ___]; a blank source is reported the same way.
Without --discount-rate the NPV is a marker; without --p80-cost-uplift the P80 cost is a marker.
Totals in the JSON equal the sum of the yearly rows (reconciliation is asserted before writing).
Exit 1 on missing columns, non-numeric cells or an unreadable file. Stdlib only, offline.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

TBD = "[TO BE BASELINED — owner: ___]"
BENEFIT_COLS = ["benefit_id", "name", "driver", "unit_value", "units_per_year",
                "ramp_pct_y1", "ramp_pct_y2", "ramp_pct_y3", "source"]
COST_COLS = ["cost_id", "name", "one_time", "run_rate_per_year", "start_year", "source"]
SENS_PCT = 20


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def read_csv(path: Path, cols: list[str]) -> list[dict]:
    if not path.is_file():
        die(f"file not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        die(f"{path.name}: no data rows")
    missing = [c for c in cols if c not in rows[0]]
    if missing:
        die(f"{path.name}: missing columns {missing}")
    return [{k: (v or "").strip() for k, v in r.items() if k} for r in rows]


def num(row: dict, col: str, where: str, default=None):
    """Float or None for blank; exit 1 on non-numeric."""
    raw = row.get(col, "")
    if raw == "":
        return default
    try:
        return float(raw.replace(",", "").replace("$", "").replace("%", ""))
    except ValueError:
        die(f"{where}: non-numeric {col}={raw!r}")


def r2(x: float) -> float:
    return round(x + 0.0, 2)


def fmt(x) -> str:
    if x is None:
        return TBD
    if isinstance(x, str):
        return x
    return f"{int(round(x)):,}" if abs(x - round(x)) < 0.005 else f"{x:,.2f}"


def model(benefits, costs, years, rate, uplift):
    out_b, out_c = [], []
    for b in benefits:
        where = f"benefit {b['benefit_id'] or '?'}"
        uv, upy = num(b, "unit_value", where), num(b, "units_per_year", where)
        ramps = [num(b, f"ramp_pct_y{i}", where, 100.0) for i in (1, 2, 3)]
        yearly = []
        if uv is not None and upy is not None:
            for y in range(1, years + 1):
                ramp = ramps[min(y, 3) - 1]
                yearly.append(r2(uv * upy * ramp / 100.0))
        out_b.append({"benefit_id": b["benefit_id"], "name": b["name"], "driver": b["driver"],
                      "unit_value": uv, "units_per_year": upy, "ramp_pct": ramps,
                      "source": b["source"] or TBD, "in_headline": bool(yearly),
                      "yearly": [0.0] + yearly if yearly else None,
                      "total": r2(sum(yearly)) if yearly else None})
    for c in costs:
        where = f"cost {c['cost_id'] or '?'}"
        one, run = num(c, "one_time", where), num(c, "run_rate_per_year", where)
        start = int(num(c, "start_year", where, 0.0))
        if start < 0 or start > years:
            die(f"{where}: start_year {start} outside 0..{years}")
        yearly = None
        if one is not None or run is not None:
            yearly = [0.0] * (years + 1)
            if one is not None:
                yearly[start] += one
            if run is not None:
                for y in range(max(start, 1), years + 1):
                    yearly[y] += run
            yearly = [r2(v) for v in yearly]
        out_c.append({"cost_id": c["cost_id"], "name": c["name"], "one_time": one,
                      "run_rate_per_year": run, "start_year": start, "source": c["source"] or TBD,
                      "in_headline": yearly is not None, "yearly": yearly,
                      "total": r2(sum(yearly)) if yearly else None})

    ben_y = [r2(sum(b["yearly"][y] for b in out_b if b["yearly"])) for y in range(years + 1)]
    cost_y = [r2(sum(c["yearly"][y] for c in out_c if c["yearly"])) for y in range(years + 1)]
    net_y = [r2(b - c) for b, c in zip(ben_y, cost_y)]
    cum, cum_y = 0.0, []
    for n in net_y:
        cum = r2(cum + n)
        cum_y.append(cum)
    payback = None
    for y in range(1, years + 1):
        if cum_y[y] >= 0 and cum_y[y - 1] < 0 and net_y[y] > 0:
            frac = -cum_y[y - 1] / net_y[y]
            payback = int(round(12 * (y - 1) + 12 * frac))
            break
        if cum_y[y] >= 0 and y == 1 and cum_y[0] >= 0:
            payback = 0
            break
    npv = r2(sum(n / (1 + rate) ** y for y, n in enumerate(net_y))) if rate is not None else None
    total_cost = r2(sum(cost_y))
    p80 = r2(total_cost * (1 + uplift)) if uplift is not None else None

    headline = [b for b in out_b if b["in_headline"]]
    top3 = sorted(headline, key=lambda b: -b["total"])[:3]
    total_net = r2(sum(net_y))
    sens = []
    for b in top3:
        lo = r2(total_net - b["total"] * SENS_PCT / 100.0)
        hi = r2(total_net + b["total"] * SENS_PCT / 100.0)
        # break-even factor f: f * total_b + (total_net - total_b) = 0
        f = 1 - total_net / b["total"] if b["total"] else None
        be_unit = r2(b["unit_value"] * f) if f is not None and f > 0 else None
        sens.append({"benefit_id": b["benefit_id"], "name": b["name"], "total": b["total"],
                     "net_minus": lo, "net_base": total_net, "net_plus": hi,
                     "break_even_factor": r2(f) if f is not None else None,
                     "break_even_unit_value": be_unit,
                     "holds_at_zero": bool(f is not None and f <= 0)})

    # reconciliation: totals are sums of the yearly rows
    assert r2(sum(ben_y)) == r2(sum(b["total"] for b in headline)) or not headline
    assert abs(r2(sum(net_y)) - r2(sum(ben_y) - sum(cost_y))) < 0.01

    excluded = [b for b in out_b if not b["in_headline"]] + [c for c in out_c if not c["in_headline"]]
    unsourced = [x for x in out_b + out_c if x["source"] == TBD]
    return {"years": years, "discount_rate": rate, "p80_cost_uplift": uplift, "sensitivity_pct": SENS_PCT,
            "discount_rate_pct": r2(rate * 100) if rate is not None else None,
            "p80_cost_uplift_pct": r2(uplift * 100) if uplift is not None else None,
            "benefits": out_b, "costs": out_c,
            "yearly": [{"year": y, "benefits": ben_y[y], "costs": cost_y[y], "net": net_y[y],
                        "cumulative": cum_y[y]} for y in range(years + 1)],
            "headline_valid": bool(headline),
            "totals": {"benefits": r2(sum(ben_y)), "costs": total_cost, "net": total_net,
                       "npv": npv, "p80_cost": p80, "payback_month": payback},
            "sensitivity": sens,
            "excluded_from_headline": [x.get("benefit_id") or x.get("cost_id") for x in excluded],
            "unsourced": [x.get("benefit_id") or x.get("cost_id") for x in unsourced]}


def render(m: dict, client: str) -> str:
    t, yrs = m["totals"], m["years"]
    rate_txt = f"{m['discount_rate'] * 100:g}%" if m["discount_rate"] is not None else TBD
    npv_txt = fmt(t["npv"]) if m["discount_rate"] is not None else f"{TBD} (no sourced discount rate)"
    p80_txt = fmt(t["p80_cost"]) if m["p80_cost_uplift"] is not None else f"{TBD} (no P80 uplift supplied)"
    pay = f"month {t['payback_month']}" if t["payback_month"] is not None else "not within horizon"
    n_head = sum(b["in_headline"] for b in m["benefits"])
    net_txt = fmt(t["net"]) if n_head else f"{TBD} (no baselined benefit; this is not a value case yet)"
    if not n_head:
        npv_txt, pay = TBD, TBD
    L = [f"# Value Case — {client} — {yrs}-year model", "",
         "## Bottom line", "| Item | Value |", "|---|---|",
         f"| {yrs}-year net (undiscounted) | {net_txt} |",
         f"| NPV at {rate_txt} | {npv_txt} |",
         f"| Payback | {pay} |",
         f"| Total cost (P50 basis) | {fmt(t['costs'])} |",
         f"| P80 cost | {p80_txt} |",
         f"| Benefits in headline | {n_head} of {len(m['benefits'])} |",
         f"| Excluded (unbaselined) | {', '.join(m['excluded_from_headline']) or 'none'} |", ""]
    L += ["## Cash flows", "| Year | Benefits | Costs | Net | Cumulative |", "|---|---|---|---|---|"]
    for y in m["yearly"]:
        L.append(f"| {y['year']} | {fmt(y['benefits'])} | {fmt(y['costs'])} | {fmt(y['net'])} | {fmt(y['cumulative'])} |")
    L.append(f"| **Total** | {fmt(t['benefits'])} | {fmt(t['costs'])} | {fmt(t['net'])} | |")
    L += ["", "## Benefits", "| ID | Benefit | Driver | Unit value | Units / yr | Ramp Y1/Y2/Y3 | Total | Source |",
          "|---|---|---|---|---|---|---|---|"]
    for b in m["benefits"]:
        ramp = "/".join(f"{r:g}%" for r in b["ramp_pct"])
        L.append(f"| {b['benefit_id']} | {b['name']} | {b['driver']} | {fmt(b['unit_value'])} | "
                 f"{fmt(b['units_per_year'])} | {ramp} | {fmt(b['total'])} | {b['source']} |")
    L += ["", "## Costs", "| ID | Cost | One-time | Run-rate / yr | Start year | Total | Source |",
          "|---|---|---|---|---|---|---|"]
    for c in m["costs"]:
        one = fmt(c["one_time"]) if c["one_time"] is not None or not c["in_headline"] else "—"
        run = fmt(c["run_rate_per_year"]) if c["run_rate_per_year"] is not None or not c["in_headline"] else "—"
        L.append(f"| {c['cost_id']} | {c['name']} | {one} | {run} | "
                 f"{c['start_year']} | {fmt(c['total'])} | {c['source']} |")
    L += ["", f"## Sensitivity (±{SENS_PCT}% on top-3 benefits by value)",
          f"| Benefit | Net at −{SENS_PCT}% | Net base | Net at +{SENS_PCT}% | Break-even unit value |",
          "|---|---|---|---|---|"]
    for s in m["sensitivity"]:
        be = ("case holds even at zero" if s["holds_at_zero"]
              else (fmt(s["break_even_unit_value"]) if s["break_even_unit_value"] is not None else TBD))
        L.append(f"| {s['benefit_id']} {s['name']} | {fmt(s['net_minus'])} | {fmt(s['net_base'])} | "
                 f"{fmt(s['net_plus'])} | {be} |")
    if not m["sensitivity"]:
        L.append(f"| no baselined benefits | {TBD} | {TBD} | {TBD} | {TBD} |")
    L += ["", "## Sources", "| ID | Item | Source |", "|---|---|---|"]
    for x in m["benefits"]:
        L.append(f"| {x['benefit_id']} | {x['name']} | {x['source']} |")
    for x in m["costs"]:
        L.append(f"| {x['cost_id']} | {x['name']} | {x['source']} |")
    if m["unsourced"]:
        L += ["", f"Unsourced rows (not CFO-grade until baselined): {', '.join(m['unsourced'])}."]
    L += ["", "## Assumptions",
          f"- Horizon: {yrs} years; year 0 carries one-time costs only.",
          f"- Ramp after year 3 equals the year-3 ramp. Sensitivity flexes each top benefit ±{SENS_PCT}%.",
          f"- Discount rate: {rate_txt}. P80 uplift on cost: "
          + (f"{m['p80_cost_uplift'] * 100:g}%" if m["p80_cost_uplift"] is not None else TBD) + ".", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="Value model: benefits + costs -> cash flows, NPV, payback, sensitivity")
    ap.add_argument("benefits", help="benefits.csv")
    ap.add_argument("costs", help="costs.csv")
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--discount-rate", type=float, default=None, help="e.g. 0.08; omit -> NPV marked TBD")
    ap.add_argument("--p80-cost-uplift", type=float, default=None, help="e.g. 0.15; omit -> P80 cost marked TBD")
    ap.add_argument("--client", default="<Client>")
    ap.add_argument("--json", dest="json_out", default="", help="write value-model.json")
    ap.add_argument("--out", default="", help="write value-case.md")
    a = ap.parse_args()
    if a.years < 1 or a.years > 20:
        die("--years must be 1..20")
    if a.discount_rate is not None and not (0 <= a.discount_rate < 1):
        die("--discount-rate must be a fraction in [0, 1)")
    if a.p80_cost_uplift is not None and a.p80_cost_uplift < 0:
        die("--p80-cost-uplift must be >= 0")
    benefits = read_csv(Path(a.benefits), BENEFIT_COLS)
    costs = read_csv(Path(a.costs), COST_COLS)
    m = model(benefits, costs, a.years, a.discount_rate, a.p80_cost_uplift)
    m["client"] = a.client
    if a.json_out:
        Path(a.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json_out).write_text(json.dumps(m, indent=2), encoding="utf-8")
    md = render(m, a.client)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(md, encoding="utf-8")
    if not a.out and not a.json_out:
        print(md)
    else:
        t = m["totals"]
        print(f"value model: {a.years}y net {fmt(t['net'])}, payback "
              f"{t['payback_month'] if t['payback_month'] is not None else 'n/a'} months, "
              f"{len(m['excluded_from_headline'])} excluded, {len(m['unsourced'])} unsourced")
    return 0


if __name__ == "__main__":
    main()

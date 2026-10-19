#!/usr/bin/env python3
"""Value model: benefits.csv + costs.csv -> yearly cash flows, NPV, payback, P80 cost, sensitivity.

    python3 -I scripts/value_model.py benefits.csv costs.csv --years 5 --discount-rate 0.08 \
        --p80-cost-uplift 0.15 --json value-model.json --out value-case.md

benefits.csv columns: benefit_id, name, driver, unit_value, units_per_year, ramp_pct_y1,
    ramp_pct_y2, ramp_pct_y3, source      (ramp after year 3 = ramp_pct_y3)
costs.csv columns:    cost_id, name, one_time, run_rate_per_year, start_year, source

Rules: no number is invented. A blank unit_value / units_per_year excludes the benefit from the
headline and lists it as [TO BE BASELINED — owner: Finance lead]; a blank source is reported the same way.
Without --discount-rate the NPV is a marker; without --p80-cost-uplift the P80 cost is a marker.
Totals in the JSON equal the sum of the yearly rows (reconciliation is asserted before writing).
A blank ramp_pct_y1..y3 is not assumed to be 100%: the benefit is excluded from the headline and its
ramp is marked TBD. Rows that are entirely blank (e.g. ",,,," from Excel) are skipped; duplicate ids,
a blank id on a data row, non-integer start_year and non-finite numbers are input errors.
Refresh (--previous value-model.json of the earlier case): adds "Change vs previous value case" — the
headline totals (benefits, costs, net, NPV, P80 cost, payback month) previous → now with the change,
and each benefit added, removed, re-estimated, newly baselined or dropped — stored in value-model.json
as `change` so every figure in the section traces to it.
Exit 2 on missing columns, non-numeric cells, duplicate ids or an unreadable / non-UTF-8 file
(repo convention). Stdlib only, offline.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

TBD = "[TO BE BASELINED — owner: Finance lead]"
BENEFIT_COLS = ["benefit_id", "name", "driver", "unit_value", "units_per_year",
                "ramp_pct_y1", "ramp_pct_y2", "ramp_pct_y3", "source"]
COST_COLS = ["cost_id", "name", "one_time", "run_rate_per_year", "start_year", "source"]
SENS_PCT = 20


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def read_csv(path: Path, cols: list[str]) -> list[dict]:
    if not path.is_file():
        die(f"file not found: {path}")
    try:
        with path.open(encoding="utf-8-sig", newline="") as f:
            rdr = csv.DictReader(f)
            header = rdr.fieldnames or []
            raw = [(rdr.line_num, r) for r in rdr]
    except UnicodeDecodeError:
        die(f"{path.name}: not a UTF-8 CSV file (save it as 'CSV UTF-8')")
    except csv.Error as e:
        die(f"{path.name}: unreadable CSV ({e})")
    missing = [c for c in cols if c not in header]
    if missing:
        die(f"{path.name}: missing columns {missing}")
    id_col = cols[0]
    rows, seen = [], {}
    for line, r in raw:
        row = {k: (v or "").strip() for k, v in r.items() if k}
        if not any(row.values()):
            continue  # all-blank row (",,,," from spreadsheet exports)
        rid = row.get(id_col, "")
        if not rid:
            die(f"{path.name} line {line}: blank {id_col} on a data row")
        if rid in seen:
            die(f"{path.name}: duplicate {id_col} '{rid}' (lines {seen[rid]} and {line}); "
                "each line must be counted once")
        seen[rid] = line
        rows.append(row)
    if not rows:
        die(f"{path.name}: no data rows")
    return rows


def num(row: dict, col: str, where: str, default=None):
    """Float or None for blank; exit 2 on non-numeric or non-finite."""
    raw = row.get(col, "")
    if raw == "":
        return default
    try:
        v = float(raw.replace(",", "").replace("$", "").replace("%", ""))
    except ValueError:
        die(f"{where}: non-numeric {col}={raw!r}")
    if not math.isfinite(v):
        die(f"{where}: {col}={raw!r} is not a finite number")
    return v


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
        ramps = [num(b, f"ramp_pct_y{i}", where) for i in (1, 2, 3)]
        ramp_missing = None in ramps[:min(years, 3)]
        yearly = []
        if uv is not None and upy is not None and not ramp_missing:
            for y in range(1, years + 1):
                ramp = ramps[min(y, 3) - 1]
                yearly.append(r2(uv * upy * ramp / 100.0))
        out_b.append({"benefit_id": b["benefit_id"], "name": b["name"], "driver": b["driver"],
                      "unit_value": uv, "units_per_year": upy, "ramp_pct": ramps,
                      "ramp_tbd": ramp_missing,
                      "source": b["source"] or TBD, "in_headline": bool(yearly),
                      "yearly": [0.0] + yearly if yearly else None,
                      "total": r2(sum(yearly)) if yearly else None})
    for c in costs:
        where = f"cost {c['cost_id'] or '?'}"
        one, run = num(c, "one_time", where), num(c, "run_rate_per_year", where)
        start_f = num(c, "start_year", where, 0.0)
        if not float(start_f).is_integer():
            die(f"{where}: start_year must be a whole year, got {c.get('start_year')!r}")
        start = int(start_f)
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

    # reconciliation: totals are sums of the yearly rows (explicit checks, not asserts: they must
    # also hold under python -O and must never surface as a traceback)
    if not all(math.isfinite(v) for v in ben_y + cost_y + net_y + cum_y + [total_net]):
        die("values too large to model (a total overflowed); check the units of the input figures")
    if headline and abs(r2(sum(ben_y)) - r2(sum(b["total"] for b in headline))) >= 0.01:
        die("internal reconciliation failed: yearly benefits do not sum to benefit totals")
    if abs(r2(sum(net_y)) - r2(sum(ben_y) - sum(cost_y))) >= 0.01:
        die("internal reconciliation failed: net does not equal benefits minus costs")

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


def change_vs(prev: dict, m: dict) -> dict:
    """Previous value-model.json vs this run: headline items and each benefit, with deltas."""
    pt, t = prev.get("totals") or {}, m["totals"]
    rows = []
    for key, label in (("benefits", "Benefits (5-year)" if m["years"] == 5 else "Benefits"), ("costs", "Costs (P50 basis)"),
                       ("net", "Net (undiscounted)"), ("npv", "NPV"), ("p80_cost", "P80 cost"),
                       ("payback_month", "Payback month")):
        old, new = pt.get(key), t.get(key)
        rows.append({"item": label, "previous": old, "now": new,
                     "delta": r2(new - old) if isinstance(old, (int, float)) and isinstance(new, (int, float)) else None})
    before = {b["benefit_id"]: b for b in prev.get("benefits") or []}
    bens = []
    for b in m["benefits"]:
        o = before.get(b["benefit_id"])
        if o is None:
            status = "added"
        elif o.get("total") is None and b["total"] is not None:
            status = "now baselined (enters the headline)"
        elif o.get("total") is not None and b["total"] is None:
            status = "dropped from the headline (no longer baselined)"
        elif o.get("total") != b["total"]:
            status = "re-estimated"
        else:
            status = "unchanged"
        bens.append({"benefit_id": b["benefit_id"], "name": b["name"], "previous_total": o.get("total") if o else None,
                     "now_total": b["total"], "status": status,
                     "delta": r2(b["total"] - o["total"]) if o and o.get("total") is not None and b["total"] is not None else None})
    for bid, o in before.items():
        if bid not in {b["benefit_id"] for b in m["benefits"]}:
            bens.append({"benefit_id": bid, "name": o.get("name", ""), "previous_total": o.get("total"), "now_total": None,
                         "status": "removed", "delta": None})
    return {"previous_client": prev.get("client", ""), "rows": rows, "benefits": bens}


def render_change(ch: dict) -> list[str]:
    def f(v):
        return fmt(v) if v is not None else "—"

    def d(v):
        return "—" if v is None else ("+" if v >= 0 else "−") + fmt(abs(v))
    L = ["## Change vs previous value case", "| Item | Previous | Now | Change |", "|---|---|---|---|"]
    L += [f"| {r['item']} | {f(r['previous'])} | {f(r['now'])} | {d(r['delta'])} |" for r in ch["rows"]]
    L += ["", "| Benefit | Previous total | Now total | Change | Status |", "|---|---|---|---|---|"]
    L += [f"| {b['benefit_id']} {b['name']} | {f(b['previous_total'])} | {f(b['now_total'])} | {d(b['delta'])} | {b['status']} |"
          for b in ch["benefits"]]
    return L + [""]


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
    if m.get("change"):
        L += render_change(m["change"])
    L += ["## Cash flows", "| Year | Benefits | Costs | Net | Cumulative |", "|---|---|---|---|---|"]
    for y in m["yearly"]:
        L.append(f"| {y['year']} | {fmt(y['benefits'])} | {fmt(y['costs'])} | {fmt(y['net'])} | {fmt(y['cumulative'])} |")
    L.append(f"| **Total** | {fmt(t['benefits'])} | {fmt(t['costs'])} | {fmt(t['net'])} | |")
    L += ["", "## Benefits", "| ID | Benefit | Driver | Unit value | Units / yr | Ramp Y1/Y2/Y3 | Total | Source |",
          "|---|---|---|---|---|---|---|---|"]
    for b in m["benefits"]:
        if all(r is None for r in b["ramp_pct"]):
            ramp = TBD
        else:
            ramp = "/".join(f"{r:g}%" if r is not None else "—" for r in b["ramp_pct"])
            if b["ramp_tbd"]:
                ramp += f" (blank ramp {TBD})"
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
    ap.add_argument("--previous", default="", help="value-model.json of the previous value case, for the change section")
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
    if a.previous:
        pp = Path(a.previous)
        if not pp.is_file():
            die(f"previous value model not found: {pp}")
        try:
            prev = json.loads(pp.read_text(encoding="utf-8"))
        except ValueError as e:
            die(f"previous value model is not valid JSON: {e}")
        if not isinstance(prev, dict) or not isinstance(prev.get("totals"), dict) or not isinstance(prev.get("benefits"), list):
            die("previous value model is not a value-model.json from this script (needs totals and benefits)")
        m["change"] = change_vs(prev, m)
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
    sys.exit(main())

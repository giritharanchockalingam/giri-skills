#!/usr/bin/env python3
"""TCO table from a scored inventory + user-supplied rate inputs. No default prices.

Inputs
  scored inventory CSV (from score_inventory.py): needs `band` (Simple / Medium / Complex /
    Very complex); `retire_candidate` (true/false) rows are excluded from migration counts.
  rates CSV: key,value[,unit,source,notes] — every amount is annual unless stated. Keys:
    currency                         ISO code (default USD)
    current_licence                  current platform licence per year
    current_infrastructure           current hosting per year
    current_run_team                 current run/support team per year
    current_support_contract         vendor support per year
    target_licence, target_infrastructure, target_run_team, target_support_contract
    unit_cost_simple, unit_cost_medium, unit_cost_complex, unit_cost_very_complex
                                     one-time migration cost per interface by band
    training_one_time, decommission_one_time
    dual_run_months                  months both platforms run (target pays both run-rates)
    decommission_month               month (from start) the current platform is switched off;
                                     current-platform costs in `target` stop after it
    horizon_years                    default 3 (max 5)
  A key that is absent or blank makes every line that needs it
  `[TO BE BASELINED — owner: Integration architect]`; a derived total that touches such a line is reported the
  same way, never as a number (assets/tco-model-spec.md).

Outputs
  --out tco.csv        one row per scenario x category x line x year
                       (scenario, category, line, year, amount, currency, source, basis, confidence)
  --summary tco.md     run-rate comparison, one-time cost, net benefit and payback tables
  --json tco.json      machine-readable totals

Usage:
    python3 -I tco.py scored.csv --rates rates.csv --out tco.csv --summary tco.md --json tco.json

Exit codes: 0 ok; 1 bad input (missing file/columns, non-numeric value). Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

TBD = "[TO BE BASELINED — owner: Integration architect]"
BANDS = [("Simple", "unit_cost_simple"), ("Medium", "unit_cost_medium"),
         ("Complex", "unit_cost_complex"), ("Very complex", "unit_cost_very_complex")]
RUN_CATS = [("licence", "licence"), ("infrastructure", "infrastructure"),
            ("run_team", "run team"), ("support_contract", "support contract")]


def load_rates(path: Path) -> tuple[dict, dict]:
    if not path.is_file():
        sys.exit(f"error: rates file not found: {path}")
    vals, src = {}, {}
    with path.open(newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        if not rdr.fieldnames or "key" not in rdr.fieldnames or "value" not in rdr.fieldnames:
            sys.exit("error: rates CSV needs columns key,value")
        for r in rdr:
            k, v = (r.get("key") or "").strip(), (r.get("value") or "").strip()
            if not k or not v:
                continue
            if k == "currency":
                vals[k] = v
            else:
                try:
                    vals[k] = float(v.replace(",", ""))
                except ValueError:
                    sys.exit(f"error: non-numeric value for {k}: {v!r}")
            src[k] = (r.get("source") or "").strip() or "rates CSV"
    return vals, src


def load_inventory(path: Path) -> list[dict]:
    if not path.is_file():
        sys.exit(f"error: inventory not found: {path}")
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("error: inventory has no rows")
    if "band" not in rows[0]:
        sys.exit("error: inventory has no `band` column (run score_inventory.py first)")
    return rows


def money(v, cur: str) -> str:
    return TBD if v is None else f"{v:,.0f} {cur}"


def build(rows: list[dict], rates: dict, src: dict):
    cur = str(rates.get("currency", "USD"))
    horizon = int(min(max(rates.get("horizon_years", 3), 1), 5))
    dual_months = rates.get("dual_run_months")
    decom_month = rates.get("decommission_month")
    lines = []  # scenario, category, line, year, amount(None=TBD), source

    def add(scn, cat, line, year, key_or_amount, source, basis="budget", conf="M"):
        if isinstance(key_or_amount, str):
            amt, s = rates.get(key_or_amount), src.get(key_or_amount, f"missing key {key_or_amount}")
        else:
            amt, s = key_or_amount, source
        lines.append({"scenario": scn, "category": cat, "line": line, "year": year,
                      "amount": amt, "currency": cur, "source": s, "basis": basis, "confidence": conf})

    # run-rate, both scenarios
    for year in range(1, horizon + 1):
        for cat, label in RUN_CATS:
            add("current", cat, f"current {label}", year, f"current_{cat}", None)
            # target: new platform costs
            add("target", cat, f"target {label}", year, f"target_{cat}", None)
        # dual run: current platform costs continue inside the target scenario until decommission
        if decom_month is None:
            add("target", "dual_run", "current platform until decommission", year, None,
                "decommission_month missing", "assumption", "L")
        else:
            months_in_year = max(0.0, min(12.0, decom_month - 12 * (year - 1)))
            if months_in_year > 0:
                share = months_in_year / 12.0
                total = 0.0
                missing = False
                for cat, _ in RUN_CATS:
                    v = rates.get(f"current_{cat}")
                    if v is None:
                        missing = True
                    else:
                        total += v * share
                add("target", "dual_run", f"current platform {months_in_year:.0f} months (decommission month {decom_month:.0f})",
                    year, None if missing else round(total, 2),
                    "current_* keys x months before decommission", "estimate", "M")
    # one-time migration, by band
    counts = {}
    for r in rows:
        if str(r.get("retire_candidate", "")).strip().lower() in ("true", "1", "yes"):
            continue
        counts[r.get("band", "")] = counts.get(r.get("band", ""), 0) + 1
    for band, key in BANDS:
        n = counts.get(band, 0)
        if n == 0:
            continue
        unit = rates.get(key)
        add("target", "migration_one_time", f"migrate {n} {band} interfaces @ {key}", 0,
            None if unit is None else round(n * unit, 2),
            f"{src.get(key, 'missing ' + key)}; count from scored inventory", "estimate", "M")
    add("target", "training", "training / enablement", 0, "training_one_time", None, "estimate", "M")
    add("target", "decommission", "decommission", 0, "decommission_one_time", None, "estimate", "M")
    if dual_months is not None and decom_month is None:
        lines.append({"scenario": "target", "category": "dual_run", "line": "dual_run_months given but decommission_month missing",
                      "year": 0, "amount": None, "currency": cur, "source": "rates CSV", "basis": "assumption", "confidence": "L"})
    return lines, cur, horizon, counts


def summarize(lines, cur, horizon):
    def total(scn, year, exclude_one_time=True):
        sel = [l for l in lines if l["scenario"] == scn and l["year"] == year]
        if exclude_one_time:
            sel = [l for l in sel if l["year"] != 0]
        if any(l["amount"] is None for l in sel):
            return None
        return sum(l["amount"] for l in sel)

    run = {scn: {y: total(scn, y) for y in range(1, horizon + 1)} for scn in ("current", "target")}
    one_time_lines = [l for l in lines if l["year"] == 0]
    one_time = None if any(l["amount"] is None for l in one_time_lines) else sum(l["amount"] for l in one_time_lines)
    cum = {"current": {}, "target": {}}
    net_year, net_cum, payback = {}, {}, None
    cc, ct = 0.0, (one_time if one_time is not None else None)
    cum["current"][0], cum["target"][0] = 0.0, ct
    net_year[0] = None if ct is None else -ct
    net_cum[0] = net_year[0]
    broken = ct is None
    for y in range(1, horizon + 1):
        c, t = run["current"][y], run["target"][y]
        if broken or c is None or t is None:
            broken = True
            cum["current"][y] = None if c is None else (cc := cc + c)
            cum["target"][y] = None
            net_year[y] = net_cum[y] = None
            continue
        cc += c
        ct += t
        cum["current"][y], cum["target"][y] = cc, ct
        net_year[y] = c - t
        net_cum[y] = cc - ct
        if payback is None and net_cum[y] >= 0:
            payback = y
    return {"currency": cur, "horizon_years": horizon, "run_rate": run, "one_time_total": one_time,
            "cumulative": cum, "net_benefit_by_year": net_year, "net_cumulative": net_cum,
            "payback_year": payback if not broken else None,
            "net_3yr": net_cum.get(min(3, horizon)) if not broken else None,
            "tbd_lines": [l["line"] for l in lines if l["amount"] is None]}


def render_md(lines, s, counts):
    cur, H = s["currency"], s["horizon_years"]
    yrs = list(range(1, H + 1))
    L = [f"# TCO — scored inventory x rate inputs", "",
         f"Currency: {cur} · Basis: undiscounted · Horizon: {H} years · "
         f"Lines marked TBD: {len(s['tbd_lines'])}", "",
         "## Run-rate comparison",
         "| Category | " + " | ".join(f"Current Y{y}" for y in yrs) + " | " + " | ".join(f"Target Y{y}" for y in yrs) + " | Source |",
         "|---|" + "---|" * (2 * H) + "---|"]
    cats = []
    for l in lines:
        if l["year"] != 0 and l["category"] not in cats:
            cats.append(l["category"])
    for cat in cats:
        cells, srcs = [], set()
        for scn in ("current", "target"):
            for y in yrs:
                sel = [l for l in lines if l["scenario"] == scn and l["category"] == cat and l["year"] == y]
                if not sel:
                    cells.append("—")
                elif any(l["amount"] is None for l in sel):
                    cells.append(TBD)
                else:
                    cells.append(f"{sum(l['amount'] for l in sel):,.0f}")
                srcs.update(l["source"] for l in sel)
        L.append(f"| {cat.replace('_', ' ')} | " + " | ".join(cells) + f" | {'; '.join(sorted(srcs))[:80]} |")
    L.append("| **Annual total** | " + " | ".join(
        money(s["run_rate"][scn][y], cur) for scn in ("current", "target") for y in yrs) + " | |")
    L += ["", "## One-time migration cost", "| Line | Amount | Source | Confidence |", "|---|---|---|---|"]
    L += [f"| {l['line']} | {money(l['amount'], cur)} | {l['source']} | {l['confidence']} |"
          for l in lines if l["year"] == 0]
    L.append(f"| **Total one-time** | {money(s['one_time_total'], cur)} | | |")
    L += ["", "## Net benefit and payback",
          "| Year | Current cumulative | Target cumulative (incl. one-time) | Net benefit (year) | Net cumulative |",
          "|---|---|---|---|---|"]
    for y in range(0, H + 1):
        L.append(f"| {y} | {money(s['cumulative']['current'].get(y), cur)} | {money(s['cumulative']['target'].get(y), cur)} | "
                 f"{money(s['net_benefit_by_year'].get(y), cur)} | {money(s['net_cumulative'].get(y), cur)} |")
    pb = s["payback_year"]
    L.append("")
    L.append(f"Payback: {('year ' + str(pb)) if pb else ('not within horizon' if s['net_3yr'] is not None else TBD)} · "
             f"3-year net: {money(s['net_3yr'], cur)}")
    L += ["", "## Inventory counts used (non-retirement)", "| Band | Count |", "|---|---|"]
    L += [f"| {b} | {counts.get(b, 0)} |" for b, _ in BANDS]
    if s["tbd_lines"]:
        L += ["", "## Lines awaiting input (owner: Integration architect)"]
        L += [f"- {t}" for t in s["tbd_lines"]]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inventory", type=Path, help="scored inventory CSV (with band column)")
    ap.add_argument("--rates", type=Path, required=True, help="rate inputs CSV (key,value,...)")
    ap.add_argument("--out", type=Path, required=True, help="TCO lines CSV")
    ap.add_argument("--summary", type=Path, help="Markdown summary")
    ap.add_argument("--json", type=Path, help="JSON totals")
    a = ap.parse_args(argv)
    rows = load_inventory(a.inventory)
    rates, src = load_rates(a.rates)
    lines, cur, horizon, counts = build(rows, rates, src)
    s = summarize(lines, cur, horizon)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["scenario", "category", "line", "year", "amount", "currency",
                                          "source", "basis", "confidence"])
        w.writeheader()
        for l in lines:
            w.writerow({**l, "amount": TBD if l["amount"] is None else f"{l['amount']:.2f}"})
    if a.summary:
        a.summary.write_text(render_md(lines, s, counts), encoding="utf-8")
    if a.json:
        a.json.write_text(json.dumps({**s, "band_counts": counts}, indent=2), encoding="utf-8")
    print(f"{len(lines)} TCO lines ({len(s['tbd_lines'])} TBD) -> {a.out}; "
          f"3-yr net: {money(s['net_3yr'], cur)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

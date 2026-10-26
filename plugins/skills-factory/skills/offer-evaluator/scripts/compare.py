#!/usr/bin/env python3
"""Offer comparison calculator (stdlib only). No built-in COL or market data.

Reads assets/offer-comparison.csv layout, computes year-1 cash, annual recurring,
annualized total over a horizon, and COL-adjusted recurring using indices the
user supplies on the command line.

Usage:
    compare.py --file offer-comparison.csv [--horizon 4]
               [--col "Columbus OH=100,Austin TX=108,Remote=100"] [--base-location "Columbus OH"]
               [--tax "Columbus OH=0.045,Austin TX=0,Remote=0.045"] [--json]

Rules (see references/total-comp.md and col-adjustment.md):
    year1_cash       = base + bonus + sign_on + relocation
    annual_recurring = base + bonus + equity/yr + retirement match + benefits + stipends
    annualized_total = annual_recurring + (sign_on + relocation) / horizon
    adjusted         = annual_recurring / (index_location / index_base)   [recurring only]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

NUMERIC = ["base", "bonus_target_pct", "sign_on", "equity_total_value", "equity_vest_years",
           "retirement_match_pct", "benefits_value_annual", "stipends_annual", "relocation"]


def parse_map(s: str | None, what: str) -> dict[str, float]:
    out: dict[str, float] = {}
    if not s:
        return out
    for part in s.split(","):
        if "=" not in part:
            raise SystemExit(f"error: {what} entries must look like 'Location=value', got '{part}'")
        k, v = part.rsplit("=", 1)
        try:
            out[k.strip()] = float(v)
        except ValueError:
            raise SystemExit(f"error: {what} value for '{k.strip()}' is not a number: '{v}'")
    return out


def num(row: dict, key: str) -> float:
    v = (row.get(key) or "").strip()
    if v == "":
        return 0.0
    try:
        return float(v.replace("$", "").replace(",", ""))
    except ValueError:
        raise SystemExit(f"error: '{key}' for option '{row.get('option')}' is not numeric: '{v}'")


def compute(row: dict, horizon: float, col: dict[str, float], base_loc: str | None, tax: dict[str, float]) -> dict:
    base = num(row, "base")
    bonus = base * num(row, "bonus_target_pct") / 100
    sign_on = num(row, "sign_on")
    reloc = num(row, "relocation")
    eq_total, eq_years = num(row, "equity_total_value"), num(row, "equity_vest_years")
    equity_yr = eq_total / eq_years if eq_years > 0 else 0.0
    match = base * num(row, "retirement_match_pct") / 100
    benefits = num(row, "benefits_value_annual")
    stipends = num(row, "stipends_annual")

    year1 = base + bonus + sign_on + reloc
    recurring = base + bonus + equity_yr + match + benefits + stipends
    annualized = recurring + (sign_on + reloc) / horizon if horizon > 0 else recurring

    loc = (row.get("location") or "").strip()
    rel_index, adjusted, col_note = None, None, "no COL index supplied"
    if col:
        if base_loc is None:
            raise SystemExit("error: --base-location is required when --col is given")
        if loc in col and base_loc in col:
            rel_index = col[loc] / col[base_loc]
            adjusted = recurring / rel_index
            col_note = f"{loc}={col[loc]:g} vs {base_loc}={col[base_loc]:g}"
        else:
            col_note = f"index missing for '{loc}' or '{base_loc}' — TO BE BASELINED (owner: user)"

    after_tax = None
    if tax:
        if loc in tax:
            after_tax = (adjusted if adjusted is not None else recurring) * (1 - tax[loc])
        else:
            col_note += f"; tax rate missing for '{loc}'"

    return {
        "option": row.get("option"), "company": row.get("company"), "title": row.get("title"), "location": loc,
        "base": base, "bonus_target": bonus, "sign_on": sign_on, "relocation": reloc, "equity_per_year": equity_yr,
        "retirement_match": match, "benefits": benefits, "stipends": stipends,
        "year1_cash": year1, "annual_recurring": recurring, "annualized_total": annualized,
        "rel_index": rel_index, "adjusted_recurring": adjusted, "after_tax_recurring": after_tax, "col_note": col_note,
    }


def fmt(v, ratio: bool = False) -> str:
    if v is None:
        return "n/a"
    return f"{v:.3f}" if ratio else f"${v:,.0f}"


def render(results: list[dict], horizon: float) -> str:
    cols = ["option", "location", "base", "bonus_target", "sign_on", "equity_per_year", "retirement_match",
            "benefits", "year1_cash", "annual_recurring", "annualized_total", "rel_index", "adjusted_recurring"]
    out = [f"Offer comparison — horizon {horizon:g} years", "",
           "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in results:
        out.append("| " + " | ".join(str(r[c]) if c in ("option", "location") else fmt(r[c], c == "rel_index") for c in cols) + " |")
    cur = next((r for r in results if (r["option"] or "").lower() == "current"), None)
    if cur:
        out += ["", "| option | Δ recurring vs current | Δ adjusted vs current |", "|---|---|---|"]
        for r in results:
            if r is cur:
                continue
            d1 = r["annual_recurring"] - cur["annual_recurring"]
            d2 = (r["adjusted_recurring"] - cur["adjusted_recurring"]) if (r["adjusted_recurring"] is not None and cur["adjusted_recurring"] is not None) else None
            d2s = f"{d2:+,.0f}" if d2 is not None else "n/a"
            out.append(f"| {r['option']} | {d1:+,.0f} | {d2s} |")
    out += ["", "Notes:"] + [f"- {r['option']}: {r['col_note']}" for r in results]
    out.append("- Bonus valued at target; equity at user-stated value over vesting; nothing estimated.")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True, type=Path)
    ap.add_argument("--horizon", type=float, default=4.0, help="planning horizon in years (default 4)")
    ap.add_argument("--col", help='user-supplied COL indices, e.g. "Columbus OH=100,Austin TX=108"')
    ap.add_argument("--base-location", dest="base_location", help="location whose index is the baseline")
    ap.add_argument("--tax", help='optional effective tax rates per location, e.g. "Austin TX=0,Columbus OH=0.045"')
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not a.file.exists():
        print(f"error: file not found: {a.file}", file=sys.stderr)
        return 2
    col = parse_map(a.col, "--col")
    tax = parse_map(a.tax, "--tax")
    with a.file.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("error: no rows in file", file=sys.stderr)
        return 2
    results = [compute(r, a.horizon, col, a.base_location, tax) for r in rows]
    print(json.dumps(results, indent=2) if a.json else render(results, a.horizon))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""LLM API token-economics model: workload + price sheet + feature->model assignment -> monthly cost.

Per feature: monthly input/output/cached tokens, cost (input, cached input, output), cost per
request, the saving from prompt caching, and a what-if swap to the cheapest priced model the user
marks eligible for that feature. Totals by model and overall; budget utilisation, headroom and
alert levels (default 50/80/100 % of budget) when a budget is supplied.

No price is built in. Every price comes from --prices (model, price_in_per_1m, price_out_per_1m,
optional cached_in_per_1m, source, as_of). A price row without source/as_of is reported as
`[TO BE BASELINED — owner: FinOps lead]`. Cached input tokens are charged at the full input price
when no cached price is supplied (stated in the notes). A blank cached_input_share means no caching.

Inputs:
  --workload    CSV feature,requests_per_month,input_tokens,output_tokens[,cached_input_share]
                (tokens are averages per request; share is 0..1 of input tokens served from cache)
  --prices      CSV model,price_in_per_1m,price_out_per_1m[,cached_in_per_1m],source,as_of
  --assignment  CSV feature,model[,eligible_models]  (eligible_models: ';'-separated swap candidates)
  --budget      monthly budget in the price currency (optional)
  --actuals     CSV feature,actual_cost[,actual_requests],period,source — what the features really cost in
                one billed month (brownfield). Adds "actuals": modelled vs actual cost per feature, variance
                and variance %, actual cost per request, and spend on features the model does not cover.

Usage:
  python3 -I cost_model.py --workload w.csv --prices p.csv --assignment a.csv [--budget 1000] [--actuals billed.csv] --out <dir>
  python3 -I cost_model.py ... --json          # JSON to stdout

Exit codes: 0 ok (within budget or no budget) · 1 total exceeds the supplied budget ·
2 required input missing or unusable (file, column, unpriced assigned model, feature without
assignment). Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

OWNER = "FinOps lead"
TBB = f"[TO BE BASELINED — owner: {OWNER}]"
M = 1_000_000


class InputError(Exception):
    """A required input is missing or unusable (exit 2)."""


def read_csv(path: Path, required: list[str], label: str) -> list[dict]:
    if not path.is_file():
        raise InputError(f"{label} file not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in required if c not in header]
        if missing:
            raise InputError(f"{label} CSV lacks column(s) {missing}; header is {header}")
        rows = []
        for i, row in enumerate(reader, start=2):
            row = {(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None}
            first = row.get(required[0], "")
            if not first or first.startswith("#"):  # blank key column = template/guidance row
                continue
            row["_line"] = i
            rows.append(row)
    if not rows:
        raise InputError(f"{label} CSV has no data rows")
    return rows


def num(row: dict, key: str, label: str, *, optional: bool = False, lo: float = 0.0, hi: float | None = None):
    raw = row.get(key, "")
    if raw == "":
        if optional:
            return None
        raise InputError(f"{label} line {row['_line']}: '{key}' is blank")
    try:
        v = float(raw.replace(",", ""))
    except ValueError as e:
        raise InputError(f"{label} line {row['_line']}: '{key}' value {raw!r} is not numeric") from e
    if v < lo or (hi is not None and v > hi):
        rng = f">= {lo}" + (f" and <= {hi}" if hi is not None else "")
        raise InputError(f"{label} line {row['_line']}: '{key}' must be {rng}, got {v}")
    return v


def load(workload: Path, prices: Path, assignment: Path):
    w_rows = read_csv(workload, ["feature", "requests_per_month", "input_tokens", "output_tokens"], "workload")
    p_rows = read_csv(prices, ["model", "price_in_per_1m", "price_out_per_1m", "source", "as_of"], "prices")
    a_rows = read_csv(assignment, ["feature", "model"], "assignment")
    feats = {}
    for r in w_rows:
        f = r["feature"]
        if f in feats:
            raise InputError(f"workload line {r['_line']}: duplicate feature {f!r}")
        feats[f] = {"requests_per_month": num(r, "requests_per_month", "workload"),
                    "input_tokens": num(r, "input_tokens", "workload"),
                    "output_tokens": num(r, "output_tokens", "workload"),
                    "cached_input_share": num(r, "cached_input_share", "workload", optional=True, hi=1.0)}
    price = {}
    for r in p_rows:
        m = r["model"]
        if m in price:
            raise InputError(f"prices line {r['_line']}: duplicate model {m!r}")
        price[m] = {"price_in_per_1m": num(r, "price_in_per_1m", "prices"),
                    "price_out_per_1m": num(r, "price_out_per_1m", "prices"),
                    "cached_in_per_1m": num(r, "cached_in_per_1m", "prices", optional=True),
                    "source": r.get("source", ""), "as_of": r.get("as_of", "")}
    assign = {}
    for r in a_rows:
        f, m = r["feature"], r["model"]
        if f not in feats:
            raise InputError(f"assignment line {r['_line']}: feature {f!r} not in workload")
        if not m:
            raise InputError(f"assignment line {r['_line']}: feature {f!r} has no model")
        if m not in price:
            raise InputError(f"assignment line {r['_line']}: model {m!r} has no row in the price sheet")
        elig = [x.strip() for x in r.get("eligible_models", "").split(";") if x.strip()]
        assign[f] = {"model": m, "eligible_models": elig}
    unassigned = [f for f in feats if f not in assign]
    if unassigned:
        raise InputError(f"feature(s) without a model assignment: {unassigned}")
    return feats, price, assign


def feature_cost(w: dict, p: dict) -> dict:
    """Monthly cost of one feature's workload on one priced model."""
    req = w["requests_per_month"]
    tin, tout = req * w["input_tokens"], req * w["output_tokens"]
    share = w["cached_input_share"] or 0.0
    cached = tin * share
    uncached = tin - cached
    cached_rate = p["cached_in_per_1m"] if p["cached_in_per_1m"] is not None else p["price_in_per_1m"]
    c_in = uncached / M * p["price_in_per_1m"]
    c_cached = cached / M * cached_rate
    c_out = tout / M * p["price_out_per_1m"]
    total = c_in + c_cached + c_out
    no_cache = tin / M * p["price_in_per_1m"] + c_out
    return {"input_tokens_month": round(tin), "cached_input_tokens_month": round(cached),
            "output_tokens_month": round(tout), "cost_input": round(c_in, 2),
            "cost_cached_input": round(c_cached, 2), "cost_output": round(c_out, 2),
            "cost_month": round(total, 2), "cost_without_caching": round(no_cache, 2),
            "caching_saving": round(no_cache - total, 2),
            "cost_per_request": round(total / req, 6) if req else None, "_raw_total": total}


def compute(feats, price, assign, budget: float | None, alert_levels: list[float]) -> dict:
    notes, features, by_model, whatif = [], {}, {}, []
    raw_total = 0.0
    for f, w in feats.items():
        m = assign[f]["model"]
        c = feature_cost(w, price[m])
        raw_total += c.pop("_raw_total")
        if (w["cached_input_share"] or 0) > 0 and price[m]["cached_in_per_1m"] is None:
            notes.append(f"{f}: no cached-input price for {m}; cached tokens charged at the full input price.")
        features[f] = {"model": m, "requests_per_month": w["requests_per_month"],
                       "input_tokens": w["input_tokens"], "output_tokens": w["output_tokens"],
                       "cached_input_share": w["cached_input_share"] or 0.0, **c}
        bm = by_model.setdefault(m, {"features": [], "requests_per_month": 0.0, "cost_month": 0.0})
        bm["features"].append(f)
        bm["requests_per_month"] += w["requests_per_month"]
        bm["cost_month"] = round(bm["cost_month"] + c["cost_month"], 2)

        # what-if: cheapest priced eligible model
        cands, unpriced = {}, []
        for e in assign[f]["eligible_models"]:
            if e in price:
                cc = feature_cost(w, price[e])
                cc.pop("_raw_total")
                cands[e] = cc["cost_month"]
            else:
                unpriced.append(e)
        if unpriced:
            notes.append(f"{f}: eligible model(s) {unpriced} have no price row; excluded from the what-if.")
        row = {"feature": f, "current_model": m, "current_cost": c["cost_month"],
               "eligible_priced": sorted(cands), "eligible_unpriced": unpriced}
        if cands:
            best = min(cands, key=lambda k: (cands[k], k))
            row.update({"cheapest_model": best, "cheapest_cost": cands[best],
                        "saving": round(c["cost_month"] - cands[best], 2)})
            if best == m or cands[best] >= c["cost_month"]:
                row.update({"cheapest_model": m, "cheapest_cost": c["cost_month"], "saving": 0.0})
        else:
            row.update({"cheapest_model": None, "cheapest_cost": None, "saving": None})
        whatif.append(row)

    total = round(raw_total, 2)
    total_req = sum(w["requests_per_month"] for w in feats.values())
    swapped_total = round(sum((r["cheapest_cost"] if r["cheapest_cost"] is not None else r["current_cost"])
                              for r in whatif), 2)
    caching_saving = round(sum(v["caching_saving"] for v in features.values()), 2)
    out = {
        "currency_note": "Same currency as the price sheet.",
        "monthly_total": total,
        "requests_per_month": total_req,
        "cost_per_request": round(total / total_req, 6) if total_req else None,
        "caching_saving_total": caching_saving,
        "cost_without_caching_total": round(sum(v["cost_without_caching"] for v in features.values()), 2),
        "features": features,
        "by_model": by_model,
        "what_if": {"rows": whatif, "total_if_all_swapped": swapped_total,
                    "saving_if_all_swapped": round(total - swapped_total, 2)},
        "budget": None,
        "prices": {m: dict(p, unsourced=not (p["source"] and p["as_of"])) for m, p in price.items()},
        "notes": notes,
    }
    for m, p in price.items():
        if not (p["source"] and p["as_of"]):
            notes.append(f"Price for {m} lacks a source or as-of date: {TBB}.")
    if budget is not None:
        util = total / budget * 100 if budget else None
        alerts = [{"level_pct": lvl, "amount": round(budget * lvl / 100, 2),
                   "reached": total >= budget * lvl / 100} for lvl in alert_levels]
        out["budget"] = {"budget_month": budget, "utilisation_pct": round(util, 1) if util is not None else None,
                         "headroom": round(budget - total, 2), "over_budget": total > budget, "alerts": alerts}
    return out


def load_actuals(path: Path) -> list[dict]:
    rows = read_csv(path, ["feature", "actual_cost"], "actuals")
    seen, out = set(), []
    for r in rows:
        if r["feature"] in seen:
            raise InputError(f"actuals line {r['_line']}: duplicate feature {r['feature']!r}")
        seen.add(r["feature"])
        out.append({"feature": r["feature"], "actual_cost": num(r, "actual_cost", "actuals"),
                    "actual_requests": num(r, "actual_requests", "actuals", optional=True),
                    "period": r.get("period", ""), "source": r.get("source", "")})
    return out


def compare_actuals(res: dict, actuals: list[dict]) -> dict:
    """Modelled vs billed cost per feature (variance = actual - modelled; % of modelled)."""
    by = {a["feature"]: a for a in actuals}
    rows = []
    for f, v in res["features"].items():
        a = by.get(f)
        row = {"feature": f, "modelled_cost": v["cost_month"], "modelled_requests": v["requests_per_month"],
               "actual_cost": None, "actual_requests": None, "variance": None, "variance_pct": None,
               "actual_cost_per_request": None}
        if a:
            row["actual_cost"] = round(a["actual_cost"], 2)
            row["actual_requests"] = a["actual_requests"]
            row["variance"] = round(a["actual_cost"] - v["cost_month"], 2)
            row["variance_pct"] = round(row["variance"] / v["cost_month"] * 100, 1) if v["cost_month"] else None
            if a["actual_requests"]:
                row["actual_cost_per_request"] = round(a["actual_cost"] / a["actual_requests"], 6)
        rows.append(row)
    rows.sort(key=lambda r: -abs(r["variance"]) if r["variance"] is not None else 0)
    unmodelled = [{"feature": a["feature"], "actual_cost": round(a["actual_cost"], 2)}
                  for a in actuals if a["feature"] not in res["features"]]
    matched = [r for r in rows if r["actual_cost"] is not None]
    m_tot = round(sum(r["modelled_cost"] for r in matched), 2)
    a_tot = round(sum(r["actual_cost"] for r in matched), 2)
    periods = sorted({a["period"] for a in actuals if a["period"]})
    sources = sorted({a["source"] for a in actuals if a["source"]})
    return {"period": "; ".join(periods) or TBB, "source": "; ".join(sources) or TBB, "rows": rows,
            "not_billed": [r["feature"] for r in rows if r["actual_cost"] is None], "unmodelled": unmodelled,
            "unmodelled_total": round(sum(u["actual_cost"] for u in unmodelled), 2),
            "modelled_total_matched": m_tot, "actual_total_matched": a_tot,
            "variance_total": round(a_tot - m_tot, 2),
            "variance_pct_total": round((a_tot - m_tot) / m_tot * 100, 1) if m_tot else None,
            "actual_total_all": round(a_tot + sum(u["actual_cost"] for u in unmodelled), 2),
            "billed_vs_budget_pct": (round((a_tot + sum(u["actual_cost"] for u in unmodelled))
                                           / res["budget"]["budget_month"] * 100, 1) if res.get("budget") else None)}


def money(x) -> str:
    return "n/a" if x is None else f"{x:,.2f}"


def intc(x) -> str:
    return f"{x:,.0f}"


def pct(x) -> str:
    return f"{x:g}"


def render_actuals_md(a: dict) -> list[str]:
    def sp(x):
        return "n/a" if x is None else f"{x:+g}%"

    def signed(x):
        return "n/a" if x is None else f"{x:+,.2f}"

    def per_req(x):
        return "n/a" if x is None else f"{x:.6f}"
    L = ["", "## Actuals vs model", "",
         f"Billed period {a['period']} (source: {a['source']}). Variance = actual − modelled, % of modelled. "
         "A large variance means the workload averages (requests, tokens, cache share) no longer match production: "
         "update the workload CSV from the logs and re-run.", "",
         "| Feature | Modelled / month | Actual | Variance | Variance % | Modelled requests | Actual requests | Actual cost / request |",
         "|---|---|---|---|---|---|---|---|"]
    for r in a["rows"]:
        L.append(f"| {r['feature']} | {money(r['modelled_cost'])} | {money(r['actual_cost'])} | "
                 f"{signed(r['variance'])} | {sp(r['variance_pct'])} | "
                 f"{intc(r['modelled_requests'])} | {'n/a' if r['actual_requests'] is None else intc(r['actual_requests'])} | "
                 f"{per_req(r['actual_cost_per_request'])} |")
    L += ["", f"Matched features: modelled {money(a['modelled_total_matched'])}, actual {money(a['actual_total_matched'])}, "
          f"variance {a['variance_total']:+,.2f} ({sp(a['variance_pct_total'])})."]
    if a["unmodelled"]:
        L.append(f"Billed but not in the model: " + ", ".join(f"{u['feature']} {money(u['actual_cost'])}" for u in a["unmodelled"])
                 + f" (total {money(a['unmodelled_total'])}); add these features to the workload. "
                 f"All billed spend: {money(a['actual_total_all'])}.")
    if a["not_billed"]:
        L.append(f"In the model but absent from the bill: {', '.join(a['not_billed'])}.")
    if a.get("billed_vs_budget_pct") is not None:
        L.append(f"Billed spend is {a['billed_vs_budget_pct']:g}% of the monthly budget"
                 + (" — over budget in the billed month." if a["billed_vs_budget_pct"] > 100 else "."))
    return L


def render_md(res: dict) -> str:
    L = ["# LLM cost model", ""]
    L += ["## Monthly total", ""]
    L.append(f"**{money(res['monthly_total'])} per month** for {intc(res['requests_per_month'])} requests "
             f"({res['cost_per_request']:.6f} per request). Prompt caching saves {money(res['caching_saving_total'])} "
             f"against {money(res['cost_without_caching_total'])} without caching. {res['currency_note']}")
    L += ["", "| Model | Features | Requests / month | Cost / month |", "|---|---|---|---|"]
    for m, b in res["by_model"].items():
        L.append(f"| {m} | {', '.join(b['features'])} | {intc(b['requests_per_month'])} | {money(b['cost_month'])} |")
    L += ["", "## By feature", "",
          "| Feature | Model | Requests / month | Input tokens / month | Cached input tokens | Output tokens / month "
          "| Cost / month | Cost / request | Caching saving |",
          "|---|---|---|---|---|---|---|---|---|"]
    for f, v in res["features"].items():
        L.append(f"| {f} | {v['model']} | {intc(v['requests_per_month'])} | {intc(v['input_tokens_month'])} | "
                 f"{intc(v['cached_input_tokens_month'])} | {intc(v['output_tokens_month'])} | {money(v['cost_month'])} | "
                 f"{v['cost_per_request']:.6f} | {money(v['caching_saving'])} |")
    L += ["", "## What-if", "",
          "Swap each feature to the cheapest priced model the user marked eligible (quality is not assessed here; "
          "run the eval harness before switching).", "",
          "| Feature | Current model | Current cost | Cheapest eligible | Cost if swapped | Saving |",
          "|---|---|---|---|---|---|"]
    for r in res["what_if"]["rows"]:
        if r["cheapest_model"] is None:
            L.append(f"| {r['feature']} | {r['current_model']} | {money(r['current_cost'])} | "
                     f"none marked eligible | n/a | n/a |")
        else:
            L.append(f"| {r['feature']} | {r['current_model']} | {money(r['current_cost'])} | {r['cheapest_model']} | "
                     f"{money(r['cheapest_cost'])} | {money(r['saving'])} |")
    L += ["", f"Total if every swap is made: {money(res['what_if']['total_if_all_swapped'])} "
          f"(saving {money(res['what_if']['saving_if_all_swapped'])})."]
    L += ["", "## Budget", ""]
    b = res["budget"]
    if b is None:
        L.append(f"No monthly budget supplied: {TBB}. Headroom and alerts not computed.")
    else:
        state = "OVER BUDGET" if b["over_budget"] else "within budget"
        util = "n/a" if b["utilisation_pct"] is None else f"{b['utilisation_pct']:g}%"
        L.append(f"**{state}** — budget {money(b['budget_month'])}, utilisation {util}, headroom {money(b['headroom'])}.")
        L += ["", "| Alert level | Amount | Reached |", "|---|---|---|"]
        for a in b["alerts"]:
            L.append(f"| {pct(a['level_pct'])}% | {money(a['amount'])} | {'yes' if a['reached'] else 'no'} |")
    if res.get("actuals"):
        L += render_actuals_md(res["actuals"])
    L += ["", "## Sources", "", "| Model | In / 1M | Out / 1M | Cached in / 1M | Source | As of |", "|---|---|---|---|---|---|"]
    for m, p in res["prices"].items():
        cached = "not supplied" if p["cached_in_per_1m"] is None else f"{p['cached_in_per_1m']:g}"
        src = p["source"] or TBB
        asof = p["as_of"] or TBB
        L.append(f"| {m} | {p['price_in_per_1m']:g} | {p['price_out_per_1m']:g} | {cached} | {src} | {asof} |")
    L += ["", "Prices are user-supplied and dated; re-run when a price sheet changes. Token counts are averages "
          "per request; retries, tool calls and system prompts count only if included in them."]
    for n in res["notes"]:
        L.append(f"- Note: {n}")
    return "\n".join(L) + "\n"


def parse_levels(raw: str) -> list[float]:
    try:
        levels = sorted({float(x) for x in raw.split(",") if x.strip()})
    except ValueError as e:
        raise InputError(f"--alert-levels must be comma-separated numbers, got {raw!r}") from e
    if not levels or any(x <= 0 for x in levels):
        raise InputError("--alert-levels must be positive percentages")
    return levels


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workload", type=Path, required=True)
    ap.add_argument("--prices", type=Path, required=True)
    ap.add_argument("--assignment", type=Path, required=True)
    ap.add_argument("--budget", help="monthly budget (same currency as the price sheet)")
    ap.add_argument("--alert-levels", default="50,80,100", help="budget alert levels in %% (default 50,80,100)")
    ap.add_argument("--actuals", type=Path, help="billed cost per feature for one month (brownfield variance)")
    ap.add_argument("--out", type=Path, help="directory for cost-model.json and cost-model.md")
    ap.add_argument("--json", action="store_true", help="print the JSON result to stdout")
    a = ap.parse_args(argv)
    try:
        budget = None
        if a.budget not in (None, ""):
            try:
                budget = float(str(a.budget).replace(",", ""))
            except ValueError as e:
                raise InputError(f"--budget must be a number, got {a.budget!r}") from e
            if budget <= 0:
                raise InputError("--budget must be > 0")
        feats, price, assign = load(a.workload, a.prices, a.assignment)
        res = compute(feats, price, assign, budget, parse_levels(a.alert_levels))
        if a.actuals:
            res["actuals"] = compare_actuals(res, load_actuals(a.actuals))
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "cost-model.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
        (a.out / "cost-model.md").write_text(render_md(res), encoding="utf-8")
        print(f"monthly total {money(res['monthly_total'])}: wrote {a.out / 'cost-model.json'} and {a.out / 'cost-model.md'}")
    if a.json or not a.out:
        print(json.dumps(res, indent=2))
    if res["budget"] and res["budget"]["over_budget"]:
        print(f"over budget: {money(res['monthly_total'])} > {money(res['budget']['budget_month'])}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""AI FinOps showback / chargeback: what AI usage costs by team, feature and model.

Usage:
  python3 -I chargeback.py --usage usage.csv --prices prices.csv [--budgets budgets.csv]
        [--as-of YYYY-MM-DD] [--strict] --out-dir OUT
  python3 -I chargeback.py --verify OUTPUT_FILE --usage U --prices P [--budgets B] [--as-of D]
        # exit 0 when OUTPUT_FILE is byte-identical to what this script produces for the inputs

Inputs (CSV; leading lines starting with '#' are skipped):
  usage    date, team, feature, model, requests, input_tokens, output_tokens[, cached_input_tokens]
           input_tokens is ALL input tokens; cached_input_tokens is the part served from cache
  prices   model, input_per_1m, output_per_1m[, cached_input_per_1m], effective_from
           the row in effect on a usage date = latest effective_from on or before that date
  budgets  team, month (YYYY-MM), budget_usd

Math (Decimal, full precision; money rounded half-up to cents only when written):
  cost = ((input - cached) * input_per_1m + cached * cached_rate + output * output_per_1m) / 1e6
         cached_rate = cached_input_per_1m, or input_per_1m when the sheet has no cached price
  unpriced usage (model absent, or no price in effect on the date): no cost, listed with
         [TO BE BASELINED — owner: FinOps lead]; excluded from every total
  cost_per_1k_requests = cost / priced requests * 1000 (4 dp)
  share = % of the month's priced spend (detail, month_team) or of all priced spend (other levels), 2 dp
  mom_change_pct = (month - previous month) / previous month * 100, 2 dp (month and month_team rows)
  anomaly (mean, sd, threshold written to 4 dp) = a team-day whose cost > mean + 3 * sd (sample sd) of the team's trailing 14 calendar days
         (days with no usage count as 0; days before the team's first usage are not counted);
         needs >= 7 prior days
  forecast = closed month: actual; as-of month: actual / days elapsed * days in month (linear
         run-rate); later month: not started. as-of defaults to the latest usage date.
  variance = budget - forecast (negative = over budget)

Outputs: OUT/showback.csv, OUT/anomalies.csv, OUT/budget.csv, OUT/finops-report.md
Exit codes: 0 ok · 1 --strict and a team forecast is over budget, or --verify mismatch
            · 2 missing or invalid input.
Stdlib only; reads only the given files; writes only into --out-dir.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import io
import re
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

TBD = "[TO BE BASELINED — owner: FinOps lead]"
MILLION = Decimal(1_000_000)
CENT = Decimal("0.01")
WINDOW_DAYS = 14
MIN_PRIOR_DAYS = 7
SIGMA = 3
INT_RE = re.compile(r"^\d+$")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
LEVELS = ("total", "month", "month_team", "team", "team_feature", "model", "detail")


class InputError(Exception):
    """A required input is missing or malformed (exit 2)."""


_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")
_NUMBER = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?")


def csv_safe(v) -> str:
    """OWASP CSV-injection guard: prefix a formula-leading text cell with a single quote (numbers untouched)."""
    s = "" if v is None else str(v)
    if s.startswith(_FORMULA_LEAD) and not _NUMBER.fullmatch(s):
        return "'" + s
    return s


# ------------------------------------------------------------------ input

def read_rows(path, what: str, required: tuple, optional: tuple = ()) -> list[dict]:
    if path is None:
        raise InputError(f"--{what} is required")
    p = Path(path)
    if not p.is_file():
        raise InputError(f"{what} file not found: {p}")
    try:
        text = p.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as e:
        raise InputError(f"{what} file {p.name} is not UTF-8 text ({e.reason} at byte {e.start}); "
                         "re-save it as CSV UTF-8") from None
    if "\x00" in text:
        raise InputError(f"{what} file {p.name} is not a text CSV (contains NUL bytes)")
    lines = text.splitlines()
    while lines and lines[0].lstrip().startswith("#"):
        lines.pop(0)
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    header = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in required if c not in header]
    if missing:
        raise InputError(f"{what} is missing column(s): {', '.join(missing)}")
    rows = []
    for i, r in enumerate(reader, start=2):
        extra = [x for x in (r.get(None) or []) if (x or "").strip()]
        if extra:
            raise InputError(f"{what} line {i}: {len(extra)} field(s) beyond the {len(header)}-column header "
                             f"(ragged row: {', '.join(repr(x) for x in extra[:3])}); fix the row so no value is dropped")
        r = {(k or "").strip(): (v or "").strip() if isinstance(v, str) else "" for k, v in r.items() if k is not None}
        if not any(r.get(c) for c in required + optional):
            continue
        r["_line"] = i
        rows.append(r)
    return rows


def to_date(s: str, what: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise InputError(f"{what}: {s!r} is not a YYYY-MM-DD date") from None


def to_int(s: str, what: str) -> int:
    if not INT_RE.match(s or ""):
        raise InputError(f"{what}: {s!r} is not a non-negative integer")
    return int(s)


def to_dec(s: str, what: str) -> Decimal:
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise InputError(f"{what}: {s!r} is not a number") from None
    if not d.is_finite() or d < 0:
        raise InputError(f"{what}: {s!r} must be a non-negative number")
    return d


def load_usage(path) -> list[dict]:
    rows = read_rows(path, "usage", ("date", "team", "feature", "model", "requests", "input_tokens",
                                     "output_tokens"), ("cached_input_tokens",))
    if not rows:
        raise InputError("usage has no data rows")
    out = []
    for r in rows:
        where = f"usage line {r['_line']}"
        for c in ("team", "feature", "model"):
            if not r.get(c):
                raise InputError(f"{where}: blank {c}")
        inp = to_int(r["input_tokens"], f"{where} input_tokens")
        cached = to_int(r.get("cached_input_tokens") or "0", f"{where} cached_input_tokens")
        if cached > inp:
            raise InputError(f"{where}: cached_input_tokens ({cached}) exceeds input_tokens ({inp}); "
                             "input_tokens must include cached tokens")
        out.append({"date": to_date(r["date"], f"{where} date"), "team": r["team"], "feature": r["feature"],
                    "model": r["model"], "requests": to_int(r["requests"], f"{where} requests"),
                    "input": inp, "cached": cached, "output": to_int(r["output_tokens"], f"{where} output_tokens"),
                    "line": r["_line"]})
    return out


def duplicate_rows(usage) -> list[list[int]]:
    """Groups of line numbers whose usage rows are identical (summed, but possibly a double-counted re-export)."""
    seen: dict = {}
    for u in usage:
        k = (u["date"], u["team"], u["feature"], u["model"], u["requests"], u["input"], u["cached"], u["output"])
        seen.setdefault(k, []).append(u["line"])
    return sorted(v for v in seen.values() if len(v) > 1)


def load_prices(path) -> dict[str, list[dict]]:
    rows = read_rows(path, "prices", ("model", "input_per_1m", "output_per_1m", "effective_from"),
                     ("cached_input_per_1m",))
    if not rows:
        raise InputError("prices has no data rows")
    by_model: dict[str, list[dict]] = {}
    for r in rows:
        where = f"prices line {r['_line']}"
        if not r.get("model"):
            raise InputError(f"{where}: blank model")
        cached = r.get("cached_input_per_1m") or ""
        p = {"from": to_date(r["effective_from"], f"{where} effective_from"),
             "in": to_dec(r["input_per_1m"], f"{where} input_per_1m"),
             "out": to_dec(r["output_per_1m"], f"{where} output_per_1m"),
             "cached": to_dec(cached, f"{where} cached_input_per_1m") if cached else None}
        lst = by_model.setdefault(r["model"], [])
        if any(x["from"] == p["from"] for x in lst):
            raise InputError(f"{where}: model {r['model']} has two price rows effective {p['from'].isoformat()}")
        lst.append(p)
    for lst in by_model.values():
        lst.sort(key=lambda x: x["from"])
    return by_model


def load_budgets(path) -> dict[tuple, Decimal]:
    if path is None:
        return {}
    rows = read_rows(path, "budgets", ("team", "month", "budget_usd"))
    out = {}
    for r in rows:
        where = f"budgets line {r['_line']}"
        if not r.get("team"):
            raise InputError(f"{where}: blank team")
        if not MONTH_RE.match(r["month"]):
            raise InputError(f"{where}: month {r['month']!r} is not YYYY-MM")
        key = (r["team"], r["month"])
        if key in out:
            raise InputError(f"{where}: duplicate budget for {key[0]} {key[1]}")
        out[key] = to_dec(r["budget_usd"], f"{where} budget_usd")
    return out


# ------------------------------------------------------------------ math

def money(d: Decimal) -> str:
    return str(d.quantize(CENT, rounding=ROUND_HALF_UP))


def dp(d: Decimal, places: int) -> str:
    return str(d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def price_for(prices, model, day):
    lst = prices.get(model)
    if not lst:
        return None, "model not in price sheet"
    eff = [p for p in lst if p["from"] <= day]
    if not eff:
        return None, f"no price in effect before {lst[0]['from'].isoformat()}"
    return eff[-1], ""


def cost_rows(usage, prices):
    notes = set()
    for u in usage:
        p, reason = price_for(prices, u["model"], u["date"])
        u["month"] = u["date"].strftime("%Y-%m")
        if p is None:
            u["cost"], u["reason"] = None, reason
            continue
        cached_rate = p["cached"] if p["cached"] is not None else p["in"]
        if u["cached"] and p["cached"] is None:
            notes.add(u["model"])
        u["cost"] = ((u["input"] - u["cached"]) * p["in"] + u["cached"] * cached_rate
                     + u["output"] * p["out"]) / MILLION
        u["reason"] = ""
    return notes


def _agg(rows, keyf):
    out: dict = {}
    for u in rows:
        k = keyf(u)
        a = out.setdefault(k, {"requests": 0, "input": 0, "output": 0, "cost": Decimal(0)})
        a["requests"] += u["requests"]
        a["input"] += u["input"]
        a["output"] += u["output"]
        a["cost"] += u["cost"]
    return out


def prev_month(m: str) -> str:
    y, mo = int(m[:4]), int(m[5:])
    return f"{y - 1}-12" if mo == 1 else f"{y}-{mo - 1:02d}"


def pct(n: Decimal, d: Decimal) -> str:
    return dp(n / d * 100, 2) if d else "n/a"


def showback(usage):
    priced = [u for u in usage if u["cost"] is not None]
    unpriced = [u for u in usage if u["cost"] is None]
    grand = sum((u["cost"] for u in priced), Decimal(0))
    months = _agg(priced, lambda u: u["month"])
    rows = []

    def row(level, month, team, feature, model, a, share, mom="", reason=""):
        req = a["requests"]
        rows.append({"level": level, "month": month, "team": team, "feature": feature, "model": model,
                     "requests": req, "input_tokens": a["input"], "output_tokens": a["output"],
                     "cost_usd": money(a["cost"]), "cost_per_1k_requests": dp(a["cost"] / req * 1000, 4) if req else "n/a",
                     "share": share, "mom_change_pct": mom, "_cost": a["cost"], "reason": reason})

    if priced:
        row("total", "*", "*", "*", "*", _agg(priced, lambda u: 0)[0], pct(grand, grand))
    for m, a in sorted(months.items()):
        pm = months.get(prev_month(m))
        row("month", m, "*", "*", "*", a, pct(a["cost"], grand),
            pct(a["cost"] - pm["cost"], pm["cost"]) if pm else "n/a")
    mt = _agg(priced, lambda u: (u["month"], u["team"]))
    for (m, t), a in sorted(mt.items()):
        pm = mt.get((prev_month(m), t))
        row("month_team", m, t, "*", "*", a, pct(a["cost"], months[m]["cost"]),
            pct(a["cost"] - pm["cost"], pm["cost"]) if pm else "n/a")
    for t, a in sorted(_agg(priced, lambda u: u["team"]).items()):
        row("team", "*", t, "*", "*", a, pct(a["cost"], grand))
    for (t, f), a in sorted(_agg(priced, lambda u: (u["team"], u["feature"])).items()):
        row("team_feature", "*", t, f, "*", a, pct(a["cost"], grand))
    for mdl, a in sorted(_agg(priced, lambda u: u["model"]).items()):
        row("model", "*", "*", "*", mdl, a, pct(a["cost"], grand))
    for (m, t, f, mdl), a in sorted(_agg(priced, lambda u: (u["month"], u["team"], u["feature"], u["model"])).items()):
        row("detail", m, t, f, mdl, a, pct(a["cost"], months[m]["cost"]))
    un: dict = {}
    for u in unpriced:
        k = (u["month"], u["team"], u["feature"], u["model"], u["reason"])
        a = un.setdefault(k, {"requests": 0, "input": 0, "output": 0})
        a["requests"] += u["requests"]
        a["input"] += u["input"]
        a["output"] += u["output"]
    for (m, t, f, mdl, reason), a in sorted(un.items()):
        rows.append({"level": "detail", "month": m, "team": t, "feature": f, "model": mdl,
                     "requests": a["requests"], "input_tokens": a["input"], "output_tokens": a["output"],
                     "cost_usd": TBD, "cost_per_1k_requests": TBD, "share": TBD, "mom_change_pct": "",
                     "_cost": None, "reason": reason})
    return rows, grand


def anomalies(usage):
    daily: dict = {}
    by_feat: dict = {}
    for u in usage:
        if u["cost"] is None:
            continue
        daily.setdefault(u["team"], {}).setdefault(u["date"], Decimal(0))
        daily[u["team"]][u["date"]] += u["cost"]
        k = (u["team"], u["date"], u["feature"])
        by_feat[k] = by_feat.get(k, Decimal(0)) + u["cost"]
    out = []
    for team in sorted(daily):
        series = daily[team]
        first = min(series)
        for d in sorted(series):
            window = [d - timedelta(days=i) for i in range(1, WINDOW_DAYS + 1)]
            window = [w for w in window if w >= first]
            if len(window) < MIN_PRIOR_DAYS:
                continue
            vals = [series.get(w, Decimal(0)) for w in window]
            n = Decimal(len(vals))
            mean = sum(vals, Decimal(0)) / n
            var = sum(((v - mean) ** 2 for v in vals), Decimal(0)) / (n - 1)
            sd = var.sqrt()
            threshold = mean + SIGMA * sd
            cost = series[d]
            if cost > threshold:
                feats = sorted(((c, f) for (t, dd, f), c in by_feat.items() if t == team and dd == d),
                               key=lambda x: (-x[0], x[1]))
                out.append({"date": d.isoformat(), "team": team, "cost_usd": money(cost),
                            "trailing_mean_usd": dp(mean, 4), "trailing_sd_usd": dp(sd, 4),
                            "threshold_usd": dp(threshold, 4), "excess_usd": money(cost - threshold),
                            "prior_days": len(vals), "top_feature": feats[0][1] if feats else ""})
    return out


def budgets_table(usage, budgets, as_of: date):
    actual: dict = {}
    unpriced_req: dict = {}
    for u in usage:
        k = (u["team"], u["month"])
        actual.setdefault(k, Decimal(0))
        if u["cost"] is None:
            unpriced_req[k] = unpriced_req.get(k, 0) + u["requests"]
        else:
            actual[k] += u["cost"]
    keys = sorted(set(actual) | set(budgets), key=lambda k: (k[1], k[0]))
    as_of_m = as_of.strftime("%Y-%m")
    out = []
    for team, month in keys:
        act = actual.get((team, month), Decimal(0))
        y, mo = int(month[:4]), int(month[5:])
        dim = calendar.monthrange(y, mo)[1]
        if month < as_of_m:
            fc, basis, elapsed = act, "closed month", dim
        elif month == as_of_m:
            elapsed = as_of.day
            fc, basis = act / elapsed * dim, "linear run-rate"
        else:
            fc, basis, elapsed = None, "not started", 0
        b = budgets.get((team, month))
        if fc is None:
            status = "NOT STARTED"
        elif b is None:
            status = "NO BUDGET"
        else:
            status = "OVER BUDGET" if fc > b else "WITHIN BUDGET"
        out.append({"team": team, "month": month, "budget": money(b) if b is not None else TBD,
                    "actual": money(act), "forecast": money(fc) if fc is not None else "n/a",
                    "variance": money(b - fc) if (b is not None and fc is not None) else
                    ("n/a" if fc is None else TBD),
                    "status": status, "basis": basis, "days_elapsed": elapsed, "days_in_month": dim,
                    "unpriced_requests": unpriced_req.get((team, month), 0)})
    return out


# ------------------------------------------------------------------ rendering

SHOWBACK_FIELDS = ["level", "month", "team", "feature", "model", "requests", "cost_usd", "cost_per_1k_requests",
                   "share", "mom_change_pct", "input_tokens", "output_tokens"]
ANOMALY_FIELDS = ["date", "team", "cost_usd", "trailing_mean_usd", "trailing_sd_usd", "threshold_usd",
                  "excess_usd", "prior_days", "top_feature"]
BUDGET_FIELDS = ["team", "month", "budget", "actual", "forecast", "variance", "status", "basis", "days_elapsed",
                 "days_in_month", "unpriced_requests"]


def csv_text(fields, rows) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: csv_safe(v) for k, v in r.items()})
    return buf.getvalue()


def usd(s: str) -> str:
    return f"${s}" if s and (s[0].isdigit() or s[0] == "-") else s  # negatives as $-1.23 so figures trace to the CSVs


def render_md(usage_name, prices_name, budgets_name, usage, sb, anoms, bud, as_of, notes, strict, dups=()) -> str:
    by = {lvl: [r for r in sb if r["level"] == lvl] for lvl in LEVELS}
    total = by["total"][0] if by["total"] else None
    unpriced = [r for r in by["detail"] if r["_cost"] is None]
    over = [b for b in bud if b["status"] == "OVER BUDGET"]
    first, last = min(u["date"] for u in usage), max(u["date"] for u in usage)
    teams = sorted({u["team"] for u in usage})
    lines = ["# AI FinOps showback", "",
             f"Usage: `{usage_name}` · prices: `{prices_name}` · budgets: "
             + (f"`{budgets_name}`" if budgets_name else f"not supplied — every budget is {TBD}"), "",
             "## Summary", "",
             f"- Priced AI spend {first.isoformat()} to {last.isoformat()}: **{usd(total['cost_usd']) if total else '$0.00'}**"
             f" across {len(teams)} team(s); as-of date {as_of.isoformat()}.",
             f"- Budgets over forecast: {len(over)}" + (" — " + ", ".join(f"{b['team']} {b['month']}" for b in over)
                                                       if over else "") + ".",
             f"- Cost anomalies (team-days above mean + 3 sd of the trailing 14 days): {len(anoms)}.",
             f"- Unpriced usage groups: {len(unpriced)}" + (f" — cost {TBD}; excluded from every total."
                                                            if unpriced else "."),
             ]
    if dups:
        lines.append(f"- Exact-duplicate usage rows: {len(dups)} group(s) (usage lines "
                     + "; ".join(", ".join(str(n) for n in g) for g in dups)
                     + ") — summed as supplied; confirm they are separate usage, not a re-exported row "
                     f"(double count). Owner: {TBD}.")
    if strict and over:
        lines.append("- `--strict` was set and a forecast is over budget: the run fails (exit 1).")
    lines += ["", "## Spend by team", "",
              "| Team | Month | Spend | Share of month | Change vs prior month |", "|---|---|---|---|---|"]
    for r in by["month_team"]:
        mom = f"{r['mom_change_pct']}%" if r["mom_change_pct"] not in ("", "n/a") else "n/a"
        lines.append(f"| {r['team']} | {r['month']} | {usd(r['cost_usd'])} | {r['share']}% | {mom} |")
    lines += ["", "| Team | Total spend | Share of total |", "|---|---|---|"]
    for r in by["team"]:
        lines.append(f"| {r['team']} | {usd(r['cost_usd'])} | {r['share']}% |")
    lines += ["", "| Month | Spend | Change vs prior month |", "|---|---|---|"]
    for r in by["month"]:
        mom = f"{r['mom_change_pct']}%" if r["mom_change_pct"] not in ("", "n/a") else "n/a"
        lines.append(f"| {r['month']} | {usd(r['cost_usd'])} | {mom} |")
    as_of_m = as_of.strftime("%Y-%m")
    dim = calendar.monthrange(as_of.year, as_of.month)[1]
    if as_of.day < dim and any(r["month"] == as_of_m for r in by["month"]):
        lines += ["", f"{as_of_m} is partial ({as_of.day} of {dim} days to the as-of date): its change vs the prior "
                      "month compares a partial month with a full one; use the Budgets forecast for the full month."]
    lines += ["", "## Unit economics", "",
              "| Team | Feature | Priced requests | Spend | Cost per 1k requests | Share of total |",
              "|---|---|---|---|---|---|"]
    for r in by["team_feature"]:
        lines.append(f"| {r['team']} | {r['feature']} | {r['requests']} | {usd(r['cost_usd'])} | "
                     f"{usd(r['cost_per_1k_requests'])} | {r['share']}% |")
    lines += ["", "| Model | Priced requests | Spend | Cost per 1k requests | Share of total |", "|---|---|---|---|---|"]
    for r in by["model"]:
        lines.append(f"| {r['model']} | {r['requests']} | {usd(r['cost_usd'])} | {usd(r['cost_per_1k_requests'])} | "
                     f"{r['share']}% |")
    lines += ["", "## Anomalies", ""]
    if not anoms:
        lines.append("None: no team-day exceeded mean + 3 sd of its trailing 14 days.")
    else:
        lines += ["| Date | Team | Spend | Trailing mean | Trailing sd | Threshold | Excess | Prior days | Top feature |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for a in anoms:
            lines.append(f"| {a['date']} | {a['team']} | {usd(a['cost_usd'])} | {usd(a['trailing_mean_usd'])} | "
                         f"{usd(a['trailing_sd_usd'])} | {usd(a['threshold_usd'])} | {usd(a['excess_usd'])} | "
                         f"{a['prior_days']} | {a['top_feature']} |")
        lines += ["", "Owner for each anomaly: the team's engineering lead confirms cause (release, traffic, "
                      "prompt change, abuse) before any chargeback adjustment."]
    lines += ["", "## Budgets", "",
              "| Team | Month | Budget | Actual | Forecast | Variance | Status | Basis |",
              "|---|---|---|---|---|---|---|---|"]
    for b in bud:
        lines.append(f"| {b['team']} | {b['month']} | {usd(b['budget'])} | {usd(b['actual'])} | {usd(b['forecast'])} | "
                     f"{usd(b['variance'])} | {b['status']} | {b['basis']} |")
    if any(b["unpriced_requests"] for b in bud):
        lines += ["", "Actual and forecast exclude unpriced usage, so they understate spend for: "
                  + ", ".join(f"{b['team']} {b['month']}" for b in bud if b["unpriced_requests"]) + "."]
    lines += ["", "## Unpriced usage", ""]
    if not unpriced:
        lines.append("None: every usage row had a price in effect on its date.")
    else:
        lines += ["| Month | Team | Feature | Model | Requests | Reason | Cost |", "|---|---|---|---|---|---|---|"]
        for r in unpriced:
            lines.append(f"| {r['month']} | {r['team']} | {r['feature']} | {r['model']} | {r['requests']} | "
                         f"{r['reason']} | {TBD} |")
        lines += ["", "Add a dated price row for each model (FinOps lead, from the vendor contract or price page) "
                      "and re-run; no price is estimated."]
    lines += ["", "## Method", "",
              "- Cost per usage row = ((input − cached) × input price + cached × cached price + output × output "
              "price) ÷ 1M tokens, using the price row with the latest `effective_from` on or before the usage date.",
              ]
    if notes:
        lines.append("- No cached-input price in the sheet for " + ", ".join(sorted(notes))
                     + ": cached input tokens are charged at the full input price.")
    lines += ["- Full precision internally; money is rounded half-up to cents only when written. Each rollup is "
              "rounded from its full-precision sum, so it can differ from the sum of its rounded rows by under "
              "half a cent per row.",
              "- Cost per 1k requests = spend ÷ priced requests, 4 decimals. Share = % of the month's priced spend for "
              "month-team rows, of all priced spend otherwise.",
              "- Anomaly: a team-day whose spend exceeds mean + 3 × sample sd of the team's previous 14 calendar days "
              "(days without usage count as zero; days before the team's first usage are not counted); at least 7 "
              "prior days are required. Trailing mean, sd and threshold are shown to 4 decimals.",
              "- Forecast: a closed month's forecast is its actual; the as-of month is projected by linear run-rate "
              "(actual ÷ days elapsed × days in month); later months are not started. As-of defaults to the latest "
              "usage date, never today. Variance = budget − forecast.",
              f"- Prices are taken as supplied in `{prices_name}`; this report does not verify them against vendor "
              "price pages or invoices. Showback figures are allocations of metered usage, not an invoice "
              "reconciliation.", ""]
    return "\n".join(lines)


def produce(args):
    usage = load_usage(args.usage)
    prices = load_prices(args.prices)
    budgets = load_budgets(args.budgets)
    last = max(u["date"] for u in usage)
    as_of = to_date(args.as_of, "--as-of") if args.as_of else last
    if as_of < last:
        raise InputError(f"--as-of {as_of.isoformat()} is before the latest usage date {last.isoformat()}")
    notes = cost_rows(usage, prices)
    dups = duplicate_rows(usage)
    sb, _ = showback(usage)
    anoms = anomalies(usage)
    bud = budgets_table(usage, budgets, as_of)
    files = {
        "showback.csv": csv_text(SHOWBACK_FIELDS, sb),
        "anomalies.csv": csv_text(ANOMALY_FIELDS, anoms),
        "budget.csv": csv_text(BUDGET_FIELDS, bud),
        "finops-report.md": render_md(Path(args.usage).name, Path(args.prices).name,
                                      Path(args.budgets).name if args.budgets else None,
                                      usage, sb, anoms, bud, as_of, notes, args.strict, dups),
    }
    if dups and not args.verify:
        print(f"warning: {len(dups)} group(s) of exact-duplicate usage rows (lines "
              + "; ".join(", ".join(str(n) for n in g) for g in dups) + ") were summed; check for a double count",
              file=sys.stderr)
    return files, bud


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--usage", help="usage CSV (assets/usage-template.csv)")
    ap.add_argument("--prices", help="dated price sheet CSV (assets/prices-template.csv)")
    ap.add_argument("--budgets", default="", help="budgets CSV team,month,budget_usd (optional)")
    ap.add_argument("--as-of", default="", help="as-of date YYYY-MM-DD for forecasts (default: latest usage date)")
    ap.add_argument("--strict", action="store_true", help="exit 1 when any team forecast is over budget")
    ap.add_argument("--out-dir", type=Path, help="directory for the four outputs")
    ap.add_argument("--verify", type=Path, metavar="FILE", help="re-check FILE against the inputs (exit 0 = match)")
    args = ap.parse_args(argv)
    args.budgets = args.budgets or None
    try:
        if not args.verify and not args.out_dir:
            raise InputError("--out-dir is required")
        files, bud = produce(args)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.verify:
        name = args.verify.name
        if name not in files or not args.verify.is_file():
            print(f"verify: {args.verify} is not a file this skill produces ({', '.join(files)})", file=sys.stderr)
            return 1
        ok = args.verify.read_text(encoding="utf-8") == files[name]
        print(f"verify {name}: {'match' if ok else 'MISMATCH — output does not match the inputs'}")
        return 0 if ok else 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (args.out_dir / name).write_text(text, encoding="utf-8")
    over = [b for b in bud if b["status"] == "OVER BUDGET"]
    print(f"budgets over forecast: {len(over)}")
    if args.strict and over:
        print("strict: forecast over budget for " + ", ".join(f"{b['team']} {b['month']}" for b in over),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

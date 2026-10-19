#!/usr/bin/env python3
"""Service-level objectives for an AI feature, measured from a request log (stdlib only).

SLIs (each a good-events / eligible-events ratio):
  availability  eligible: every request            good: status == ok
  latency       eligible: ok requests with latency good: latency_ms <= threshold
  quality       eligible: rows with quality_pass   good: quality_pass == 1
  cost          eligible: rows with cost_usd       good: cost_usd <= threshold
Error budget = 1 - objective. Budget consumed = (1 - SLI) / (1 - objective) over the whole log
(= the burn rate over the log span). Burn rate per window = window error ratio / (1 - objective),
windows anchored at the last timestamp in the log: 1h/5m and 6h/30m (page), 3d/6h (ticket) — the
Google SRE workbook multiwindow, multi-burn-rate policy (references/sources.md). Burn thresholds
scale with the SLO window: budget share (2%, 5%, 10%) x window hours / long-window hours, i.e.
14.4, 6 and 1 for a 30-day window.

Without a target for an SLI, an objective is PROPOSED from the data and labelled
[TO BE BASELINED — owner: Product owner]: availability/quality = highest standard level not above
the observed SLI; latency = observed p95 of ok requests rounded up to the next 100 ms at 0.95;
cost = observed p95 cost rounded up to the next 0.001 at 0.95.

Usage:
  python3 -I slo.py --log requests.csv [--targets targets.csv] [--system NAME] --out-dir OUT
  python3 -I slo.py --verify OUT/slos.csv          # re-derives statuses from slo.json

log CSV: timestamp (ISO-8601), latency_ms, status (ok|error), quality_pass (0|1, optional),
         cost_usd (optional). Lines starting with '#' are comments.
targets CSV: sli,objective,threshold,window_days (threshold required for latency and cost).
Outputs (in --out-dir): slos.csv, slo-spec.md, slo.json.
Exit codes: 0 no agreed SLO breached · 1 an agreed SLO is breached (budget consumed > 1; outputs
still written) · 2 missing/invalid input. No network; writes only inside --out-dir.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path

SLIS = ("availability", "latency", "quality", "cost")
TBD_PO = "[TO BE BASELINED — owner: Product owner]"
TBD_SRE = "[TO BE BASELINED — owner: SRE lead]"
TBD_EVAL = "[TO BE BASELINED — owner: Eval lead]"
TBD_FINOPS = "[TO BE BASELINED — owner: FinOps lead]"
LADDER = {"availability": ["0.9", "0.95", "0.99", "0.995", "0.999", "0.9995", "0.9999"],
          "quality": ["0.8", "0.85", "0.9", "0.95", "0.98", "0.99"]}
PROPOSED_PCT_OBJECTIVE = "0.95"
REFERENCE_WINDOW_DAYS = "30"  # SRE workbook's reference period for the 14.4 / 6 / 1 thresholds
# (name, long window, short window, budget share, notification) — SRE workbook table 5-8
POLICY = [("fast-burn page", timedelta(hours=1), timedelta(minutes=5), Fraction(2, 100), "page"),
          ("slow-burn page", timedelta(hours=6), timedelta(minutes=30), Fraction(5, 100), "page"),
          ("ticket", timedelta(days=3), timedelta(hours=6), Fraction(10, 100), "ticket")]
CSV_COLS = ["sli", "objective", "threshold", "observed", "budget_consumed", "burn_rate", "status", "note"]
DEFINITION = {
    "availability": "ok requests / all requests",
    "latency": "ok requests with latency_ms <= threshold / ok requests with a latency",
    "quality": "rows with quality_pass = 1 / rows with quality_pass",
    "cost": "rows with cost_usd <= threshold / rows with cost_usd",
}
UNIT = {"latency": "ms", "cost": "USD"}


class InputError(Exception):
    """Missing or invalid input -> exit 2."""


# ------------------------------------------------------------------ formatting
def dec(fr: Fraction, places: int) -> str:
    q = Decimal(1).scaleb(-places)
    return str((Decimal(fr.numerator) / Decimal(fr.denominator)).quantize(q, rounding=ROUND_HALF_UP))


def num(s: str) -> str:
    """Normalise a decimal string ('0.9950' -> '0.995', '2000.0' -> '2000')."""
    d = Decimal(s).normalize()
    return format(d, "f")


def opt(fr, places=3) -> str:
    return "n/a" if fr is None else dec(fr, places)


# ------------------------------------------------------------------ input
def read_rows(path: str, label: str) -> tuple[list[str], list[dict]]:
    p = Path(path)
    if not p.is_file():
        raise InputError(f"{label} file not found: {path}")
    lines = [ln for ln in p.read_text(encoding="utf-8-sig").splitlines() if not ln.startswith("#")]
    rd = csv.DictReader(io.StringIO("\n".join(lines)))
    if not rd.fieldnames:
        raise InputError(f"{label} has no header row: {path}")
    cols = [c.strip() for c in rd.fieldnames]
    rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in rd]
    return cols, rows


def parse_dec(v: str, what: str) -> Decimal:
    try:
        d = Decimal(v)
    except InvalidOperation:
        raise InputError(f"{what}: '{v}' is not a number") from None
    if not d.is_finite() or d < 0:
        raise InputError(f"{what}: '{v}' must be a non-negative number")
    return d


def parse_ts(v: str, line: int) -> datetime:
    s = v.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        raise InputError(f"log line {line}: timestamp '{v}' is not ISO-8601") from None


def read_log(path: str) -> tuple[list[dict], set]:
    cols, rows = read_rows(path, "log")
    missing = [c for c in ("timestamp", "latency_ms", "status") if c not in cols]
    if missing:
        raise InputError(f"log is missing required column(s): {', '.join(missing)}")
    if not rows:
        raise InputError("log has no data rows")
    out = []
    aware = set()
    for i, r in enumerate(rows, start=2):
        ts = parse_ts(r["timestamp"], i)
        aware.add(ts.tzinfo is not None)
        st = r["status"].lower()
        if st not in ("ok", "error"):
            raise InputError(f"log line {i}: status '{r['status']}' must be ok or error")
        lat = parse_dec(r["latency_ms"], f"log line {i} latency_ms") if r["latency_ms"] else None
        q = r.get("quality_pass", "")
        if q not in ("", "0", "1"):
            raise InputError(f"log line {i}: quality_pass '{q}' must be 0, 1 or blank")
        c = r.get("cost_usd", "")
        out.append({"ts": ts, "ok": st == "ok", "latency": lat,
                    "quality": None if q == "" else q == "1",
                    "cost": parse_dec(c, f"log line {i} cost_usd") if c else None})
    if len(aware) > 1:
        raise InputError("log mixes timestamps with and without a UTC offset")
    out.sort(key=lambda e: e["ts"])
    return out, set(cols)


def read_targets(path: str | None) -> dict:
    if not path:
        return {}
    cols, rows = read_rows(path, "targets")
    if "sli" not in cols or "objective" not in cols:
        raise InputError("targets needs columns sli,objective[,threshold,window_days]")
    out = {}
    for r in rows:
        sli = r["sli"].lower()
        if sli not in SLIS:
            raise InputError(f"targets: unknown sli '{r['sli']}' (allowed: {', '.join(SLIS)})")
        if sli in out:
            raise InputError(f"targets: sli '{sli}' listed twice")
        o = parse_dec(r["objective"], f"targets {sli} objective") if r["objective"] else None
        if o is None or not (0 < o < 1):
            raise InputError(f"targets: {sli} objective must be between 0 and 1 (exclusive), e.g. 0.995")
        th = r.get("threshold", "")
        if sli in ("latency", "cost"):
            if not th:
                raise InputError(f"targets: {sli} needs a threshold ({UNIT[sli]})")
            th = num(str(parse_dec(th, f"targets {sli} threshold")))
        elif th:
            raise InputError(f"targets: {sli} takes no threshold")
        wd = r.get("window_days", "")
        if wd:
            d = parse_dec(wd, f"targets {sli} window_days")
            if d <= 0:
                raise InputError(f"targets: {sli} window_days must be > 0")
            wd = num(str(d))
        out[sli] = {"objective": num(str(o)), "threshold": th or "", "window_days": wd or ""}
    return out


# ------------------------------------------------------------------ math
def nearest_rank(sorted_vals: list, p: int):
    """Nearest-rank percentile: value at rank ceil(p/100 * n) (1-based)."""
    n = len(sorted_vals)
    return sorted_vals[max(1, math.ceil(p * n / 100)) - 1]


def events(sli: str, log: list[dict], threshold: str):
    th = Decimal(threshold) if threshold else None
    if sli == "availability":
        return [(e["ts"], e["ok"]) for e in log]
    if sli == "latency":
        return [(e["ts"], e["latency"] <= th) for e in log if e["ok"] and e["latency"] is not None]
    if sli == "quality":
        return [(e["ts"], e["quality"]) for e in log if e["quality"] is not None]
    return [(e["ts"], e["cost"] <= th) for e in log if e["cost"] is not None]


def window_counts(ev, end: datetime, start_ts: datetime, w: timedelta):
    """(bad, total) for events with t > end - w; None when the log does not cover the window."""
    if start_ts > end - w:
        return None
    sel = [g for t, g in ev if t > end - w]
    return (sum(1 for g in sel if not g), len(sel))


def burn(counts, objective: str):
    if counts is None or counts[1] == 0:
        return None
    return Fraction(counts[0], counts[1]) / (1 - Fraction(objective))


def burn_threshold(share: Fraction, window_days: str, long_w: timedelta) -> Fraction:
    return share * Fraction(window_days) * 24 / Fraction(int(long_w.total_seconds()), 3600)


def propose(sli: str, sli_value: Fraction, log: list[dict]) -> tuple[str, str]:
    """(objective, threshold) proposed from the data; objective '' when no standard level fits."""
    if sli in LADDER:
        fits = [x for x in LADDER[sli] if Fraction(x) <= sli_value]
        return (fits[-1] if fits else ""), ""
    if sli == "latency":
        vals = sorted(e["latency"] for e in log if e["ok"] and e["latency"] is not None)
        p95 = nearest_rank(vals, 95)
        return PROPOSED_PCT_OBJECTIVE, num(str((p95 / 100).to_integral_value(rounding=ROUND_CEILING) * 100))
    vals = sorted(e["cost"] for e in log if e["cost"] is not None)
    p95 = nearest_rank(vals, 95)
    return PROPOSED_PCT_OBJECTIVE, num(str(p95.quantize(Decimal("0.001"), rounding=ROUND_CEILING)))


def status_of(kind: str, consumed, alerts: list[dict]) -> str:
    if kind == "proposed":
        return "proposed"
    if consumed is not None and consumed > 1:
        return "breached"
    if any(a["fires"] for a in alerts):
        return "at-risk"
    return "met"


def evaluate(sli, objective, threshold, window_days, kind, log):
    ev = events(sli, log, threshold)
    bad = sum(1 for _, g in ev if not g)
    total = len(ev)
    end, start = log[-1]["ts"], log[0]["ts"]
    rec = {"sli": sli, "kind": kind, "objective": objective, "threshold": threshold,
           "window_days": window_days, "bad": bad, "total": total, "alerts": []}
    if not objective:
        rec.update(status="proposed", consumed=None, burn_1h=None)
        return rec
    consumed = Fraction(bad, total) / (1 - Fraction(objective))
    wd = window_days or REFERENCE_WINDOW_DAYS
    for name, lw, sw, share, note in POLICY:
        lc, sc = window_counts(ev, end, start, lw), window_counts(ev, end, start, sw)
        lb, sb = burn(lc, objective), burn(sc, objective)
        thr = burn_threshold(share, wd, lw)
        fires = lb is not None and sb is not None and lb >= thr and sb >= thr
        rec["alerts"].append({"name": name, "long_window_h": lw.total_seconds() / 3600,
                              "short_window_h": sw.total_seconds() / 3600, "budget_share": str(share),
                              "notification": note, "threshold": thr, "long": lc, "short": sc,
                              "long_burn": lb, "short_burn": sb, "fires": fires})
    rec["consumed"] = consumed
    rec["burn_1h"] = rec["alerts"][0]["long_burn"]
    rec["status"] = status_of(kind, consumed, rec["alerts"])
    return rec


# ------------------------------------------------------------------ outputs
def note_of(r: dict) -> str:
    if r["kind"] == "proposed":
        return TBD_PO if r["objective"] else f"no standard level fits the observed SLI; objective {TBD_PO}"
    return "agreed target"


def csv_row(r: dict) -> list[str]:
    obs = Fraction(r["total"] - r["bad"], r["total"])
    return [r["sli"], r["objective"] or TBD_PO, r["threshold"], dec(obs, 5), opt(r["consumed"]),
            opt(r["burn_1h"]), r["status"], note_of(r)]


def write_csv(recs) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLS)
    for r in recs:
        w.writerow(csv_row(r))
    return buf.getvalue()


def md_slo_row(r: dict) -> str:
    c = csv_row(r)
    th = f"{c[2]} {UNIT[r['sli']]}" if c[2] else "—"
    return f"| {c[0]} | {DEFINITION[r['sli']]} | {c[1]} | {th} | {c[3]} | {r['total']} | {c[6]} | {c[7]} |"


def write_md(doc: dict, recs: list[dict]) -> str:
    s = doc["summary"]
    L = [f"# SLO specification — {doc['system']}", "", "## Summary", ""]
    breached = [r["sli"] for r in recs if r["status"] == "breached"]
    at_risk = [r["sli"] for r in recs if r["status"] == "at-risk"]
    agreed = [r for r in recs if r["kind"] == "agreed"]
    if breached:
        L.append(f"**BREACHED: {', '.join(breached)}.** The error budget for these SLOs is spent over the log window.")
    elif at_risk:
        L.append(f"**AT RISK: {', '.join(at_risk)}.** A burn-rate alert condition is true at the end of the log.")
    elif agreed:
        L.append("**All agreed SLOs met.**")
    else:
        L.append(f"**No agreed targets.** Every objective below is a proposal from observed data: {TBD_PO}.")
    if agreed and len(agreed) < len(recs):
        L.append(f"SLIs without an agreed target carry a proposed objective: {TBD_PO}.")
    L += ["",
          f"Log: `{doc['log']}` · {s['requests']} requests · {s['first']} to {s['last']} ({s['span_hours']} h).",
          f"Observed latency (ok requests, nearest-rank): p50 {s['p50_ms']} ms · p95 {s['p95_ms']} ms · p99 {s['p99_ms']} ms.",
          f"Cost per request: {s['cost_per_request']} USD (mean over {s['cost_rows']} rows with cost)."
          if s["cost_rows"] else f"Cost per request: not in the log — {TBD_FINOPS}.", ""]
    for m in doc["not_measured"]:
        L.append(f"- {m}")
    if doc["not_measured"]:
        L.append("")
    L += ["## SLIs and objectives", "",
          "| SLI | Definition (good / eligible) | Objective | Threshold | Observed | Eligible events | Status | Note |",
          "|---|---|---|---|---|---|---|---|"]
    L += [md_slo_row(r) for r in recs]
    L += ["", "## Error budgets", "",
          "| SLI | Error budget (1 − objective) | Bad / eligible events | Budget consumed | Burn rate, last 1 h | Budget spent to date |",
          "|---|---|---|---|---|---|"]
    for r in recs:
        if not r["objective"]:
            L.append(f"| {r['sli']} | {TBD_PO} | {r['bad']} / {r['total']} | n/a | n/a | n/a |")
            continue
        budget = 1 - Fraction(r["objective"])
        if r["window_days"]:
            spent = dec(r["consumed"] * Fraction(s["span_seconds"], 86400) / Fraction(r["window_days"]), 3)
        else:
            spent = f"window {TBD_SRE}"
        L.append(f"| {r['sli']} | {dec(budget, 6).rstrip('0').rstrip('.')} | {r['bad']} / {r['total']} | "
                 f"{opt(r['consumed'])} | {opt(r['burn_1h'])} | {spent} |")
    L += ["", "Budget consumed = (1 − SLI) / (1 − objective) over the log: the share of the window's budget used "
          "if the log is representative of the whole SLO window. Above 1.000 the SLO is breached. "
          "Budget spent to date scales it by log span ÷ SLO window.", ""]
    L += ["## Alerting policy", "",
          "Multiwindow, multi-burn-rate alerts (Google SRE workbook, ch. 5): an alert fires when the burn rate over "
          "both the long and the short window is at or above the threshold. Threshold = budget share × SLO window hours "
          "÷ long-window hours (14.4, 6 and 1 for a 30-day window). Windows end at the last log timestamp; "
          "n/a = the log does not cover the window.", ""]
    no_window = [r["sli"] for r in recs if r["objective"] and not r["window_days"]]
    if no_window:
        L.append(f"SLO window for {', '.join(no_window)}: {TBD_SRE}; thresholds below use the workbook's "
                 f"{REFERENCE_WINDOW_DAYS}-day reference window.")
        L.append("")
    L += ["| SLI | Alert | Long / short window | Burn threshold | Long burn | Short burn | Fires | Notify |",
          "|---|---|---|---|---|---|---|---|"]
    for r in recs:
        for a in r["alerts"]:
            L.append(f"| {r['sli']} | {a['name']} | {fmt_h(a['long_window_h'])} / {fmt_h(a['short_window_h'])} | "
                     f"{dec(a['threshold'], 2)} | {opt(a['long_burn'])} | {opt(a['short_burn'])} | "
                     f"{'yes' if a['fires'] else 'no'} | {a['notification']} |")
    L += ["", "## Method", "",
          "- Percentiles are nearest-rank: the value at rank ceil(p/100 × n) of the sorted values.",
          "- Latency counts ok requests only (errors already count against availability); \"under threshold\" means <= threshold.",
          "- Proposals: availability and quality take the highest standard level not above the observed SLI "
          f"({', '.join(LADDER['availability'])} / {', '.join(LADDER['quality'])}); latency and cost take the observed "
          "p95 rounded up (100 ms / 0.001 USD) at objective 0.95. A proposal describes today's behaviour; it is not a commitment.",
          "- Status: breached when budget consumed > 1; at-risk when any burn-rate alert fires at the end of the log; "
          "otherwise met. Proposed objectives are never gated.",
          "- Limits: the log is a sample; a short log cannot show the 6 h or 3 d windows; quality depends on how "
          "quality_pass was labelled (eval or user feedback); cost covers only rows that carry cost_usd."]
    return "\n".join(L) + "\n"


def fmt_h(h: float) -> str:
    if h < 1:
        return f"{int(round(h * 60))} m"
    if h >= 24 and h % 24 == 0:
        return f"{int(h // 24)} d"
    return f"{int(h)} h"


def frac_json(x):
    return None if x is None else {"num": x.numerator, "den": x.denominator, "value": round(float(x), 9)}


def rec_json(r: dict) -> dict:
    d = {k: r[k] for k in ("sli", "kind", "objective", "threshold", "window_days", "bad", "total", "status")}
    d["observed"] = dec(Fraction(r["total"] - r["bad"], r["total"]), 5)
    d["budget_consumed"] = frac_json(r["consumed"])
    d["burn_rate_1h"] = frac_json(r["burn_1h"])
    d["alerts"] = [{"name": a["name"], "long_window_h": a["long_window_h"], "short_window_h": a["short_window_h"],
                    "budget_share": a["budget_share"], "notification": a["notification"],
                    "threshold": frac_json(a["threshold"]), "long": list(a["long"]) if a["long"] else None,
                    "short": list(a["short"]) if a["short"] else None, "long_burn": frac_json(a["long_burn"]),
                    "short_burn": frac_json(a["short_burn"]), "fires": a["fires"]} for a in r["alerts"]]
    return d


def run(args) -> int:
    if not args.log:
        raise InputError("--log is required")
    if not args.out_dir:
        raise InputError("--out-dir is required")
    log, cols = read_log(args.log)
    targets = read_targets(args.targets)
    recs, not_measured = [], []
    for sli in SLIS:
        t = targets.get(sli)
        probe = events(sli, log, (t or {}).get("threshold") or "0")
        if not probe:
            if t:
                raise InputError(f"targets set {sli} but the log has no eligible rows for it")
            owner = {"availability": TBD_SRE, "latency": TBD_SRE, "quality": TBD_EVAL, "cost": TBD_FINOPS}[sli]
            col = {"quality": "quality_pass", "cost": "cost_usd"}.get(sli, "latency_ms")
            not_measured.append(f"{sli}: not measured — the log has no `{col}` values; {owner}.")
            continue
        if t:
            recs.append(evaluate(sli, t["objective"], t["threshold"], t["window_days"], "agreed", log))
        else:
            good = sum(1 for _, g in probe if g)
            obj, th = propose(sli, Fraction(good, len(probe)), log)
            recs.append(evaluate(sli, obj, th, "", "proposed", log))
    lat = sorted(e["latency"] for e in log if e["ok"] and e["latency"] is not None)
    costs = [e["cost"] for e in log if e["cost"] is not None]
    span = log[-1]["ts"] - log[0]["ts"]
    summary = {"requests": len(log), "first": log[0]["ts"].isoformat(), "last": log[-1]["ts"].isoformat(),
               "span_seconds": int(span.total_seconds()),
               "span_hours": dec(Fraction(int(span.total_seconds()), 3600), 2),
               "p50_ms": num(str(nearest_rank(lat, 50))) if lat else "n/a",
               "p95_ms": num(str(nearest_rank(lat, 95))) if lat else "n/a",
               "p99_ms": num(str(nearest_rank(lat, 99))) if lat else "n/a",
               "cost_rows": len(costs),
               "cost_per_request": str((sum(costs) / len(costs)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
               if costs else None}
    doc = {"skill": "ai-slo-definition", "version": "0.2.0", "system": args.system or "AI feature",
           "log": Path(args.log).name, "summary": summary, "not_measured": not_measured,
           "reference_window_days": REFERENCE_WINDOW_DAYS,
           "verdict": "breached" if any(r["status"] == "breached" for r in recs) else "pass",
           "slos": [rec_json(r) for r in recs]}
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "slos.csv").write_text(write_csv(recs), encoding="utf-8")
    (out / "slo-spec.md").write_text(write_md(doc, recs), encoding="utf-8")
    (out / "slo.json").write_text(json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
    print(f"slo: {len(recs)} SLIs · " + " ".join(f"{r['sli']}={r['status']}" for r in recs) + f" -> {out}")
    breached = [r["sli"] for r in recs if r["status"] == "breached"]
    if breached:
        print(f"GATE: SLO breached: {', '.join(breached)}", file=sys.stderr)
        return 1
    return 0


# ------------------------------------------------------------------ verify
def _fr(d):
    return None if d is None else Fraction(d["num"], d["den"])


def verify(path: str) -> int:
    """Recompute budget, burn, alert and status from the counts in slo.json; csv/md must agree."""
    p = Path(path)
    jp = p.parent / "slo.json"
    if not p.is_file() or not jp.is_file():
        print(f"verify: missing {p if not p.is_file() else jp}")
        return 1
    doc = json.loads(jp.read_text(encoding="utf-8"))
    errs, recs = [], []
    for s in doc["slos"]:
        r = {"sli": s["sli"], "kind": s["kind"], "objective": s["objective"], "threshold": s["threshold"],
             "window_days": s["window_days"], "bad": s["bad"], "total": s["total"], "alerts": []}
        if s["objective"]:
            r["consumed"] = Fraction(s["bad"], s["total"]) / (1 - Fraction(s["objective"]))
            if r["consumed"] != _fr(s["budget_consumed"]):
                errs.append(f"{s['sli']}: budget_consumed does not follow from the counts")
            for a in s["alerts"]:
                lb = burn(tuple(a["long"]) if a["long"] else None, s["objective"])
                sb = burn(tuple(a["short"]) if a["short"] else None, s["objective"])
                thr = _fr(a["threshold"])
                fires = lb is not None and sb is not None and lb >= thr and sb >= thr
                if fires != a["fires"]:
                    errs.append(f"{s['sli']}: alert '{a['name']}' fires={a['fires']} but counts give {fires}")
                r["alerts"].append({"fires": fires})
            r["burn_1h"] = _fr(s["burn_rate_1h"])
        else:
            r["consumed"] = r["burn_1h"] = None
        r["status"] = status_of(s["kind"], r["consumed"], r["alerts"])
        if r["status"] != s["status"]:
            errs.append(f"{s['sli']}: status {s['status']} but counts give {r['status']}")
        recs.append(r)
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".csv":
        got = list(csv.reader(io.StringIO(text)))
        if not got or got[0] != CSV_COLS:
            errs.append("slos.csv header differs")
        elif got[1:] != [csv_row(r) for r in recs]:
            errs.append("slos.csv rows differ from slo.json")
    else:
        for r in recs:
            if md_slo_row(r) not in text:
                errs.append(f"slo-spec.md lacks the row for {r['sli']}")
        if any(r["status"] == "breached" for r in recs) != ("**BREACHED" in text):
            errs.append("slo-spec.md verdict disagrees with the statuses")
    for e in errs:
        print(f"verify: {e}")
    print("verify: ok" if not errs else f"verify: {len(errs)} problem(s)")
    return 0 if not errs else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log")
    ap.add_argument("--targets")
    ap.add_argument("--system")
    ap.add_argument("--out-dir")
    ap.add_argument("--verify", metavar="FILE")
    a = ap.parse_args(argv)
    if a.verify:
        return verify(a.verify)
    try:
        return run(a)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

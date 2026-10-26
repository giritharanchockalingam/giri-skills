#!/usr/bin/env python3
"""LLM observability roll-up: trace spans (JSONL) + SLOs -> dashboard.json, alerts.md, trace schema.

Computes, per feature and overall, over the current window: request count, error rate,
p50/p95/p99 latency (nearest-rank percentile, references/metrics-method.md), tokens per request,
cost per request (only from spans that carry cost_usd — never estimated from prices), eval score
mean, user feedback counts, and drift against an optional baseline window (relative change in
tokens per request, p95 latency and eval score mean). Evaluates every SLO row and writes alerts.

Usage:
  python3 -I observe.py --traces traces.jsonl --slo slo.csv --out-dir OUT
        [--baseline-start 2026-09-01 --baseline-end 2026-09-07] [--schema assets/trace-schema.json]

Span fields (one JSON object per line; see assets/trace-schema.json): trace_id, ts (ISO 8601),
feature (or route), model, latency_ms, input_tokens, output_tokens, status (ok|error); optional
cost_usd, eval_score, user_feedback (up|down).
SLO CSV: metric,threshold,window[,feature][,comparator]. window = all | <n>m | <n>h | <n>d,
measured back from the newest current-window span. feature empty or * = overall.

Windows: with a baseline, baseline = spans with baseline-start <= ts <= baseline-end (dates are
whole days, UTC) and current = spans after baseline-end; spans before baseline-start are
excluded. Without a baseline, current = all spans and drift is not computed.

Exit codes: 0 no SLO breached · 1 at least one SLO breached (outputs still written) ·
2 missing/invalid required input (no valid spans, unreadable SLO file, bad metric/window).
Stdlib only; no network; writes only inside --out-dir.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_SCHEMA = Path(__file__).resolve().parent.parent / "assets" / "trace-schema.json"
MIN_METRICS = {"eval_score_mean"}  # SLO direction: these must stay >= threshold; all others <=
SLO_METRICS = {
    "error_rate", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms", "tokens_per_request",
    "cost_per_request_usd", "eval_score_mean", "negative_feedback_rate",
    "drift_tokens_per_request_pct", "drift_latency_p95_ms_pct", "drift_eval_score_mean_pct",
}
DRIFT_KEYS = ("tokens_per_request", "latency_p95_ms", "eval_score_mean")
WINDOW_RE = re.compile(r"^(\d+)([mhd])$")


class InputError(Exception):
    """Missing or invalid required input -> exit 2."""


def parse_ts(v) -> datetime:
    s = str(v).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def percentile(values: list[float], p: float):
    """Nearest-rank percentile: the value at rank ceil(p/100 × n) of the sorted sample (1-based)."""
    if not values:
        return None
    s = sorted(values)
    rank = max(1, math.ceil(p / 100.0 * len(s)))
    return s[rank - 1]


def clean(x):
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return x


def load_schema(path: Path) -> dict:
    if not path.is_file():
        raise InputError(f"trace schema not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_spans(path: Path, schema: dict) -> tuple[list[dict], list[dict]]:
    if not path.is_file():
        raise InputError(f"traces file not found: {path}")
    required = [k for k in schema.get("required", []) if k != "feature"]
    spans, rejected = [], []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError as e:
            rejected.append({"line": n, "reason": f"invalid JSON: {e.msg}"})
            continue
        if not isinstance(o, dict):
            rejected.append({"line": n, "reason": "not a JSON object"})
            continue
        feature = o.get("feature") or o.get("route")
        missing = [k for k in required if o.get(k) in (None, "")] + ([] if feature else ["feature|route"])
        if missing:
            rejected.append({"line": n, "reason": "missing " + ", ".join(missing)})
            continue
        try:
            span = {
                "trace_id": str(o["trace_id"]), "ts": parse_ts(o["ts"]), "feature": str(feature),
                "model": str(o["model"]), "latency_ms": float(o["latency_ms"]),
                "input_tokens": float(o["input_tokens"]), "output_tokens": float(o["output_tokens"]),
                "status": str(o["status"]).lower(),
                "cost_usd": float(o["cost_usd"]) if o.get("cost_usd") not in (None, "") else None,
                "eval_score": float(o["eval_score"]) if o.get("eval_score") not in (None, "") else None,
                "user_feedback": str(o["user_feedback"]).lower() if o.get("user_feedback") not in (None, "") else None,
            }
        except (TypeError, ValueError) as e:
            rejected.append({"line": n, "reason": f"bad value: {e}"})
            continue
        if span["status"] not in ("ok", "error"):
            rejected.append({"line": n, "reason": f"status must be ok|error, got {span['status']!r}"})
            continue
        spans.append(span)
    return spans, rejected


def metrics(spans: list[dict]) -> dict:
    n = len(spans)
    if n == 0:
        return {"requests": 0}
    lat = [s["latency_ms"] for s in spans]
    costs = [s["cost_usd"] for s in spans if s["cost_usd"] is not None]
    evals = [s["eval_score"] for s in spans if s["eval_score"] is not None]
    fb = [s["user_feedback"] for s in spans if s["user_feedback"]]
    up, down = sum(1 for f in fb if f == "up"), sum(1 for f in fb if f == "down")
    errors = sum(1 for s in spans if s["status"] == "error")
    return {
        "requests": n,
        "errors": errors,
        "error_rate": round(errors / n, 4),
        "latency_p50_ms": clean(percentile(lat, 50)),
        "latency_p95_ms": clean(percentile(lat, 95)),
        "latency_p99_ms": clean(percentile(lat, 99)),
        "input_tokens_per_request": round(sum(s["input_tokens"] for s in spans) / n, 2),
        "output_tokens_per_request": round(sum(s["output_tokens"] for s in spans) / n, 2),
        "tokens_per_request": round(sum(s["input_tokens"] + s["output_tokens"] for s in spans) / n, 2),
        "cost_per_request_usd": round(sum(costs) / len(costs), 6) if costs else None,
        "cost_total_usd": round(sum(costs), 6) if costs else None,
        "cost_coverage": round(len(costs) / n, 4),
        "eval_score_mean": round(sum(evals) / len(evals), 4) if evals else None,
        "eval_coverage": round(len(evals) / n, 4),
        "feedback_up": up,
        "feedback_down": down,
        "negative_feedback_rate": round(down / (up + down), 4) if (up + down) else None,
    }


def drift(cur: dict, base: dict) -> dict:
    out = {}
    for k in DRIFT_KEYS:
        c, b = cur.get(k), base.get(k)
        out[f"drift_{k}_pct"] = round((c - b) / b * 100.0, 2) if c is not None and b not in (None, 0) else None
    return out


def window_delta(w: str):
    w = (w or "all").strip().lower()
    if w in ("all", ""):
        return None
    m = WINDOW_RE.match(w)
    if not m:
        raise InputError(f"SLO window must be all or <n>m|h|d, got {w!r}")
    n, unit = int(m.group(1)), m.group(2)
    return timedelta(minutes=n) if unit == "m" else timedelta(hours=n) if unit == "h" else timedelta(days=n)


def load_slos(path: Path) -> list[dict]:
    if not path.is_file():
        raise InputError(f"SLO file not found: {path}")
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#")]
    rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO("\n".join(lines)))]
    if not rows:
        raise InputError("SLO file has no rows")
    slos = []
    for i, r in enumerate(rows, start=2):
        m = r.get("metric", "")
        if m not in SLO_METRICS:
            raise InputError(f"SLO line {i}: unknown metric {m!r}; supported: {sorted(SLO_METRICS)}")
        try:
            thr = float(r.get("threshold", ""))
        except ValueError:
            raise InputError(f"SLO line {i}: threshold must be numeric") from None
        comp = r.get("comparator") or (">=" if m in MIN_METRICS else "<=")
        if comp not in ("<=", ">="):
            raise InputError(f"SLO line {i}: comparator must be <= or >=")
        window_delta(r.get("window", "all"))
        feat = r.get("feature", "") or "*"
        slos.append({"metric": m, "threshold": clean(thr), "window": r.get("window") or "all",
                     "feature": feat, "comparator": comp})
    return slos


def evaluate_slos(slos, current, baseline) -> list[dict]:
    newest = max(s["ts"] for s in current) if current else None
    results = []
    for slo in slos:
        delta = window_delta(slo["window"])
        pool = current if delta is None else [s for s in current if s["ts"] > newest - delta]
        if slo["feature"] != "*":
            pool = [s for s in pool if s["feature"] == slo["feature"]]
        m = metrics(pool)
        if slo["metric"].startswith("drift_"):
            bpool = baseline if slo["feature"] == "*" else [s for s in baseline if s["feature"] == slo["feature"]]
            d = drift(m, metrics(bpool)) if bpool and pool else {}
            observed = d.get(slo["metric"])
            observed = abs(observed) if observed is not None else None
        else:
            observed = m.get(slo["metric"]) if pool else None
        if observed is None:
            status = "NO DATA"
        else:
            ok = observed <= slo["threshold"] if slo["comparator"] == "<=" else observed >= slo["threshold"]
            status = "OK" if ok else "BREACH"
        results.append({**slo, "observed": observed, "requests_in_window": len(pool), "status": status})
    return results


def split_windows(spans, b_start, b_end):
    if not (b_start or b_end):
        return spans, [], 0
    if not (b_start and b_end):
        raise InputError("give both --baseline-start and --baseline-end, or neither")

    def bound(v, end):
        dt = parse_ts(v)
        if len(v.strip()) == 10 and end:  # whole day
            dt = dt + timedelta(days=1) - timedelta(microseconds=1)
        return dt

    lo, hi = bound(b_start, False), bound(b_end, True)
    if hi < lo:
        raise InputError("baseline end is before baseline start")
    base = [s for s in spans if lo <= s["ts"] <= hi]
    cur = [s for s in spans if s["ts"] > hi]
    return cur, base, len(spans) - len(base) - len(cur)


def build(spans, rejected, slos, b_start=None, b_end=None) -> dict:
    current, baseline, excluded = split_windows(spans, b_start, b_end)
    if not current:
        raise InputError("no spans in the current window")
    features = sorted({s["feature"] for s in current} | {s["feature"] for s in baseline})
    dash = {
        "window": {
            "current_start": min(s["ts"] for s in current).isoformat(),
            "current_end": max(s["ts"] for s in current).isoformat(),
            "baseline_start": b_start, "baseline_end": b_end,
            "spans_current": len(current), "spans_baseline": len(baseline), "spans_excluded": excluded,
            "spans_rejected": len(rejected),
        },
        "percentile_method": "nearest-rank: value at rank ceil(p/100*n) of sorted latencies (all spans, ok and error)",
        "overall": metrics(current),
        "by_feature": {},
        "drift": {},
        "slo_results": evaluate_slos(slos, current, baseline),
        "rejected": rejected[:50],
    }
    for f in features:
        cur_f = [s for s in current if s["feature"] == f]
        dash["by_feature"][f] = {**metrics(cur_f), "models": sorted({s["model"] for s in cur_f})}
    if baseline:
        dash["baseline"] = metrics(baseline)
        dash["drift"]["overall"] = drift(dash["overall"], dash["baseline"])
        for f in features:
            bf = [s for s in baseline if s["feature"] == f]
            cf = [s for s in current if s["feature"] == f]
            if bf and cf:
                dash["drift"][f] = drift(metrics(cf), metrics(bf))
    dash["breaches"] = sum(1 for r in dash["slo_results"] if r["status"] == "BREACH")
    return dash


def v(x) -> str:
    return "—" if x is None else str(x)


def render(d: dict) -> str:
    w, o = d["window"], d["overall"]
    breaches = [r for r in d["slo_results"] if r["status"] == "BREACH"]
    nodata = [r for r in d["slo_results"] if r["status"] == "NO DATA"]
    L = ["# LLM observability alerts", "",
         f"Current window: {w['current_start']} → {w['current_end']} ({w['spans_current']} spans). "
         f"Baseline: {w['baseline_start'] or 'none'} → {w['baseline_end'] or 'none'} ({w['spans_baseline']} spans). "
         f"Rejected spans: {w['spans_rejected']}.", "", "## Status", ""]
    if breaches:
        L.append(f"**BREACH** — {len(breaches)} of {len(d['slo_results'])} SLOs breached.")
    else:
        L.append(f"**OK** — 0 of {len(d['slo_results'])} SLOs breached.")
    if nodata:
        L.append(f"{len(nodata)} SLO(s) have NO DATA (metric not present in spans) — not counted as met; "
                 "[TO BE BASELINED — owner: Observability lead] to instrument.")
    L += ["", "| Metric (overall) | Value |", "|---|---|"]
    for k in ("requests", "error_rate", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms",
              "tokens_per_request", "cost_per_request_usd", "cost_coverage", "eval_score_mean", "negative_feedback_rate"):
        L.append(f"| {k} | {v(o.get(k))} |")
    L += ["", "## SLO breaches", "", "| Metric | Feature | Window | Comparator | Threshold | Observed | Requests | Status |",
          "|---|---|---|---|---|---|---|---|"]
    for r in d["slo_results"]:
        L.append(f"| {r['metric']} | {r['feature']} | {r['window']} | {r['comparator']} | {r['threshold']} | "
                 f"{v(r['observed'])} | {r['requests_in_window']} | {r['status']} |")
    L += ["", "## Drift", ""]
    if not d["drift"]:
        L.append("No baseline window supplied; drift not computed.")
    else:
        L += ["Relative change, current vs baseline (%).", "",
              "| Scope | Tokens/request | p95 latency | Eval score mean |", "|---|---|---|---|"]
        for scope, dr in d["drift"].items():
            L.append(f"| {scope} | {v(dr['drift_tokens_per_request_pct'])} | {v(dr['drift_latency_p95_ms_pct'])} | "
                     f"{v(dr['drift_eval_score_mean_pct'])} |")
    L += ["", "## By feature", "",
          "| Feature | Requests | Error rate | p50 ms | p95 ms | p99 ms | Tokens/req | Cost/req USD | Eval mean |",
          "|---|---|---|---|---|---|---|---|---|"]
    for f, m in d["by_feature"].items():
        if not m.get("requests"):
            L.append(f"| {f} | 0 | — | — | — | — | — | — | — |")
            continue
        L.append(f"| {f} | {m['requests']} | {m['error_rate']} | {m['latency_p50_ms']} | {m['latency_p95_ms']} | "
                 f"{m['latency_p99_ms']} | {m['tokens_per_request']} | {v(m['cost_per_request_usd'])} | {v(m['eval_score_mean'])} |")
    L += ["", "Cost per request is computed only from spans that carry `cost_usd`; it is never estimated from prices.",
          f"Percentiles: {d['percentile_method']}."]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--traces", type=Path, required=True, help="JSONL, one span per line")
    ap.add_argument("--slo", type=Path, required=True, help="SLO CSV metric,threshold,window[,feature][,comparator]")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--baseline-start", help="baseline window start (date or ISO timestamp)")
    ap.add_argument("--baseline-end", help="baseline window end (date = whole day, or ISO timestamp)")
    ap.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="recommended trace schema (JSON Schema)")
    args = ap.parse_args(argv)
    try:
        schema = load_schema(args.schema)
        spans, rejected = load_spans(args.traces, schema)
        if not spans:
            raise InputError(f"no valid spans in {args.traces} ({len(rejected)} rejected)")
        dash = build(spans, rejected, load_slos(args.slo), args.baseline_start, args.baseline_end)
    except (InputError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "dashboard.json").write_text(json.dumps(dash, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out_dir / "alerts.md").write_text(render(dash), encoding="utf-8")
    (args.out_dir / "trace-schema.json").write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if dash["breaches"]:
        print(f"{dash['breaches']} SLO breach(es)", file=sys.stderr)
        return 1
    print(f"observability roll-up written: {dash['window']['spans_current']} spans, 0 SLO breaches")
    return 0


if __name__ == "__main__":
    sys.exit(main())

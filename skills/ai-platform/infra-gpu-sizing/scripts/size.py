#!/usr/bin/env python3
"""GPU inference sizing calculator: workload inputs -> GPU count and monthly cost.

No prices or throughput figures are built in. Every number comes from --inputs CSV
(key,value,...) or CLI flags (flags override CSV). Missing required inputs are reported.

Usage:
  python3 -I size.py --inputs gpu-sizing-inputs.csv [--json] [--set key=value ...]
  python3 -I size.py --set daily_active_users=1000 --set requests_per_user_per_day=20 ...

Required keys: daily_active_users, requests_per_user_per_day, tokens_in_per_request,
  tokens_out_per_request, active_hours_per_day, peak_factor, decode_tokens_per_s_per_gpu,
  prefill_tokens_per_s_per_gpu
Optional (defaults in DEFAULTS): calls_per_request=1, utilization_target=0.6, spare_gpus=1,
  gpus_per_replica=1, rental_hours_per_month=730, amortization_months=36, ops_fte=0,
  software_per_month=0, batch_size_at_measurement, slo_tokens_per_s_per_stream
Cost keys (each option computed only when its keys are present):
  rental_usd_per_gpu_hour
  selfhost_capex_per_gpu, selfhost_hosting_per_gpu_month, fte_cost_per_year
  api_usd_per_1m_input_tokens, api_usd_per_1m_output_tokens
Existing fleet (brownfield, optional): current_gpus (GPUs serving this workload today, incl. spares),
  current_cost_usd_per_month (what that fleet costs today). With current_gpus the output adds
  "current_fleet": the delta to the sized fleet and a verdict (over-provisioned | right-sized |
  under-provisioned); with a rental price the delta is also priced.
Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

REQUIRED = [
    "daily_active_users", "requests_per_user_per_day", "tokens_in_per_request", "tokens_out_per_request",
    "active_hours_per_day", "peak_factor", "decode_tokens_per_s_per_gpu", "prefill_tokens_per_s_per_gpu",
]
DEFAULTS = {
    "calls_per_request": 1.0, "utilization_target": 0.6, "spare_gpus": 1.0, "gpus_per_replica": 1.0,
    "rental_hours_per_month": 730.0, "amortization_months": 36.0, "ops_fte": 0.0, "software_per_month": 0.0,
}


def load_inputs(path: Path | None, overrides: list[str]) -> dict[str, float]:
    vals: dict[str, float] = {}
    if path:
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                k, v = (row.get("key") or "").strip(), (row.get("value") or "").strip()
                if k and v:
                    try:
                        vals[k] = float(v)
                    except ValueError:
                        sys.exit(f"non-numeric value for {k}: {v!r}")
    for o in overrides:
        if "=" not in o:
            sys.exit(f"--set expects key=value, got {o!r}")
        k, v = o.split("=", 1)
        try:
            vals[k.strip()] = float(v)
        except ValueError:
            sys.exit(f"non-numeric value for {k}: {v!r}")
    for k, d in DEFAULTS.items():
        vals.setdefault(k, d)
    missing = [k for k in REQUIRED if k not in vals]
    if missing:
        sys.exit(f"missing required inputs: {', '.join(missing)}")
    return vals


def size(v: dict[str, float]) -> dict:
    calls = v["calls_per_request"]
    r_day = v["daily_active_users"] * v["requests_per_user_per_day"] * calls
    r_avg = r_day / (v["active_hours_per_day"] * 3600)
    r_peak = r_avg * v["peak_factor"]
    p_peak = r_peak * v["tokens_in_per_request"]
    d_peak = r_peak * v["tokens_out_per_request"]
    u = v["utilization_target"]
    g_d = math.ceil(d_peak / (v["decode_tokens_per_s_per_gpu"] * u))
    g_p = math.ceil(p_peak / (v["prefill_tokens_per_s_per_gpu"] * u))
    g = max(g_d, g_p, 1)
    per_replica = max(int(v["gpus_per_replica"]), 1)
    g = math.ceil(g / per_replica) * per_replica
    g_tot = g + int(v["spare_gpus"])

    out = {
        "workload": {
            "requests_per_day": round(r_day), "avg_req_per_s": round(r_avg, 4), "peak_req_per_s": round(r_peak, 4),
            "prefill_tokens_per_s_peak": round(p_peak, 1), "decode_tokens_per_s_peak": round(d_peak, 1),
            "tokens_in_per_month": round(r_day * 30 * v["tokens_in_per_request"]),
            "tokens_out_per_month": round(r_day * 30 * v["tokens_out_per_request"]),
        },
        "capacity": {"gpus_decode": g_d, "gpus_prefill": g_p, "gpus_required": g, "gpus_total_with_spare": g_tot,
                     "utilization_target": u},
        "latency_check": {},
        "cost_monthly_usd": {},
        "notes": [],
    }

    # Latency check: per-stream decode speed at measured batch vs SLO; concurrency via Little's law
    slo = v.get("slo_tokens_per_s_per_stream")
    batch = v.get("batch_size_at_measurement")
    if slo:
        n_conc = r_peak * (v["tokens_out_per_request"] / slo)
        out["latency_check"]["concurrent_streams_peak"] = round(n_conc, 1)
        if batch:
            per_stream = v["decode_tokens_per_s_per_gpu"] / batch
            out["latency_check"]["per_stream_tokens_per_s_at_measured_batch"] = round(per_stream, 1)
            out["latency_check"]["meets_slo"] = per_stream >= slo
            if per_stream < slo:
                out["notes"].append("Per-stream decode speed below SLO at the measured batch; re-measure at a smaller batch.")
            streams_capacity = g * batch
            if n_conc > streams_capacity:
                out["notes"].append(f"Peak concurrency {n_conc:.0f} exceeds batch capacity {streams_capacity:.0f}; add GPUs or reduce batch target.")
                out["capacity"]["gpus_required_for_concurrency"] = math.ceil(n_conc / batch)

    # Costs — only where inputs exist
    ops = v["ops_fte"] * v.get("fte_cost_per_year", 0.0) / 12 if v["ops_fte"] else 0.0
    sw = v["software_per_month"]
    if "rental_usd_per_gpu_hour" in v:
        rental = v["rental_usd_per_gpu_hour"] * g_tot * v["rental_hours_per_month"]
        out["cost_monthly_usd"]["rental"] = {"gpu": round(rental, 2), "ops": round(ops, 2), "software": round(sw, 2),
                                             "total": round(rental + ops + sw, 2)}
    if "selfhost_capex_per_gpu" in v and "selfhost_hosting_per_gpu_month" in v:
        capex_m = v["selfhost_capex_per_gpu"] / v["amortization_months"] * g_tot
        hosting = v["selfhost_hosting_per_gpu_month"] * g_tot
        out["cost_monthly_usd"]["selfhost"] = {"capex_amortized": round(capex_m, 2), "hosting": round(hosting, 2),
                                               "ops": round(ops, 2), "software": round(sw, 2),
                                               "total": round(capex_m + hosting + ops + sw, 2)}
        if "rental_usd_per_gpu_hour" in v and v["rental_usd_per_gpu_hour"] > 0:
            per_gpu_month = v["selfhost_capex_per_gpu"] / v["amortization_months"] + v["selfhost_hosting_per_gpu_month"]
            out["cost_monthly_usd"]["breakeven_rental_hours_per_month_per_gpu"] = round(per_gpu_month / v["rental_usd_per_gpu_hour"], 1)
    if "api_usd_per_1m_input_tokens" in v and "api_usd_per_1m_output_tokens" in v:
        api = (out["workload"]["tokens_in_per_month"] / 1e6 * v["api_usd_per_1m_input_tokens"]
               + out["workload"]["tokens_out_per_month"] / 1e6 * v["api_usd_per_1m_output_tokens"])
        out["cost_monthly_usd"]["api"] = {"tokens": round(api, 2), "total": round(api, 2)}
    if not out["cost_monthly_usd"]:
        out["notes"].append("No price inputs supplied; capacity only.")
    if "current_gpus" in v:
        out["current_fleet"] = compare_fleet(v, out)
    out["notes"].append("Throughput and price inputs are user-supplied; results are as good as those measurements.")
    return out


def compare_fleet(v: dict[str, float], res: dict) -> dict:
    """Compare the fleet running today against the sized fleet (brownfield right-sizing)."""
    cur = v["current_gpus"]
    if cur < 0 or cur != int(cur):
        sys.exit(f"current_gpus must be a whole number >= 0, got {cur}")
    cur = int(cur)
    need = res["capacity"]["gpus_total_with_spare"]
    need = max(need, res["capacity"].get("gpus_required_for_concurrency", 0) + int(v["spare_gpus"]))
    delta = cur - need
    verdict = "over-provisioned" if delta > 0 else "under-provisioned" if delta < 0 else "right-sized"
    fleet = {"current_gpus": cur, "sized_gpus_with_spare": need, "delta_gpus": delta, "verdict": verdict,
             "sized_share_of_current": round(need / cur, 3) if cur else None}
    if "rental_usd_per_gpu_hour" in v:
        fleet["delta_usd_per_month_at_rental_rate"] = round(delta * v["rental_usd_per_gpu_hour"]
                                                            * v["rental_hours_per_month"], 2)
    if "current_cost_usd_per_month" in v:
        fleet["current_cost_usd_per_month"] = round(v["current_cost_usd_per_month"], 2)
        options = {k: o["total"] for k, o in res["cost_monthly_usd"].items() if isinstance(o, dict)}
        if options:
            best = min(options, key=options.get)
            fleet["cheapest_option"] = best
            fleet["saving_vs_current_usd_per_month"] = round(v["current_cost_usd_per_month"] - options[best], 2)
    if verdict == "over-provisioned":
        res["notes"].append(f"Existing fleet has {delta} GPU(s) more than the sized need; release them or plan growth.")
    elif verdict == "under-provisioned":
        res["notes"].append(f"Existing fleet is {-delta} GPU(s) short of the sized need at the target utilization.")
    return fleet


def print_table(res: dict) -> None:
    w, c = res["workload"], res["capacity"]
    print("WORKLOAD")
    for k, val in w.items():
        print(f"  {k:<32}{val:>16,}" if isinstance(val, int) else f"  {k:<32}{val:>16}")
    print("CAPACITY")
    for k, val in c.items():
        print(f"  {k:<32}{val:>16}")
    if res["latency_check"]:
        print("LATENCY CHECK")
        for k, val in res["latency_check"].items():
            print(f"  {k:<40}{val!s:>10}")
    if res["cost_monthly_usd"]:
        print("MONTHLY COST (USD)")
        for opt, lines in res["cost_monthly_usd"].items():
            if isinstance(lines, dict):
                parts = ", ".join(f"{k}={val:,.0f}" for k, val in lines.items())
                print(f"  {opt:<12}{parts}")
            else:
                print(f"  {opt:<44}{lines:>10}")
    if res.get("current_fleet"):
        print("CURRENT FLEET")
        for k, val in res["current_fleet"].items():
            print(f"  {k:<40}{val!s:>16}")
    for n in res["notes"]:
        print(f"NOTE: {n}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inputs", type=Path, help="CSV with key,value columns")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override or supply an input")
    ap.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = ap.parse_args(argv)
    if not args.inputs and not args.set:
        ap.error("provide --inputs and/or --set")
    res = size(load_inputs(args.inputs, args.set))
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print_table(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())

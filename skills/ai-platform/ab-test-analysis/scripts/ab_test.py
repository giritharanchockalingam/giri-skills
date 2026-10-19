#!/usr/bin/env python3
"""A/B test analysis for AI variants (prompt, model, retrieval change): ship / don't ship / inconclusive.

Reads experiment results (aggregated per variant, or one row per unit) and an optional config,
then computes, with the standard library only:
  - sample-ratio-mismatch (SRM) check: Pearson chi-square goodness of fit of assigned units
    against the expected split; flagged when p < srm_alpha (default 0.001, a convention);
  - binary metrics: two-proportion z-test (pooled SE), Wald CI on the difference (unpooled SE),
    relative lift;
  - continuous metrics: Welch's t-test (Welch-Satterthwaite df; Student-t CDF via the
    regularised incomplete beta function), CI with the t quantile;
  - Holm step-down adjustment across treatments when there is more than one treatment;
  - achieved power for the declared MDE, the sample size per arm that MDE needs, and the
    smallest effect the test could detect at the observed n.
Decision rule (per treatment): significant change in the bad direction on the primary metric
-> don't ship; significant improvement with a guardrail significantly worse -> don't ship;
significant improvement with no guardrail worse -> ship; anything else -> inconclusive.

Inputs:
  --results  CSV, either aggregated   variant,users,conversions[,metric_sum,metric_sumsq][,metric]
             or unit-level            variant,unit_id,converted[,value][,<guardrail columns>]
             Lines starting with '#' are comments.
  --config   optional kv CSV key,value[,source,notes]; keys: experiment_name, control, alpha,
             power, expected_split, mde, metric_type, primary_metric, direction, guardrails,
             srm_alpha. Blank values count as not supplied (defaults are used and labelled).

Usage:
  python3 -I ab_test.py --results r.csv [--config c.csv] --out-dir <dir>
  python3 -I ab_test.py --verify <dir>/ab-report.md --results r.csv   # re-derive and compare

Writes ab-results.csv, ab-report.md, ab.json. Exit codes: 0 analysed · 1 SRM detected (results
untrustworthy; outputs still written) or --verify mismatch · 2 input missing or unusable.
Deterministic: no clock, sorted keys, fixed rounding.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
from pathlib import Path
from statistics import NormalDist

OWNER = "Experiment owner"
TBB = f"[TO BE BASELINED — owner: {OWNER}]"
ND = NormalDist()
KNOWN_KEYS = ("experiment_name", "control", "alpha", "power", "expected_split", "mde", "metric_type",
              "primary_metric", "direction", "guardrails", "srm_alpha")
DIRECTIONS = ("higher_better", "lower_better")
OUTPUTS = ("ab-results.csv", "ab-report.md", "ab.json")


class InputError(Exception):
    """A required input is missing or unusable (exit 2)."""


# ------------------------------------------------------------------ special functions

def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (modified Lentz)."""
    tiny, eps = 1e-300, 3e-16
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 10000):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


def betainc_reg(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbt) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbt) * _betacf(b, a, 1.0 - x) / b


def t_cdf(t: float, df: float) -> float:
    """Student-t CDF: 1 - 0.5 * I_{df/(df+t^2)}(df/2, 1/2) for t >= 0."""
    x = df / (df + t * t)
    tail = 0.5 * betainc_reg(df / 2.0, 0.5, x)
    return 1.0 - tail if t >= 0 else tail


def t_ppf(p: float, df: float) -> float:
    """Student-t quantile by bisection on t_cdf (monotone)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    lo, hi = -1.0, 1.0
    while t_cdf(lo, df) > p:
        lo *= 2.0
    while t_cdf(hi, df) < p:
        hi *= 2.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def gammainc_upper_reg(s: float, x: float) -> float:
    """Regularised upper incomplete gamma Q(s, x) (series / continued fraction)."""
    if x <= 0.0:
        return 1.0
    gln = math.lgamma(s)
    if x < s + 1.0:
        ap, total, delta = s, 1.0 / s, 1.0 / s
        for _ in range(10000):
            ap += 1.0
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * 3e-16:
                break
        return max(0.0, 1.0 - total * math.exp(-x + s * math.log(x) - gln))
    tiny = 1e-300
    b = x + 1.0 - s
    c, d = 1.0 / tiny, 1.0 / b
    h = d
    for i in range(1, 10000):
        an = -i * (i - s)
        b += 2.0
        d = an * d + b
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = b + an / c
        c = c if abs(c) > tiny else tiny
        de = d * c
        h *= de
        if abs(de - 1.0) < 3e-16:
            break
    return math.exp(-x + s * math.log(x) - gln) * h


def chi2_sf(x: float, k: int) -> float:
    return gammainc_upper_reg(k / 2.0, x / 2.0)


def norm_two_sided_p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2.0))


def holm(pvals: list[float]) -> list[float]:
    """Holm (1979) step-down adjusted p-values, returned in input order."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: (pvals[i], i))
    adj, running = [0.0] * m, 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvals[i]))
        adj[i] = running
    return adj


# ------------------------------------------------------------------ input parsing

def _read_rows(path: Path, label: str) -> tuple[list[str], list[dict]]:
    if not path.is_file():
        raise InputError(f"{label} file not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        raise InputError(f"{label} CSV is empty")
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    header = [h.strip() for h in (reader.fieldnames or [])]
    rows = []
    for i, row in enumerate(reader, start=2):
        r = {(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None}
        r["_line"] = i
        rows.append(r)
    return header, rows


def read_config(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    header, rows = _read_rows(path, "config")
    if "key" not in header or "value" not in header:
        raise InputError(f"config CSV needs columns key,value; header is {header}")
    cfg = {}
    for r in rows:
        k = r.get("key", "")
        if not k:
            continue
        if k not in KNOWN_KEYS:
            raise InputError(f"config line {r['_line']}: unknown key {k!r}; known keys: {', '.join(KNOWN_KEYS)}")
        if r.get("value", "") != "":
            cfg[k] = r["value"]
    return cfg


def _num(raw: str, what: str, *, integer: bool = False) -> float:
    try:
        v = float(raw.replace(",", ""))
    except ValueError as e:
        raise InputError(f"{what}: {raw!r} is not numeric") from e
    if not math.isfinite(v):
        raise InputError(f"{what}: {raw!r} is not finite")
    if integer and v != int(v):
        raise InputError(f"{what}: {raw!r} must be a whole number")
    return v


def read_results(path: Path, guard_names: list[str]) -> dict:
    """Return {"format", "variants" (data order), "assigned" {variant: n}, "metrics" {name: {...}}}."""
    header, rows = _read_rows(path, "results")
    if not rows:
        raise InputError("results CSV has no data rows")
    if "variant" not in header:
        raise InputError(f"results CSV needs a 'variant' column; header is {header}")
    if "users" in header:
        return _read_aggregated(header, rows)
    if "unit_id" in header:
        return _read_units(header, rows, guard_names)
    raise InputError("results CSV must be aggregated (variant,users,conversions[,metric_sum,metric_sumsq]) "
                     f"or unit-level (variant,unit_id,converted[,value]); header is {header}")


def _read_aggregated(header: list[str], rows: list[dict]) -> dict:
    if "conversions" not in header and "metric_sum" not in header:
        raise InputError("aggregated results need 'conversions' (binary) or 'metric_sum','metric_sumsq' (continuous)")
    if "metric_sum" in header and "metric_sumsq" not in header:
        raise InputError("aggregated results with 'metric_sum' also need 'metric_sumsq'")
    variants, metrics = [], {}
    for r in rows:
        v = r.get("variant", "")
        if not v:
            raise InputError(f"results line {r['_line']}: blank variant")
        m = r.get("metric", "") or "primary"
        n = _num(r.get("users", ""), f"results line {r['_line']} users", integer=True)
        if n <= 0:
            raise InputError(f"results line {r['_line']}: users must be > 0")
        rec = {"n": int(n)}
        if r.get("conversions", "") != "":
            c = _num(r["conversions"], f"results line {r['_line']} conversions", integer=True)
            if c < 0 or c > n:
                raise InputError(f"results line {r['_line']}: conversions must be between 0 and users")
            rec["conversions"] = int(c)
        if r.get("metric_sum", "") != "":
            if r.get("metric_sumsq", "") == "":
                raise InputError(f"results line {r['_line']}: metric_sum given without metric_sumsq")
            rec["sum"] = _num(r["metric_sum"], f"results line {r['_line']} metric_sum")
            rec["sumsq"] = _num(r["metric_sumsq"], f"results line {r['_line']} metric_sumsq")
        if "conversions" not in rec and "sum" not in rec:
            raise InputError(f"results line {r['_line']}: no conversions and no metric_sum")
        metric = metrics.setdefault(m, {"order": len(metrics), "rows": {}})
        if v in metric["rows"]:
            raise InputError(f"results line {r['_line']}: duplicate row for variant {v!r} metric {m!r}")
        metric["rows"][v] = rec
        if v not in variants:
            variants.append(v)
    return {"format": "aggregated", "variants": variants, "metrics": metrics}


def _read_units(header: list[str], rows: list[dict], guard_names: list[str]) -> dict:
    if "converted" not in header and "value" not in header:
        raise InputError("unit-level results need 'converted' (0/1) and/or 'value'")
    variants, seen = [], {}
    cols = [c for c in ("converted", "value") if c in header] + [g for g in guard_names if g in header
                                                                    and g not in ("converted", "value")]
    data: dict[str, dict[str, list[float]]] = {c: {} for c in cols}
    for r in rows:
        v, u = r.get("variant", ""), r.get("unit_id", "")
        if not v or not u:
            raise InputError(f"results line {r['_line']}: blank variant or unit_id")
        if u in seen:
            raise InputError(f"results line {r['_line']}: unit_id {u!r} appears more than once "
                             f"(first in variant {seen[u]!r}); each unit must be assigned once")
        seen[u] = v
        if v not in variants:
            variants.append(v)
        for c in cols:
            raw = r.get(c, "")
            if raw == "":
                continue
            x = _num(raw, f"results line {r['_line']} {c}")
            if c == "converted" and x not in (0.0, 1.0):
                raise InputError(f"results line {r['_line']}: converted must be 0 or 1, got {raw!r}")
            data[c].setdefault(v, []).append(x)
    assigned = {v: sum(1 for u in seen.values() if u == v) for v in variants}
    metrics = {}
    for i, c in enumerate(cols):
        rows_ = {}
        for v, xs in data[c].items():
            rec = {"n": len(xs), "sum": sum(xs), "sumsq": sum(x * x for x in xs)}
            if all(x in (0.0, 1.0) for x in xs):
                rec["conversions"] = int(sum(xs))
            rows_[v] = rec
        metrics[c] = {"order": i, "rows": rows_}
    return {"format": "unit-level", "variants": variants, "metrics": metrics, "assigned": assigned}


# ------------------------------------------------------------------ settings

def _prob(raw: str, key: str) -> float:
    v = _num(raw, f"config {key}")
    if not 0.0 < v < 1.0:
        raise InputError(f"config {key} must be between 0 and 1 (exclusive), got {raw!r}")
    return v


def parse_guardrails(raw: str) -> list[dict]:
    out = []
    for part in [p.strip() for p in raw.replace(",", ";").split(";") if p.strip()]:
        name, _, d = part.partition(":")
        name, d = name.strip(), d.strip().lower()
        if d and d not in DIRECTIONS:
            raise InputError(f"guardrail {name!r}: direction must be one of {DIRECTIONS}, got {d!r}")
        out.append({"name": name, "direction": d or None})
    return out


def settings(cfg: dict[str, str], res: dict) -> dict:
    """Effective settings with provenance ('config' or 'default' / 'inferred' / 'tbd')."""
    variants = res["variants"]
    s: dict = {"prov": {}}

    def put(key, value, prov):
        s[key] = value
        s["prov"][key] = prov

    put("experiment_name", cfg.get("experiment_name", "unnamed experiment"),
        "config" if "experiment_name" in cfg else "default")
    if "control" in cfg:
        if cfg["control"] not in variants:
            raise InputError(f"config control {cfg['control']!r} is not a variant in the results ({variants})")
        put("control", cfg["control"], "config")
    else:
        put("control", "control" if "control" in variants else variants[0], "default")
    if len(variants) < 2:
        raise InputError(f"results need at least two variants; found {variants}")
    put("alpha", _prob(cfg["alpha"], "alpha") if "alpha" in cfg else 0.05, "config" if "alpha" in cfg else "default")
    put("power", _prob(cfg["power"], "power") if "power" in cfg else 0.8, "config" if "power" in cfg else "default")
    put("srm_alpha", _prob(cfg["srm_alpha"], "srm_alpha") if "srm_alpha" in cfg else 0.001,
        "config" if "srm_alpha" in cfg else "default")
    d = cfg.get("direction", "").lower()
    if d and d not in DIRECTIONS:
        raise InputError(f"config direction must be one of {DIRECTIONS}, got {cfg['direction']!r}")
    put("direction", d or "higher_better", "config" if d else "default")

    metric_names = sorted(res["metrics"], key=lambda k: res["metrics"][k]["order"])
    if res["format"] == "unit-level":
        mt = cfg.get("metric_type", "").lower()
        if mt and mt not in ("binary", "continuous"):
            raise InputError(f"config metric_type must be binary or continuous, got {cfg['metric_type']!r}")
        if not mt:
            mt = "binary" if "converted" in res["metrics"] else "continuous"
            put("metric_type", mt, "inferred")
        else:
            put("metric_type", mt, "config")
        col = "converted" if mt == "binary" else "value"
        if col not in res["metrics"]:
            raise InputError(f"metric_type {mt} needs a '{col}' column in unit-level results")
        put("primary_metric", col, "default")
    else:
        if "primary_metric" in cfg:
            if cfg["primary_metric"] not in res["metrics"]:
                raise InputError(f"config primary_metric {cfg['primary_metric']!r} not in results metrics {metric_names}")
            put("primary_metric", cfg["primary_metric"], "config")
        else:
            put("primary_metric", metric_names[0], "default")
        mt = cfg.get("metric_type", "").lower()
        if mt and mt not in ("binary", "continuous"):
            raise InputError(f"config metric_type must be binary or continuous, got {cfg['metric_type']!r}")
        put("metric_type", mt or infer_type(res["metrics"][s["primary_metric"]]), "config" if mt else "inferred")

    # expected split
    if "expected_split" in cfg:
        put("expected_split", parse_split(cfg["expected_split"], variants), "config")
    else:
        put("expected_split", {v: 1.0 / len(variants) for v in variants}, "default")

    # MDE: absolute, or relative to the control with a % suffix
    if "mde" in cfg:
        raw = cfg["mde"].strip()
        rel = raw.endswith("%")
        v = _num(raw.rstrip("%"), "config mde")
        if v <= 0:
            raise InputError("config mde must be > 0")
        put("mde", {"value": v / 100.0 if rel else v, "relative": rel, "raw": raw}, "config")
    else:
        put("mde", None, "tbd")

    guards = parse_guardrails(cfg.get("guardrails", ""))
    put("guardrails", guards, "config" if guards else "none")
    return s


def infer_type(metric: dict) -> str:
    rows = metric["rows"].values()
    if all("sum" in r for r in rows) and not all("conversions" in r for r in rows):
        return "continuous"
    if all("conversions" in r for r in rows):
        return "binary"
    if all("sum" in r for r in rows):
        return "continuous"
    raise InputError("cannot infer the metric type: rows mix conversions and metric_sum")


def parse_split(raw: str, variants: list[str]) -> dict[str, float]:
    parts = [p.strip() for p in raw.replace(";", "/").replace(":", "/").split("/") if p.strip()]
    if all("=" in p for p in parts):
        named = {}
        for p in parts:
            k, _, val = p.partition("=")
            named[k.strip()] = _num(val, "expected_split")
        if sorted(named) != sorted(variants):
            raise InputError(f"expected_split names {sorted(named)} must match the variants {sorted(variants)}")
        weights = [named[v] for v in variants]
    else:
        weights = [_num(p, "expected_split") for p in parts]
        if len(weights) != len(variants):
            raise InputError(f"expected_split has {len(weights)} parts but there are {len(variants)} variants "
                             f"({', '.join(variants)}); positional parts follow the variant order in the results")
    if any(w <= 0 for w in weights):
        raise InputError("expected_split parts must be > 0")
    tot = sum(weights)
    return {v: w / tot for v, w in zip(variants, weights)}


# ------------------------------------------------------------------ statistics

def srm_check(assigned: dict[str, int], split: dict[str, float], srm_alpha: float) -> dict:
    total = sum(assigned.values())
    rows, chi2 = [], 0.0
    for v, n in assigned.items():
        exp = total * split[v]
        chi2 += (n - exp) ** 2 / exp
        rows.append({"variant": v, "observed": n, "expected": round(exp, 2),
                     "observed_share": round(n / total, 4), "expected_share": round(split[v], 4)})
    df = len(assigned) - 1
    p = chi2_sf(chi2, df)
    return {"chi2": round(chi2, 4), "df": df, "p_value": p, "srm_alpha": srm_alpha,
            "srm_detected": p < srm_alpha, "total": total, "rows": rows}


def describe(rec: dict, mtype: str) -> dict:
    n = rec["n"]
    if mtype == "binary":
        if "conversions" not in rec:
            raise InputError("binary metric needs conversions (or 0/1 values) for every variant")
        p = rec["conversions"] / n
        return {"n": n, "mean": p, "var": p * (1.0 - p), "conversions": rec["conversions"]}
    if "sum" not in rec:
        raise InputError("continuous metric needs metric_sum and metric_sumsq (or values) for every variant")
    if n < 2:
        raise InputError("continuous metric needs at least 2 units per variant")
    mean = rec["sum"] / n
    var = (rec["sumsq"] - rec["sum"] ** 2 / n) / (n - 1)
    if var < 0:
        if var > -1e-9 * max(1.0, abs(rec["sumsq"])):
            var = 0.0
        else:
            raise InputError("metric_sumsq is inconsistent with metric_sum (negative variance)")
    return {"n": n, "mean": mean, "var": var}


def compare(c: dict, t: dict, mtype: str, alpha: float) -> dict:
    diff = t["mean"] - c["mean"]
    if mtype == "binary":
        pool = (c["conversions"] + t["conversions"]) / (c["n"] + t["n"])
        se_pool = math.sqrt(pool * (1 - pool) * (1 / c["n"] + 1 / t["n"]))
        stat = diff / se_pool if se_pool > 0 else 0.0
        p = norm_two_sided_p(stat) if se_pool > 0 else 1.0
        se = math.sqrt(c["var"] / c["n"] + t["var"] / t["n"])
        crit = ND.inv_cdf(1 - alpha / 2)
        df = None
    else:
        se = math.sqrt(c["var"] / c["n"] + t["var"] / t["n"])
        if se == 0:
            stat, p, df, crit = 0.0, (1.0 if diff == 0 else 0.0), None, 0.0
        else:
            stat = diff / se
            num = (c["var"] / c["n"] + t["var"] / t["n"]) ** 2
            den = ((c["var"] / c["n"]) ** 2 / (c["n"] - 1)) + ((t["var"] / t["n"]) ** 2 / (t["n"] - 1))
            df = num / den if den > 0 else float(c["n"] + t["n"] - 2)
            p = 2.0 * (1.0 - t_cdf(abs(stat), df))
            crit = t_ppf(1 - alpha / 2, df)
    rel = diff / c["mean"] if c["mean"] != 0 else None
    return {"diff": diff, "se": se, "stat": stat, "df": df, "p_value": min(1.0, max(0.0, p)),
            "ci_low": diff - crit * se, "ci_high": diff + crit * se, "rel_lift": rel,
            "rel_ci_low": (diff - crit * se) / c["mean"] if c["mean"] != 0 else None,
            "rel_ci_high": (diff + crit * se) / c["mean"] if c["mean"] != 0 else None}


def power_block(c: dict, t: dict, mtype: str, alpha: float, power: float, mde: dict | None) -> dict:
    za, zb = ND.inv_cdf(1 - alpha / 2), ND.inv_cdf(power)
    se_obs = math.sqrt(c["var"] / c["n"] + t["var"] / t["n"])
    out = {"detectable_effect": (za + zb) * se_obs, "achieved_power": None, "n_per_arm_needed": None,
           "mde_abs": None}
    if mde is None:
        return out
    delta = mde["value"] * c["mean"] if mde["relative"] else mde["value"]
    out["mde_abs"] = delta
    if delta == 0:
        return out
    if mtype == "binary":
        p1, p2 = c["mean"], c["mean"] + delta
        if not 0.0 <= p2 <= 1.0:
            out["mde_note"] = "control rate + MDE falls outside 0..1"
            return out
        v1, v2 = p1 * (1 - p1), p2 * (1 - p2)
    else:
        v1, v2 = c["var"], t["var"]
    se_mde = math.sqrt(v1 / c["n"] + v2 / t["n"])
    if se_mde > 0:
        out["achieved_power"] = ND.cdf(abs(delta) / se_mde - za) + ND.cdf(-abs(delta) / se_mde - za)
    if v1 + v2 > 0:
        out["n_per_arm_needed"] = math.ceil((za + zb) ** 2 * (v1 + v2) / delta ** 2)
    return out


def analyse(res: dict, s: dict) -> dict:
    control = s["control"]
    treatments = [v for v in res["variants"] if v != control]
    alpha = s["alpha"]
    prim = s["primary_metric"]
    assigned = res.get("assigned") or {v: res["metrics"][prim]["rows"][v]["n"]
                                       for v in res["variants"] if v in res["metrics"][prim]["rows"]}
    missing = [v for v in res["variants"] if v not in assigned]
    if missing:
        raise InputError(f"primary metric {prim!r} has no row for variant(s) {missing}")
    srm = srm_check(assigned, s["expected_split"], s["srm_alpha"])

    plan = [{"name": prim, "role": "primary", "type": s["metric_type"], "direction": s["direction"]}]
    notes, not_measured = [], []
    for g in s["guardrails"]:
        if g["name"] == prim:
            raise InputError(f"guardrail {g['name']!r} is also the primary metric")
        if g["name"] not in res["metrics"]:
            not_measured.append(g["name"])
            continue
        plan.append({"name": g["name"], "role": "guardrail", "type": infer_type(res["metrics"][g["name"]]),
                     "direction": g["direction"]})
    declared = {p["name"] for p in plan}
    undeclared = sorted(m for m in res["metrics"] if m not in declared
                        and not (res["format"] == "unit-level" and m in ("converted", "value")))
    if undeclared:
        notes.append(f"Metric(s) in the results not declared as primary or guardrail, not analysed: {', '.join(undeclared)}.")

    metrics = []
    for spec in plan:
        rows = res["metrics"][spec["name"]]["rows"]
        absent = [v for v in res["variants"] if v not in rows]
        if absent:
            raise InputError(f"metric {spec['name']!r} has no data for variant(s) {absent}")
        desc = {v: describe(rows[v], spec["type"]) for v in res["variants"]}
        comps = {t: compare(desc[control], desc[t], spec["type"], alpha) for t in treatments}
        adj = holm([comps[t]["p_value"] for t in treatments]) if len(treatments) > 1 else \
            [comps[t]["p_value"] for t in treatments]
        for t, pa in zip(treatments, adj):
            comps[t]["p_adj"] = pa
            comps[t]["significant"] = pa < alpha
            d = spec["direction"]
            if not comps[t]["significant"]:
                comps[t]["effect"] = "no significant change"
            elif d is None:
                comps[t]["effect"] = "significant change, direction not declared"
            else:
                good = comps[t]["diff"] > 0 if d == "higher_better" else comps[t]["diff"] < 0
                comps[t]["effect"] = "significantly better" if good else "significantly worse"
        entry = {**spec, "variants": desc, "comparisons": comps}
        if spec["role"] == "primary":
            entry["power"] = {t: power_block(desc[control], desc[t], spec["type"], alpha, s["power"], s["mde"])
                              for t in treatments}
        metrics.append(entry)

    decisions = {}
    for t in treatments:
        p = metrics[0]["comparisons"][t]
        breaches = [m["name"] for m in metrics[1:] if m["comparisons"][t]["effect"] == "significantly worse"]
        unclear = [m["name"] for m in metrics[1:]
                   if m["comparisons"][t]["effect"] == "significant change, direction not declared"]
        if p["effect"] == "significantly worse":
            dec, why = "don't ship", "primary metric is significantly worse than control"
        elif p["effect"] == "significantly better" and breaches:
            dec, why = "don't ship", f"primary improved but guardrail(s) significantly worse: {', '.join(breaches)}"
        elif p["effect"] == "significantly better" and unclear:
            dec, why = "inconclusive", (f"primary improved but guardrail(s) {', '.join(unclear)} moved significantly "
                                        f"and have no declared direction ({TBB})")
        elif p["effect"] == "significantly better" and not_measured:
            dec, why = "inconclusive", (f"primary improved but declared guardrail(s) {', '.join(not_measured)} "
                                        f"are not in the results ({TBB})")
        elif p["effect"] == "significantly better":
            dec, why = "ship", "primary metric significantly better and no guardrail significantly worse"
        else:
            dec, why = "inconclusive", "no significant difference on the primary metric at the chosen alpha"
        decisions[t] = {"decision": dec, "reason": why, "guardrail_breaches": breaches}

    if srm["srm_detected"]:
        overall = {"decision": "untrustworthy", "variant": None,
                   "reason": "sample ratio mismatch detected; fix assignment or logging before reading the results"}
    else:
        ships = [t for t in treatments if decisions[t]["decision"] == "ship"]
        if ships:
            sign = 1 if s["direction"] == "higher_better" else -1
            best = max(ships, key=lambda t: (sign * metrics[0]["comparisons"][t]["diff"], t))
            overall = {"decision": "ship", "variant": best, "reason": decisions[best]["reason"]}
        elif all(decisions[t]["decision"] == "don't ship" for t in treatments):
            overall = {"decision": "don't ship", "variant": None,
                       "reason": "; ".join(f"{t}: {decisions[t]['reason']}" for t in treatments)}
        else:
            overall = {"decision": "inconclusive", "variant": None,
                       "reason": "; ".join(f"{t}: {decisions[t]['reason']}" for t in treatments)}
    return {"control": control, "treatments": treatments, "srm": srm, "metrics": metrics,
            "decisions": decisions, "overall": overall, "guardrails_not_measured": not_measured, "notes": notes}


# ------------------------------------------------------------------ rendering

def f6(x) -> str:
    return "n/a" if x is None else f"{x:.6f}"


def f4(x) -> str:
    return "n/a" if x is None else f"{x:.4f}"


def pfmt(p: float) -> str:
    return "< 0.000001" if p < 1e-6 else f"{p:.6f}"


def pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:+.2f}%"


def render_csv(a: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["metric", "role", "variant", "n", "rate_or_mean", "diff", "ci_low", "ci_high", "rel_lift",
                "p_value", "p_adj", "significant"])
    for m in a["metrics"]:
        c = m["variants"][a["control"]]
        w.writerow([m["name"], m["role"], a["control"], c["n"], f6(c["mean"]), "n/a", "n/a", "n/a", "n/a",
                    "n/a", "n/a", "control"])
        for t in a["treatments"]:
            d, cmp_ = m["variants"][t], m["comparisons"][t]
            w.writerow([m["name"], m["role"], t, d["n"], f6(d["mean"]), f6(cmp_["diff"]), f6(cmp_["ci_low"]),
                        f6(cmp_["ci_high"]), f4(cmp_["rel_lift"]), f6(cmp_["p_value"]), f6(cmp_["p_adj"]),
                        "yes" if cmp_["significant"] else "no"])
    return buf.getvalue()


def prov(s: dict, key: str) -> str:
    return {"config": "from config", "default": "default", "inferred": "inferred from the data",
            "tbd": "not supplied", "none": "none declared"}[s["prov"][key]]


def render_md(a: dict, s: dict, fmt: str) -> str:
    srm, ov, prim = a["srm"], a["overall"], a["metrics"][0]
    L = [f"# A/B test analysis — {s['experiment_name']}", ""]
    head = {"ship": f"**Decision: ship `{ov['variant']}`.**", "don't ship": "**Decision: don't ship.**",
            "inconclusive": "**Decision: inconclusive.**",
            "untrustworthy": "**Results untrustworthy: sample ratio mismatch detected. Do not decide on these numbers.**"}
    L += ["## Summary", "", head[ov["decision"]] + f" {ov['reason'][0].upper() + ov['reason'][1:]}.", ""]
    L += [f"- Primary metric `{prim['name']}` ({prim['type']}, {prim['direction'].replace('_', ' ')}); "
          f"control `{a['control']}`; {len(a['treatments'])} treatment(s); alpha {s['alpha']:g}.",
          f"- Sample ratio check: chi-square {srm['chi2']:.4f}, df {srm['df']}, p {pfmt(srm['p_value'])} — "
          f"{'SRM DETECTED' if srm['srm_detected'] else 'no mismatch'} (threshold p < {s['srm_alpha']:g})."]
    void = " (void: SRM detected)" if srm["srm_detected"] else ""
    for t in a["treatments"]:
        c = prim["comparisons"][t]
        L.append(f"- `{t}` vs `{a['control']}`: diff {f6(c['diff'])} ({pct(c['rel_lift'])} relative), "
                 f"p_adj {pfmt(c['p_adj'])} → {a['decisions'][t]['decision']}{void}.")
    L += ["", "| Setting | Value | Basis |", "|---|---|---|",
          f"| control | {s['control']} | {prov(s, 'control')} |",
          f"| alpha | {s['alpha']:g} | {prov(s, 'alpha')} |",
          f"| power | {s['power']:g} | {prov(s, 'power')} |",
          f"| srm_alpha | {s['srm_alpha']:g} | {prov(s, 'srm_alpha')} |",
          f"| expected_split | {' / '.join(f'{v}={w:.4f}' for v, w in s['expected_split'].items())} | "
          f"{prov(s, 'expected_split')} |",
          f"| metric_type | {s['metric_type']} | {prov(s, 'metric_type')} |",
          f"| direction | {s['direction']} | {prov(s, 'direction')} |",
          f"| mde | {s['mde']['raw'] if s['mde'] else TBB} | {prov(s, 'mde')} |",
          f"| guardrails | {', '.join(g['name'] + (':' + g['direction'] if g['direction'] else '') for g in s['guardrails']) or 'none'} "
          f"| {prov(s, 'guardrails')} |", f"| results format | {fmt} | detected |"]

    L += ["", "## Sample ratio check", ""]
    if srm["srm_detected"]:
        L.append(f"**SRM detected (p {pfmt(srm['p_value'])} < {s['srm_alpha']:g}).** The observed split differs from "
                 "the expected split by more than chance allows. Find the cause (assignment, redirects, bot filtering, "
                 "logging loss) before reading any metric below. The run exits 1.")
    else:
        L.append(f"No sample ratio mismatch (p {pfmt(srm['p_value'])} ≥ {s['srm_alpha']:g}).")
    L += ["", "| Variant | Observed units | Expected units | Observed share | Expected share |", "|---|---|---|---|---|"]
    for r in srm["rows"]:
        L.append(f"| {r['variant']} | {r['observed']} | {r['expected']:.2f} | {r['observed_share']:.4f} | "
                 f"{r['expected_share']:.4f} |")

    def table(m):
        rows = ["| Variant | n | Rate / mean | Diff | CI low | CI high | Rel. lift | p | p_adj | Significant |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        c = m["variants"][a["control"]]
        rows.append(f"| {a['control']} (control) | {c['n']} | {f6(c['mean'])} | — | — | — | — | — | — | — |")
        for t in a["treatments"]:
            d, x = m["variants"][t], m["comparisons"][t]
            rows.append(f"| {t} | {d['n']} | {f6(d['mean'])} | {f6(x['diff'])} | {f6(x['ci_low'])} | "
                        f"{f6(x['ci_high'])} | {pct(x['rel_lift'])} | {pfmt(x['p_value'])} | {pfmt(x['p_adj'])} | "
                        f"{'yes' if x['significant'] else 'no'} |")
        return rows

    L += ["", "## Results", "", f"Primary metric `{prim['name']}` ({prim['type']}). CIs are "
          f"{(1 - s['alpha']) * 100:g}% two-sided.", ""] + table(prim)
    L += ["", "| Treatment | Smallest detectable effect | MDE (absolute) | Achieved power for MDE | n per arm for MDE |",
          "|---|---|---|---|---|"]
    for t in a["treatments"]:
        pw = prim["power"][t]
        L.append(f"| {t} | {f6(pw['detectable_effect'])} | {f6(pw['mde_abs']) if pw['mde_abs'] is not None else TBB} | "
                 f"{f4(pw['achieved_power']) if pw['achieved_power'] is not None else TBB} | "
                 f"{pw['n_per_arm_needed'] if pw['n_per_arm_needed'] is not None else TBB} |")
    if s["mde"] is None:
        L += ["", f"No minimum detectable effect (MDE) was declared: {TBB}. Power and the required sample size "
              "cannot be judged; the smallest detectable effect above uses the observed n, alpha and power "
              f"({prov(s, 'power')})."]

    L += ["", "## Guardrails", ""]
    if len(a["metrics"]) == 1 and not a["guardrails_not_measured"]:
        L.append(f"No guardrail metrics declared: {TBB}. Decision rests on the primary metric alone.")
    for m in a["metrics"][1:]:
        L += [f"### `{m['name']}` ({m['type']}, {m['direction'].replace('_', ' ') if m['direction'] else 'direction not declared'})", ""]
        if m["direction"] is None:
            L += [f"Direction not declared: {TBB}. Any significant move blocks a ship decision.", ""]
        L += table(m)
        L.append("")
        for t in a["treatments"]:
            L.append(f"- `{t}`: {m['comparisons'][t]['effect']}.")
        L.append("")
    for g in a["guardrails_not_measured"]:
        L.append(f"- Guardrail `{g}` declared but not present in the results: {TBB}.")

    L += ["", "## Decision", "", "| Treatment | Decision | Reason |", "|---|---|---|"]
    for t in a["treatments"]:
        d = a["decisions"][t]
        L.append(f"| {t} | {d['decision']}{void} | {d['reason']} |")
    L += ["", f"Overall: **{ov['decision']}" + (f" `{ov['variant']}`**." if ov["variant"] else "**.")]
    L += ["", "Rule: ship when the primary metric is significantly better (Holm-adjusted p < alpha) and no guardrail "
          "is significantly worse; don't ship when the primary metric is significantly worse, or when it improved "
          "but a guardrail is significantly worse; otherwise inconclusive. An SRM overrides every decision."]

    L += ["", "## Method & limits", "",
          "- SRM: Pearson chi-square goodness of fit of assigned units to the expected split (df = variants − 1). "
          "The p < 0.001 default is a practitioner convention; Microsoft's experimentation platform uses 0.0005 "
          "(see references/sources.md).",
          "- Binary metrics: two-proportion z-test with pooled standard error; Wald CI on the difference with the "
          "unpooled standard error; relative lift = diff / control rate.",
          "- Continuous metrics: Welch's t-test (Welch–Satterthwaite df); p from the Student-t CDF computed with the "
          "regularised incomplete beta function; CI uses the t quantile.",
          "- Multiple treatments: Holm step-down adjustment within each metric across treatments.",
          "- Power: normal approximation, two-sided, unadjusted alpha; n per arm assumes equal allocation.",
          "- Limits: frequentist fixed-horizon analysis — peeking at interim results inflates false positives; "
          "units are assumed independent (no clustering, no repeated measures); novelty effects, seasonality and "
          "interference between variants are not detected; the decision is statistical, not a product or risk "
          "sign-off."]
    for n in a["notes"]:
        L.append(f"- Note: {n}")
    return "\n".join(L) + "\n"


def to_json(a: dict, s: dict, cfg: dict, fmt: str) -> str:
    def r(x):
        if isinstance(x, float):
            return float(f"{x:.10g}")  # 10 significant digits: keeps tiny p-values meaningful
        if isinstance(x, dict):
            return {k: r(v) for k, v in x.items()}
        if isinstance(x, list):
            return [r(v) for v in x]
        return x
    eff = {k: v for k, v in s.items() if k != "prov"}
    doc = {"config": cfg, "settings": eff, "provenance": s["prov"], "results_format": fmt, **a,
           "tbd_owner": OWNER}
    return json.dumps(r(doc), indent=2, sort_keys=True) + "\n"


def build(results: Path, cfg: dict) -> tuple[dict, dict[str, str], int]:
    s_guard = parse_guardrails(cfg.get("guardrails", ""))
    res = read_results(results, [g["name"] for g in s_guard])
    s = settings(cfg, res)
    a = analyse(res, s)
    files = {"ab-results.csv": render_csv(a), "ab-report.md": render_md(a, s, res["format"]),
             "ab.json": to_json(a, s, cfg, res["format"])}
    return a, files, (1 if a["srm"]["srm_detected"] else 0)


def verify(path: Path, results: Path) -> int:
    meta = path.parent / "ab.json"
    if not path.is_file() or not meta.is_file():
        print(f"verify: {path} or its sibling ab.json is missing")
        return 1
    if path.name not in OUTPUTS:
        print(f"verify: {path.name} is not one of {OUTPUTS}")
        return 1
    cfg = json.loads(meta.read_text(encoding="utf-8")).get("config", {})
    try:
        _, files, _ = build(results, cfg)
    except InputError as e:
        print(f"verify: cannot re-derive: {e}")
        return 1
    if path.read_text(encoding="utf-8") != files[path.name]:
        print(f"verify: {path.name} does not match the re-derived output")
        return 1
    print(f"verify: {path.name} matches the re-derived output")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", type=Path, help="results CSV (aggregated or unit-level)")
    ap.add_argument("--config", type=Path, help="optional kv-csv config")
    ap.add_argument("--out-dir", type=Path, help="directory for ab-results.csv, ab-report.md, ab.json")
    ap.add_argument("--verify", type=Path, help="re-derive one output from --results and its sibling ab.json")
    a = ap.parse_args(argv)
    if a.results is None:
        print("error: --results is required", file=sys.stderr)
        return 2
    if a.verify:
        return verify(a.verify, a.results)
    if a.out_dir is None:
        print("error: --out-dir is required", file=sys.stderr)
        return 2
    try:
        analysis, files, code = build(a.results, read_config(a.config))
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    a.out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (a.out_dir / name).write_text(text, encoding="utf-8")
    ov = analysis["overall"]
    print(f"decision: {ov['decision']}{' ' + ov['variant'] if ov['variant'] else ''}; wrote {', '.join(OUTPUTS)} "
          f"to {a.out_dir}")
    if code:
        print(f"SRM detected (p {pfmt(analysis['srm']['p_value'])}): results untrustworthy", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())

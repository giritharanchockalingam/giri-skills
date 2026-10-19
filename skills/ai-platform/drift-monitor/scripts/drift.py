#!/usr/bin/env python3
"""Data / prediction drift between a baseline window and a current window (stdlib only).

For every feature (column) shared by the two CSV windows:
  numeric      PSI over baseline decile bins + two-sample Kolmogorov-Smirnov D and p-value (exact; Stephens-corrected asymptotic above 1e6 n*m)
  categorical  PSI over categories (a category unseen in the baseline gets its own bin) +
               chi-square test of homogeneity (2 x K table) and its p-value
  both         missing-value rate in each window
Type is detected per feature (numeric when >= 95% of non-missing values in both windows parse as
finite floats) and can be overridden with --types "col=numeric,col2=categorical".

Usage:
  python3 -I drift.py --baseline base.csv --current cur.csv [--features a,b] [--thresholds t.csv]
                      [--types "a=categorical"] --out-dir OUT
  python3 -I drift.py --verify OUT/drift.csv        # re-checks csv/md against drift.json
  python3 -I drift.py --calc ks_sf=1.3581            # print Q_KS(lambda) (diagnostic)
  python3 -I drift.py --calc chi2_sf=3.841,1         # print chi-square upper tail (stat, df)

Thresholds CSV: metric,warn,alert (metrics: psi, p_value, null_rate_delta; blank = not used).
Defaults: psi warn 0.1 alert 0.25 (industry convention, see references/sources.md), p_value alert
0.01; null_rate_delta has no default.
Status per feature: insufficient-data (< 30 non-missing values in either window) | alert | warn | ok.
Outputs (in --out-dir): drift.csv, drift-report.md, drift.json.
Exit codes: 0 no alert · 1 at least one feature in alert (outputs still written) ·
2 missing/invalid input. No network; writes only inside --out-dir.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
from pathlib import Path

MIN_ROWS = 30
NUMERIC_SHARE = 0.95
EPS = 1e-4  # proportion used in place of 0 for an empty PSI bin (keeps ln() finite)
NULLS = {"", "na", "n/a", "nan", "null", "none"}
METRICS = ("psi", "p_value", "null_rate_delta")
DEFAULTS = {"psi": (0.1, 0.25), "p_value": (None, 0.01), "null_rate_delta": (None, None)}
TBD_THRESH = "[TO BE BASELINED — owner: ML engineering lead]"
TBD_NULL = "[TO BE BASELINED — owner: Data owner]"
CSV_COLS = ["feature", "type", "n_baseline", "n_current", "psi", "ks_d", "p_value",
            "null_rate_baseline", "null_rate_current", "status"]


class InputError(Exception):
    """Missing or invalid input -> exit 2."""


# ------------------------------------------------------------------ formatting
def f4(x):
    return "" if x is None else f"{x:.4f}"


def f3(x):
    return "" if x is None else f"{x:.3f}"


def fp(p):
    if p is None:
        return ""
    return "<0.0001" if p < 0.0001 else f"{p:.4f}"


# ------------------------------------------------------------------ input
def read_csv(path: str, label: str) -> tuple[list[str], list[dict]]:
    p = Path(path)
    if not p.is_file():
        raise InputError(f"{label} file not found: {path}")
    lines = [ln for ln in p.read_text(encoding="utf-8-sig").splitlines() if not ln.startswith("#")]
    rd = csv.DictReader(io.StringIO("\n".join(lines)))
    if not rd.fieldnames:
        raise InputError(f"{label} has no header row: {path}")
    cols = [c.strip() for c in rd.fieldnames]
    if len(set(cols)) != len(cols):
        raise InputError(f"{label} has duplicate column names")
    rows = [{(k or "").strip(): (v or "") for k, v in r.items()} for r in rd]
    return cols, rows


def is_null(v: str) -> bool:
    return v.strip().lower() in NULLS


def to_float(v: str):
    try:
        x = float(v.strip())
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def read_thresholds(path: str | None) -> tuple[dict, bool]:
    th = {k: list(v) for k, v in DEFAULTS.items()}
    if not path:
        return th, False
    _, rows = read_csv(path, "thresholds")
    for r in rows:
        m = r.get("metric", "").strip()
        if m not in METRICS:
            raise InputError(f"thresholds: unknown metric '{m}' (allowed: {', '.join(METRICS)})")
        for i, k in enumerate(("warn", "alert")):
            v = r.get(k, "").strip()
            if v == "":
                th[m][i] = None
                continue
            x = to_float(v)
            if x is None or x < 0:
                raise InputError(f"thresholds: {m} {k} must be a non-negative number, got '{v}'")
            th[m][i] = x
    return th, True


def parse_types(spec: str | None) -> dict:
    out = {}
    for part in (spec or "").split(","):
        if not part.strip():
            continue
        if "=" not in part:
            raise InputError(f"--types entry '{part}' must be col=numeric|categorical")
        k, v = (s.strip() for s in part.split("=", 1))
        if v not in ("numeric", "categorical"):
            raise InputError(f"--types: '{v}' for '{k}' must be numeric or categorical")
        out[k] = v
    return out


# ------------------------------------------------------------------ statistics
def decile_edges(sorted_vals: list[float]) -> list[float]:
    """Nearest-rank 10th..90th percentiles of the baseline; duplicate edges collapse."""
    n = len(sorted_vals)
    edges = []
    for q in range(1, 10):
        e = sorted_vals[max(0, math.ceil(q * n / 10) - 1)]
        if not edges or e > edges[-1]:
            edges.append(e)
    return edges


def bin_index(x: float, edges: list[float]) -> int:
    """Bins are (-inf, e1], (e1, e2], ..., (ek, inf)."""
    lo, hi = 0, len(edges)
    while lo < hi:
        mid = (lo + hi) // 2
        if x <= edges[mid]:
            hi = mid
        else:
            lo = mid + 1
    return lo


def psi_from_counts(b: list[int], c: list[int]) -> float:
    nb, nc = sum(b), sum(c)
    total = 0.0
    for bi, ci in zip(b, c):
        pb = bi / nb if bi else EPS
        pc = ci / nc if ci else EPS
        total += (pc - pb) * math.log(pc / pb)
    return total


def psi_numeric(base: list[float], cur: list[float]) -> tuple[float, int]:
    edges = decile_edges(sorted(base))
    k = len(edges) + 1
    b, c = [0] * k, [0] * k
    for x in base:
        b[bin_index(x, edges)] += 1
    for x in cur:
        c[bin_index(x, edges)] += 1
    return psi_from_counts(b, c), k


def ks_statistic(a: list[float], b: list[float]) -> float:
    a, b = sorted(a), sorted(b)
    n, m = len(a), len(b)
    i = j = 0
    d = 0.0
    while i < n and j < m:
        x = min(a[i], b[j])
        while i < n and a[i] == x:
            i += 1
        while j < m and b[j] == x:
            j += 1
        d = max(d, abs(i / n - j / m))
    return d


def kolmogorov_sf(lam: float) -> float:
    """Q_KS(lambda) = P(K > lambda) for the Kolmogorov distribution."""
    if lam <= 0:
        return 1.0
    if lam < 1.0:
        # P(K <= l) = sqrt(2*pi)/l * sum_{k>=1} exp(-(2k-1)^2 pi^2 / (8 l^2)); fast for small l
        s = 0.0
        for k in range(1, 200):
            t = math.exp(-((2 * k - 1) ** 2) * math.pi ** 2 / (8 * lam * lam))
            s += t
            if t < 1e-17:
                break
        return min(1.0, max(0.0, 1.0 - math.sqrt(2 * math.pi) / lam * s))
    s = 0.0
    for k in range(1, 200):
        t = math.exp(-2.0 * k * k * lam * lam)
        s += t if k % 2 else -t
        if t < 1e-17:
            break
    return min(1.0, max(0.0, 2.0 * s))


EXACT_KS_MAX_CELLS = 1_000_000  # n*m above this -> Stephens-corrected asymptotic tail (cost grows with n*m)


def ks_pvalue_exact(d: float, n: int, m: int) -> float:
    """Exact two-sided P(D >= d) for the two-sample KS statistic (no ties): 1 - P(the merged-sample random walk
    stays strictly inside the band |i/n - j/m| < d). Every interleaving is equally likely, so the walk steps to
    (i+1, j) with probability (n-i)/(n+m-i-j). Dynamic programme over the n x m lattice."""
    lim = round(d * n * m) - 0.5  # inside: |i*m - j*n| < d*n*m  (integers; d is a multiple of 1/lcm(n, m))
    row = [0.0] * (m + 1)  # row[j] = P(reach (i, j) while inside)
    row[0] = 1.0
    for j in range(1, m + 1):  # i = 0 edge
        row[j] = row[j - 1] * (m - j + 1) / (n + m - j + 1) if abs(-j * n) < lim else 0.0
    for i in range(1, n + 1):
        new = [0.0] * (m + 1)
        for j in range(0, m + 1):
            if abs(i * m - j * n) >= lim:
                continue
            p = row[j] * (n - i + 1) / (n + m - i - j + 1)  # from (i-1, j) by an x-step
            if j:
                p += new[j - 1] * (m - j + 1) / (n + m - i - j + 1)  # from (i, j-1) by a y-step
            new[j] = p
        row = new
    return min(1.0, max(0.0, 1.0 - row[m]))


def ks_pvalue(d: float, n: int, m: int) -> float:
    """Exact when n*m <= EXACT_KS_MAX_CELLS; otherwise the asymptotic Kolmogorov tail with Stephens' small-sample
    correction, Q_KS((sqrt(en) + 0.12 + 0.11/sqrt(en)) * d), en = n m / (n + m)."""
    if d <= 0:
        return 1.0
    if n * m <= EXACT_KS_MAX_CELLS:
        return ks_pvalue_exact(d, n, m)
    en = math.sqrt(n * m / (n + m))
    return kolmogorov_sf((en + 0.12 + 0.11 / en) * d)


def gammainc_upper(a: float, x: float) -> float:
    """Regularised upper incomplete gamma Q(a, x) (series for x < a+1, else Lentz continued fraction)."""
    if a <= 0:
        raise ValueError("a must be > 0")
    if x <= 0:
        return 1.0
    gln = math.lgamma(a)
    if x < a + 1:
        ap, s, delta = a, 1.0 / a, 1.0 / a
        for _ in range(10000):
            ap += 1
            delta *= x / ap
            s += delta
            if abs(delta) < abs(s) * 1e-15:
                break
        return max(0.0, 1.0 - s * math.exp(-x + a * math.log(x) - gln))
    tiny = 1e-300
    b = x + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
    return min(1.0, math.exp(-x + a * math.log(x) - gln) * h)


def chi2_sf(stat: float, df: int) -> float:
    return gammainc_upper(df / 2.0, stat / 2.0)


def chi2_homogeneity(b: list[int], c: list[int]) -> tuple[float, int]:
    nb, nc = sum(b), sum(c)
    n = nb + nc
    stat = 0.0
    k = 0
    for bi, ci in zip(b, c):
        tot = bi + ci
        if tot == 0:
            continue
        k += 1
        for obs, rowtot in ((bi, nb), (ci, nc)):
            e = rowtot * tot / n
            stat += (obs - e) ** 2 / e
    return stat, max(k - 1, 0)


# ------------------------------------------------------------------ analysis
def classify(vals_b: list[str], vals_c: list[str]) -> str:
    vals = [v for v in vals_b + vals_c if not is_null(v)]
    if not vals:
        return "categorical"
    ok = sum(1 for v in vals if to_float(v) is not None)
    return "numeric" if ok / len(vals) >= NUMERIC_SHARE else "categorical"


def status_for(r: dict, th: dict) -> tuple[str, list[str]]:
    if r["n_baseline"] < MIN_ROWS or r["n_current"] < MIN_ROWS:
        return "insufficient-data", [f"fewer than {MIN_ROWS} non-missing values in a window"]
    reasons_a, reasons_w = [], []
    pw, pa = th["psi"]
    if r["psi"] is not None:
        if pa is not None and r["psi"] >= pa:
            reasons_a.append(f"PSI {f4(r['psi'])} >= {pa:g}")
        elif pw is not None and r["psi"] >= pw:
            reasons_w.append(f"PSI {f4(r['psi'])} >= {pw:g}")
    vw, va = th["p_value"]
    if r["p_value"] is not None:
        test = "KS" if r["type"] == "numeric" else "chi-square"
        if va is not None and r["p_value"] < va:
            reasons_a.append(f"{test} p {fp(r['p_value'])} < {va:g}")
        elif vw is not None and r["p_value"] < vw:
            reasons_w.append(f"{test} p {fp(r['p_value'])} < {vw:g}")
    nw, na = th["null_rate_delta"]
    delta = abs(r["null_rate_current"] - r["null_rate_baseline"])
    if na is not None and delta >= na:
        reasons_a.append(f"missing-rate change {f3(delta)} >= {na:g}")
    elif nw is not None and delta >= nw:
        reasons_w.append(f"missing-rate change {f3(delta)} >= {nw:g}")
    if reasons_a:
        return "alert", reasons_a + reasons_w
    if reasons_w:
        return "warn", reasons_w
    return "ok", []


def analyse_feature(name, ftype, vb_raw, vc_raw, th) -> dict:
    nb_rows, nc_rows = len(vb_raw), len(vc_raw)
    vb = [v.strip() for v in vb_raw if not is_null(v)]
    vc = [v.strip() for v in vc_raw if not is_null(v)]
    r = {"feature": name, "type": ftype, "rows_baseline": nb_rows, "rows_current": nc_rows,
         "null_rate_baseline": (nb_rows - len(vb)) / nb_rows if nb_rows else 0.0,
         "null_rate_current": (nc_rows - len(vc)) / nc_rows if nc_rows else 0.0,
         "psi": None, "ks_d": None, "p_value": None, "test": None, "df": None, "bins": None,
         "unparsed_baseline": 0, "unparsed_current": 0}
    if ftype == "numeric":
        fb = [x for x in (to_float(v) for v in vb) if x is not None]
        fc = [x for x in (to_float(v) for v in vc) if x is not None]
        r["unparsed_baseline"], r["unparsed_current"] = len(vb) - len(fb), len(vc) - len(fc)
        r["n_baseline"], r["n_current"] = len(fb), len(fc)
        if fb and fc:
            r["psi"], r["bins"] = psi_numeric(fb, fc)
            r["ks_d"] = ks_statistic(fb, fc)
            r["p_value"] = ks_pvalue(r["ks_d"], len(fb), len(fc))
            r["test"] = "ks"
    else:
        r["n_baseline"], r["n_current"] = len(vb), len(vc)
        cats = sorted(set(vb) | set(vc))
        cb = {k: 0 for k in cats}
        cc = {k: 0 for k in cats}
        for v in vb:
            cb[v] += 1
        for v in vc:
            cc[v] += 1
        if vb and vc:
            b = [cb[k] for k in cats]
            c = [cc[k] for k in cats]
            r["psi"], r["bins"] = psi_from_counts(b, c), len(cats)
            stat, df = chi2_homogeneity(b, c)
            r["chi2"], r["df"], r["test"] = stat, df, "chi2"
            r["p_value"] = chi2_sf(stat, df) if df > 0 else 1.0
            r["unseen_categories"] = [k for k in cats if cb[k] == 0]
    r["status"], r["reasons"] = status_for(r, th)
    return r


# ------------------------------------------------------------------ outputs
def csv_row(r: dict) -> list[str]:
    return [r["feature"], r["type"], str(r["n_baseline"]), str(r["n_current"]), f4(r["psi"]),
            f4(r["ks_d"]), fp(r["p_value"]), f3(r["null_rate_baseline"]), f3(r["null_rate_current"]),
            r["status"]]


def write_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLS)
    for r in rows:
        w.writerow(csv_row(r))
    return buf.getvalue()


def thr_text(v):
    return "not used" if v is None else f"{v:g}"


def write_md(doc: dict) -> str:
    rows, th = doc["features"], doc["thresholds"]
    counts = doc["counts"]
    L = ["# Drift report", ""]
    L += ["## Summary", ""]
    verdict = "ALERT — drift beyond the alert threshold" if counts["alert"] else "No feature in alert"
    L.append(f"**{verdict}.** Features checked: {len(rows)} · ok {counts['ok']} · warn {counts['warn']} · "
             f"alert {counts['alert']} · insufficient-data {counts['insufficient-data']}.")
    L.append("")
    L.append(f"Baseline: `{doc['inputs']['baseline']}` ({doc['inputs']['rows_baseline']} rows). "
             f"Current: `{doc['inputs']['current']}` ({doc['inputs']['rows_current']} rows).")
    if doc["missing_columns"]:
        L.append(f"Columns not in both windows (not compared): {', '.join(doc['missing_columns'])}.")
    L.append("")
    L.append(f"Thresholds ({'from the supplied thresholds file' if doc['thresholds_supplied'] else 'defaults'}): "
             f"PSI warn {thr_text(th['psi'][0])}, alert {thr_text(th['psi'][1])}; "
             f"p-value warn {thr_text(th['p_value'][0])}, alert {thr_text(th['p_value'][1])}; "
             f"missing-rate change warn {thr_text(th['null_rate_delta'][0])}, alert {thr_text(th['null_rate_delta'][1])}.")
    if not doc["thresholds_supplied"]:
        L.append(f"Agreed thresholds for this system: {TBD_THRESH}. The defaults are conventions, not tested limits.")
    if th["null_rate_delta"][0] is None and th["null_rate_delta"][1] is None:
        L.append(f"Missing-rate change threshold: {TBD_NULL} (reported, not gated).")
    L += ["", "## Features", "",
          "| Feature | Type | n base | n cur | PSI | KS D | p-value | Missing base | Missing cur | Status |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        c = csv_row(r)
        L.append("| " + " | ".join(x if x != "" else "—" for x in c) + " |")
    L += ["", "## Alerts", ""]
    flagged = [r for r in rows if r["status"] in ("alert", "warn", "insufficient-data")]
    if not flagged:
        L.append("None: every feature is within the thresholds.")
    for r in flagged:
        extra = ""
        if r.get("unseen_categories"):
            extra = f" Categories unseen in the baseline: {', '.join(r['unseen_categories'])}."
        L.append(f"- **{r['feature']}** — {r['status']}: {'; '.join(r['reasons'])}.{extra} "
                 f"Owner to investigate: ML engineering lead.")
    L += ["", "## Method & limits", "",
          f"- Numeric (>= {int(NUMERIC_SHARE * 100)}% of non-missing values parse as numbers, unless overridden): "
          "PSI over 10 bins cut at the baseline's nearest-rank deciles (tied edges merge bins); "
          "two-sample Kolmogorov-Smirnov D with its exact p-value (lattice-path count; ties make it approximate); above 1,000,000 n·m cells the Stephens-corrected asymptotic Q_KS((√en + 0.12 + 0.11/√en)·D).",
          "- Categorical: PSI over categories, a category unseen in the baseline gets its own bin; "
          "chi-square test of homogeneity on the 2 x K count table, p-value from the regularised upper incomplete gamma.",
          f"- PSI = sum((cur - base) · ln(cur / base)); an empty bin uses proportion {EPS:g} so the log stays finite.",
          "- Missing values (blank, NA, N/A, NaN, null, None) are excluded from the distributions and reported as a rate.",
          f"- A window with fewer than {MIN_ROWS} non-missing values gives status insufficient-data, never alert.",
          "- PSI cut-offs 0.1 / 0.25 are an industry rule of thumb (Lewis 1994, via du Pisanie et al. 2023), "
          "not a statistical law; they ignore sample size and bin count.",
          "- p-values shrink with sample size: on large windows a trivial shift can be significant. Read PSI and D for magnitude.",
          "- Each feature is tested on its own (no multiple-comparison correction, no joint drift). "
          "Drift is a signal to investigate, not proof that model quality fell."]
    return "\n".join(L) + "\n"


def jsonable(rows):
    out = []
    for r in rows:
        d = dict(r)
        for k in ("psi", "ks_d", "p_value", "chi2"):
            if d.get(k) is not None:
                d[k] = round(d[k], 12)
        d["null_rate_baseline"] = round(d["null_rate_baseline"], 12)
        d["null_rate_current"] = round(d["null_rate_current"], 12)
        out.append(d)
    return out


def run(args) -> int:
    if not args.baseline or not args.current:
        raise InputError("--baseline and --current are both required")
    if not args.out_dir:
        raise InputError("--out-dir is required")
    cols_b, rows_b = read_csv(args.baseline, "baseline")
    cols_c, rows_c = read_csv(args.current, "current")
    th, supplied = read_thresholds(args.thresholds)
    types = parse_types(args.types)
    shared = [c for c in cols_b if c in cols_c]
    missing = sorted((set(cols_b) ^ set(cols_c)))
    if args.features:
        feats = [f.strip() for f in args.features.split(",") if f.strip()]
        bad = [f for f in feats if f not in shared]
        if bad:
            raise InputError(f"features not present in both windows: {', '.join(bad)}")
    else:
        feats = shared
    if not feats:
        raise InputError("no shared columns to compare")
    unknown = [k for k in types if k not in feats]
    if unknown:
        raise InputError(f"--types names columns not being compared: {', '.join(unknown)}")
    if not rows_b or not rows_c:
        raise InputError("baseline and current must each have at least one data row")
    results = []
    for f in feats:
        vb = [r.get(f, "") for r in rows_b]
        vc = [r.get(f, "") for r in rows_c]
        ftype = types.get(f) or classify(vb, vc)
        results.append(analyse_feature(f, ftype, vb, vc, th))
    counts = {k: sum(1 for r in results if r["status"] == k) for k in ("ok", "warn", "alert", "insufficient-data")}
    doc = {"skill": "drift-monitor", "version": "0.2.0",
           "inputs": {"baseline": Path(args.baseline).name, "current": Path(args.current).name,
                      "rows_baseline": len(rows_b), "rows_current": len(rows_c)},
           "thresholds": th, "thresholds_supplied": supplied, "min_rows": MIN_ROWS, "epsilon": EPS,
           "missing_columns": missing, "counts": counts, "features": jsonable(results),
           "verdict": "alert" if counts["alert"] else "pass"}
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "drift.csv").write_text(write_csv(results), encoding="utf-8")
    (out / "drift-report.md").write_text(write_md(doc), encoding="utf-8")
    (out / "drift.json").write_text(json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                                    encoding="utf-8")
    print(f"drift: {len(results)} features · ok {counts['ok']} warn {counts['warn']} alert {counts['alert']} "
          f"insufficient {counts['insufficient-data']} -> {out}")
    if counts["alert"]:
        names = ", ".join(r["feature"] for r in results if r["status"] == "alert")
        print(f"GATE: drift alert on {names}", file=sys.stderr)
        return 1
    return 0


def verify(path: str) -> int:
    """Re-derive every status from drift.json metrics + thresholds; csv and md must agree with it."""
    p = Path(path)
    jp = p.parent / "drift.json"
    if not p.is_file() or not jp.is_file():
        print(f"verify: missing {p if not p.is_file() else jp}")
        return 1
    doc = json.loads(jp.read_text(encoding="utf-8"))
    th = doc["thresholds"]
    errs = []
    expected = []
    for r in doc["features"]:
        st, _ = status_for(r, th)
        if st != r["status"]:
            errs.append(f"{r['feature']}: status {r['status']} but metrics give {st}")
        expected.append(csv_row(r))
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".csv":
        got = list(csv.reader(io.StringIO(text)))
        if not got or got[0] != CSV_COLS:
            errs.append("drift.csv header differs")
        elif got[1:] != expected:
            errs.append("drift.csv rows differ from drift.json")
    else:
        for row in expected:
            line = "| " + " | ".join(x if x != "" else "—" for x in row) + " |"
            if line not in text:
                errs.append(f"report lacks row for {row[0]}")
        n_alert = sum(1 for r in doc["features"] if r["status"] == "alert")
        if (n_alert > 0) != ("**ALERT" in text):
            errs.append("report verdict disagrees with alert count")
    for e in errs:
        print(f"verify: {e}")
    print("verify: ok" if not errs else f"verify: {len(errs)} problem(s)")
    return 0 if not errs else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline")
    ap.add_argument("--current")
    ap.add_argument("--features")
    ap.add_argument("--thresholds")
    ap.add_argument("--types")
    ap.add_argument("--out-dir")
    ap.add_argument("--verify", metavar="FILE")
    ap.add_argument("--calc", metavar="FN=ARGS", help="ks_sf=<lambda> or chi2_sf=<stat>,<df>")
    a = ap.parse_args(argv)
    if a.calc:
        fn, _, val = a.calc.partition("=")
        try:
            nums = [float(x) for x in val.split(",")]
            if fn == "ks_sf" and len(nums) == 1:
                print(f"{kolmogorov_sf(nums[0]):.12g}")
                return 0
            if fn == "chi2_sf" and len(nums) == 2 and nums[1] >= 1:
                print(f"{chi2_sf(nums[0], int(nums[1])):.12g}")
                return 0
        except ValueError:
            pass
        print(f"error: bad --calc '{a.calc}'", file=sys.stderr)
        return 2
    if a.verify:
        return verify(a.verify)
    try:
        return run(a)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

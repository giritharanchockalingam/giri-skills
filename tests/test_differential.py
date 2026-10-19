"""Differential proof: the statistical skills agree with independent reference implementations.

Every trial generates a fresh random dataset (seeded, so failures reproduce), runs the skill's own script exactly as
the runner would, and compares its numbers with SciPy / statsmodels / NumPy / pandas / the `krippendorff` package —
code the skills never import. The reference libraries are test-only dependencies; the module is skipped without them.

Run: python3 -m pytest -q tests/test_differential.py      (PROOF_TRIALS=N to change trials per check; default 60)
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
from pathlib import Path

import pytest

from conftest import REPO_ROOT, run_script

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")
stats = pytest.importorskip("scipy.stats")
special = pytest.importorskip("scipy.special")
sm_ir = pytest.importorskip("statsmodels.stats.inter_rater")
kripp = pytest.importorskip("krippendorff")

TRIALS = int(os.environ.get("PROOF_TRIALS", "60"))
SK = "skills/ai-platform"


def _write(path: Path, header: list[str], rows: list[list]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


def _p_matches(shown: str, ref: float, tol: float) -> bool:
    """Reports print tiny p-values as '<0.0001'."""
    if shown.startswith("<"):
        return ref < float(shown[1:]) + tol
    return abs(float(shown) - ref) <= tol


def _csv(path: Path) -> list[dict]:
    return list(csv.DictReader(path.open(encoding="utf-8")))


# ---------------------------------------------------------------- A/B test analysis
@pytest.mark.parametrize("seed", range(TRIALS))
def test_ab_binary_matches_scipy(tmp_path, seed):
    rng = random.Random(seed)
    n1, n2 = rng.randint(300, 30000), rng.randint(300, 30000)
    p1 = rng.uniform(0.02, 0.6)
    p2 = min(0.95, max(0.01, p1 + rng.uniform(-0.05, 0.05)))
    x1, x2 = round(n1 * p1), round(n2 * p2)
    res = _write(tmp_path / "r.csv", ["metric", "variant", "users", "conversions"],
                 [["conv", "control", n1, x1], ["conv", "treat", n2, x2]])
    cfg = _write(tmp_path / "c.csv", ["key", "value", "source", "notes"],
                 [["control", "control", "test", ""], ["primary_metric", "conv", "test", ""],
                  ["expected_split", f"{n1}/{n2}", "test", "observed split, so no SRM"]])
    r = run_script(f"{SK}/ab-test-analysis/scripts/ab_test.py", "--results", str(res), "--config", str(cfg), "--out-dir", str(tmp_path / "o"))
    assert r.returncode == 0, r.stdout + r.stderr
    row = next(x for x in _csv(tmp_path / "o" / "ab-results.csv") if x["variant"] == "treat")
    # reference: pooled two-proportion z-test (two-sided) and unpooled Wald CI on the difference
    a, b = x1 / n1, x2 / n2
    pool = (x1 + x2) / (n1 + n2)
    z = (b - a) / math.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n2))
    p_ref = 2 * stats.norm.sf(abs(z))
    se = math.sqrt(a * (1 - a) / n1 + b * (1 - b) / n2)
    zc = stats.norm.ppf(0.975)
    assert float(row["diff"]) == pytest.approx(b - a, abs=1e-6)
    assert float(row["p_value"]) == pytest.approx(p_ref, abs=2e-6)
    assert float(row["ci_low"]) == pytest.approx(b - a - zc * se, abs=2e-6)
    assert float(row["ci_high"]) == pytest.approx(b - a + zc * se, abs=2e-6)


@pytest.mark.parametrize("seed", range(TRIALS))
def test_ab_continuous_welch_matches_scipy(tmp_path, seed):
    g = np.random.default_rng(seed)
    n1, n2 = int(g.integers(30, 3000)), int(g.integers(30, 3000))
    s1 = g.normal(120, g.uniform(5, 60), n1).round(1)
    s2 = g.normal(120 + g.uniform(-8, 8), g.uniform(5, 60), n2).round(1)
    rows = [["t", "control", n1, "", f"{s1.sum():.6f}", f"{(s1 ** 2).sum():.6f}"],
            ["t", "treat", n2, "", f"{s2.sum():.6f}", f"{(s2 ** 2).sum():.6f}"]]
    res = _write(tmp_path / "r.csv", ["metric", "variant", "users", "conversions", "metric_sum", "metric_sumsq"], rows)
    cfg = _write(tmp_path / "c.csv", ["key", "value", "source", "notes"],
                 [["control", "control", "t", ""], ["primary_metric", "t", "t", ""], ["metric_type", "continuous", "t", ""],
                  ["expected_split", f"{n1}/{n2}", "t", ""]])
    r = run_script(f"{SK}/ab-test-analysis/scripts/ab_test.py", "--results", str(res), "--config", str(cfg), "--out-dir", str(tmp_path / "o"))
    assert r.returncode == 0, r.stdout + r.stderr
    row = next(x for x in _csv(tmp_path / "o" / "ab-results.csv") if x["variant"] == "treat")
    ref = stats.ttest_ind(s2, s1, equal_var=False)
    assert float(row["diff"]) == pytest.approx(s2.mean() - s1.mean(), abs=1e-5)
    assert float(row["p_value"]) == pytest.approx(ref.pvalue, abs=2e-6)


# ---------------------------------------------------------------- drift monitor
@pytest.mark.parametrize("seed", range(TRIALS))
def test_drift_ks_and_chi2_match_scipy(tmp_path, seed):
    g = np.random.default_rng(seed)
    nb, nc = int(g.integers(60, 800)), int(g.integers(60, 800))
    xb = g.normal(0, 1, nb).round(4)
    xc = g.normal(g.uniform(-0.4, 0.4), g.uniform(0.8, 1.3), nc).round(4)
    cats = ["a", "b", "c", "d"]
    cb = g.choice(cats, nb, p=[0.4, 0.3, 0.2, 0.1])
    pc = np.array([0.4, 0.3, 0.2, 0.1]) + g.uniform(-0.05, 0.05, 4)
    cc = g.choice(cats, nc, p=pc / pc.sum())
    _write(tmp_path / "b.csv", ["x", "cat"], [[f"{v}", c] for v, c in zip(xb, cb)])
    _write(tmp_path / "c.csv", ["x", "cat"], [[f"{v}", c] for v, c in zip(xc, cc)])
    r = run_script(f"{SK}/drift-monitor/scripts/drift.py", "--baseline", str(tmp_path / "b.csv"), "--current", str(tmp_path / "c.csv"),
                   "--types", "cat=categorical", "--out-dir", str(tmp_path / "o"))
    assert r.returncode in (0, 1), r.stdout + r.stderr
    rows = {x["feature"]: x for x in _csv(tmp_path / "o" / "drift.csv")}
    ks = stats.ks_2samp(xb, xc)
    assert float(rows["x"]["ks_d"]) == pytest.approx(ks.statistic, abs=1e-4)
    # exact two-sample p-value (the skill's method for n*m <= 1e6)
    assert _p_matches(rows["x"]["p_value"], stats.ks_2samp(xb, xc, method="exact").pvalue, 1e-4)
    table = np.array([[np.sum(cb == k) for k in cats], [np.sum(cc == k) for k in cats]])
    table = table[:, table.sum(axis=0) > 0]
    chi = stats.chi2_contingency(table, correction=False)
    assert _p_matches(rows["cat"]["p_value"], chi.pvalue, 1e-4)


# ---------------------------------------------------------------- annotation agreement
@pytest.mark.parametrize("seed", range(TRIALS))
def test_agreement_matches_statsmodels_and_krippendorff(tmp_path, seed):
    g = np.random.default_rng(seed)
    n_items, labels, raters = int(g.integers(15, 120)), ["x", "y", "z", "w"], ["r1", "r2", "r3"]
    truth = g.choice(labels, n_items)
    acc = g.uniform(0.5, 0.95)
    grid = []
    for i, t in enumerate(truth):
        grid.append([t if g.random() < acc else g.choice(labels) for _ in raters])
    rows = [[f"I{i:03d}", raters[j], grid[i][j]] for i in range(n_items) for j in range(3)]
    _write(tmp_path / "l.csv", ["item_id", "annotator", "label"], rows)
    r = run_script(f"{SK}/annotation-agreement/scripts/agreement.py", "--labels", str(tmp_path / "l.csv"), "--out-dir", str(tmp_path / "o"))
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads((tmp_path / "o" / "agreement.json").read_text())
    # Fleiss (statsmodels)
    counts = np.array([[row.count(lab) for lab in labels] for row in grid])
    counts = counts[:, counts.sum(axis=0) > 0]
    assert out["fleiss"]["kappa"] == pytest.approx(sm_ir.fleiss_kappa(counts, method="fleiss"), abs=1e-5)
    # Krippendorff alpha nominal (krippendorff package)
    code = {lab: k for k, lab in enumerate(labels)}
    rel = np.array([[code[grid[i][j]] for i in range(n_items)] for j in range(3)], dtype=float)
    assert out["krippendorff_alpha"] == pytest.approx(kripp.alpha(reliability_data=rel, level_of_measurement="nominal"), abs=1e-5)
    # Cohen per pair (statsmodels)
    for p in out["pairs"]:
        a, b = (raters.index(x) for x in p["pair"].split("|"))
        tab = pd.crosstab(pd.Categorical([grid[i][a] for i in range(n_items)], categories=labels),
                          pd.Categorical([grid[i][b] for i in range(n_items)], categories=labels), dropna=False).values
        assert p["kappa"] == pytest.approx(sm_ir.cohens_kappa(tab).kappa, abs=1e-5)


@pytest.mark.parametrize("seed", range(max(10, TRIALS // 3)))
def test_krippendorff_with_missing_ratings(tmp_path, seed):
    g = np.random.default_rng(1000 + seed)
    n_items, labels, raters = int(g.integers(20, 80)), ["a", "b", "c"], ["r1", "r2", "r3", "r4"]
    rel = np.full((4, n_items), np.nan)
    rows = []
    for i in range(n_items):
        t = g.choice(labels)
        who = g.choice(4, int(g.integers(2, 5)), replace=False)
        for j in who:
            lab = t if g.random() < 0.75 else g.choice(labels)
            rel[j, i] = labels.index(lab)
            rows.append([f"I{i:03d}", raters[j], lab])
    _write(tmp_path / "l.csv", ["item_id", "annotator", "label"], rows)
    r = run_script(f"{SK}/annotation-agreement/scripts/agreement.py", "--labels", str(tmp_path / "l.csv"), "--out-dir", str(tmp_path / "o"))
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads((tmp_path / "o" / "agreement.json").read_text())
    assert out["krippendorff_alpha"] == pytest.approx(kripp.alpha(reliability_data=rel, level_of_measurement="nominal"), abs=1e-5)


# ---------------------------------------------------------------- SLO definition
@pytest.mark.parametrize("seed", range(TRIALS))
def test_slo_percentiles_and_availability_match_numpy(tmp_path, seed):
    g = np.random.default_rng(seed)
    n = int(g.integers(50, 3000))
    lat = g.lognormal(7, 0.5, n).round().astype(int)
    ok = g.random(n) > g.uniform(0, 0.05)
    rows = [[f"2026-09-01T00:00:00Z" if i == 0 else f"2026-09-01T{(i // 3600) % 24:02d}:{(i // 60) % 60:02d}:{i % 60:02d}Z",
             int(lat[i]), "ok" if ok[i] else "error"] for i in range(n)]
    _write(tmp_path / "log.csv", ["timestamp", "latency_ms", "status"], rows)
    r = run_script(f"{SK}/ai-slo-definition/scripts/slo.py", "--log", str(tmp_path / "log.csv"), "--out-dir", str(tmp_path / "o"))
    assert r.returncode in (0, 1), r.stdout + r.stderr
    out = json.loads((tmp_path / "o" / "slo.json").read_text())
    okl = np.sort(lat[ok])
    for p in (50, 95, 99):  # nearest-rank == numpy's inverted_cdf
        assert int(out["summary"][f"p{p}_ms"]) == int(np.percentile(okl, p, method="inverted_cdf")), p
    avail = next(s for s in out["slos"] if s["sli"] == "availability")
    assert float(avail["observed"]) == pytest.approx(ok.mean(), abs=6e-6)


# ---------------------------------------------------------------- FinOps chargeback
@pytest.mark.parametrize("seed", range(max(10, TRIALS // 3)))
def test_finops_totals_reconcile_with_pandas(tmp_path, seed):
    g = np.random.default_rng(seed)
    models = {"m-small": (0.15, 0.60), "m-large": (2.50, 10.00)}
    rows = []
    for d in range(1, 29):
        for team in ("ops", "billing", "support"):
            for model in models:
                if g.random() < 0.7:
                    req = int(g.integers(10, 5000))
                    rows.append([f"2026-09-{d:02d}", team, "chat", model, req, int(req * g.integers(200, 3000)), int(req * g.integers(50, 800))])
    _write(tmp_path / "u.csv", ["date", "team", "feature", "model", "requests", "input_tokens", "output_tokens"], rows)
    _write(tmp_path / "p.csv", ["model", "input_per_1m", "output_per_1m", "effective_from"],
           [[m, f"{a:.2f}", f"{b:.2f}", "2026-01-01"] for m, (a, b) in models.items()])
    r = run_script(f"{SK}/ai-finops-chargeback/scripts/" + next(p.name for p in (REPO_ROOT / SK / "ai-finops-chargeback/scripts").glob("*.py")),
                   "--usage", str(tmp_path / "u.csv"), "--prices", str(tmp_path / "p.csv"), "--out-dir", str(tmp_path / "o"))
    assert r.returncode == 0, r.stdout + r.stderr
    df = pd.DataFrame(rows, columns=["date", "team", "feature", "model", "requests", "inp", "out"])
    df["cost"] = df.apply(lambda x: x.inp / 1e6 * models[x.model][0] + x.out / 1e6 * models[x.model][1], axis=1)
    sb = pd.DataFrame(_csv(tmp_path / "o" / "showback.csv"))
    leaf = sb[(sb["team"].isin(["ops", "billing", "support"])) & (sb["model"].isin(models)) & (sb["feature"] == "chat")]
    assert len(leaf) == df.groupby(["team", "model"]).ngroups
    for (team, model), cost in df.groupby(["team", "model"])["cost"].sum().items():
        got = float(leaf[(leaf.team == team) & (leaf.model == model)]["cost_usd"].iloc[0])
        assert got == pytest.approx(round(cost, 2), abs=0.0051), (team, model)

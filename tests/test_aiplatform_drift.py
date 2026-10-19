"""Tests for ai-platform/drift-monitor/scripts/drift.py (hand-checked statistics)."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/drift-monitor/scripts/drift.py"
FIX = REPO_ROOT / "skills/ai-platform/drift-monitor/evals/fixtures"


def _csv(p: Path, header: list[str], rows: list[list]) -> Path:
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return p


def _run(tmp_path, base_rows, cur_rows, header=("x",), *extra, thresholds: str | None = None):
    b = _csv(tmp_path / "b.csv", list(header), base_rows)
    c = _csv(tmp_path / "c.csv", list(header), cur_rows)
    args = ["--baseline", str(b), "--current", str(c), "--out-dir", str(tmp_path / "out"), *extra]
    if thresholds is not None:
        (tmp_path / "t.csv").write_text(thresholds, encoding="utf-8")
        args += ["--thresholds", str(tmp_path / "t.csv")]
    res = run_script(SCRIPT, *args)
    out = tmp_path / "out" / "drift.csv"
    rows = {r["feature"]: r for r in csv.DictReader(out.open(encoding="utf-8"))} if out.exists() else {}
    return res, rows


def _json(tmp_path) -> dict:
    return json.loads((tmp_path / "out" / "drift.json").read_text(encoding="utf-8"))


def test_categorical_psi_and_chi_square_hand_checked(tmp_path):
    # Baseline A50 B50, current A30 B70 (references/method.md worked example)
    base = [["A"]] * 50 + [["B"]] * 50
    cur = [["A"]] * 30 + [["B"]] * 70
    res, rows = _run(tmp_path, base, cur)
    r = rows["x"]
    psi = (0.3 - 0.5) * math.log(0.6) + (0.7 - 0.5) * math.log(1.4)  # 0.169460
    assert r["type"] == "categorical" and r["psi"] == f"{psi:.4f}" == "0.1695"
    j = _json(tmp_path)["features"][0]
    assert abs(j["chi2"] - 25 / 3) < 1e-9 and j["df"] == 1
    assert abs(j["p_value"] - math.erfc(math.sqrt(25 / 6))) < 1e-10  # 0.003892
    assert r["p_value"] == "0.0039" and r["status"] == "alert" and res.returncode == 1


def test_ks_statistic_and_pvalue_hand_checked(tmp_path):
    # 40 values 1..40 vs 40 values 11..50: ECDF gap max = 10/40 = 0.25
    base = [[i] for i in range(1, 41)]
    cur = [[i] for i in range(11, 51)]
    res, rows = _run(tmp_path, base, cur)
    r = rows["x"]
    assert r["type"] == "numeric" and r["ks_d"] == "0.2500"
    lam = math.sqrt(40 * 40 / 80) * 0.25
    q = 2 * sum((-1) ** (k - 1) * math.exp(-2 * k * k * lam * lam) for k in range(1, 100))
    assert abs(_json(tmp_path)["features"][0]["p_value"] - q) < 1e-9  # ~0.1641


def _calc(spec: str) -> float:
    res = run_script(SCRIPT, "--calc", spec)
    assert res.returncode == 0, res.stderr
    return float(res.stdout.strip())


def test_kolmogorov_and_gamma_known_values():
    assert abs(_calc("ks_sf=1.3581") - 0.05) < 1e-4  # classic 5% critical value
    assert abs(_calc("ks_sf=1.6276") - 0.01) < 1e-4  # classic 1% critical value
    assert _calc("ks_sf=0.1") == 1.0
    assert abs(_calc("chi2_sf=3.841,1") - 0.0500) < 1e-4
    assert abs(_calc("chi2_sf=5.991,2") - math.exp(-5.991 / 2)) < 1e-11  # df=2 closed form
    assert abs(_calc("chi2_sf=11.345,3") - 0.0100) < 1e-4
    assert abs(_calc("chi2_sf=0.5,4") - math.exp(-0.25) * 1.25) < 1e-11  # df=4: e^{-x/2}(1+x/2)
    assert abs(_calc("chi2_sf=100,50") - 3.4549313829848e-05) < 1e-12  # large x: continued fraction
    assert run_script(SCRIPT, "--calc", "chi2_sf=abc").returncode == 2


def test_numeric_psi_deciles_identical_is_zero_and_shift_detected(tmp_path):
    base = [[i] for i in range(100)]
    res, rows = _run(tmp_path, base, base)
    assert rows["x"]["psi"] == "0.0000" and rows["x"]["ks_d"] == "0.0000" and rows["x"]["status"] == "ok"
    # everything in the top decile bin: 0.1 -> 1.0 and nine bins 0.1 -> eps
    cur = [[95]] * 100
    res2, rows2 = _run(tmp_path, base, cur)
    eps = 1e-4
    psi = (1.0 - 0.1) * math.log(1.0 / 0.1) + 9 * (eps - 0.1) * math.log(eps / 0.1)
    assert rows2["x"]["psi"] == f"{psi:.4f}" and rows2["x"]["status"] == "alert" and res2.returncode == 1


def test_unseen_category_gets_own_bin(tmp_path):
    base = [["A"]] * 40
    cur = [["A"]] * 30 + [["Z"]] * 10
    res, rows = _run(tmp_path, base, cur, ("x",), thresholds="metric,warn,alert\npsi,0.1,0.25\np_value,,\n")
    eps = 1e-4
    psi = (0.75 - 1.0) * math.log(0.75) + (0.25 - eps) * math.log(0.25 / eps)
    assert rows["x"]["psi"] == f"{psi:.4f}"
    assert "Categories unseen in the baseline: Z." in (tmp_path / "out" / "drift-report.md").read_text()


def test_insufficient_data_is_not_alert(tmp_path):
    res, rows = _run(tmp_path, [["A"]] * 29, [["B"]] * 29)
    assert rows["x"]["status"] == "insufficient-data" and res.returncode == 0


def test_null_rate_and_type_detection_and_override(tmp_path):
    hdr = ("score", "code")
    base = [[str(i / 100), str(100 + i % 3)] for i in range(40)]
    cur = [["" if i < 8 else str(i / 100), str(100 + i % 3)] for i in range(40)]
    res, rows = _run(tmp_path, base, cur, hdr, "--types", "code=categorical",
                     thresholds="metric,warn,alert\npsi,,\np_value,,\nnull_rate_delta,0.1,0.3\n")
    assert rows["score"]["null_rate_current"] == "0.200" and rows["score"]["n_current"] == "32"
    assert rows["score"]["status"] == "warn"  # delta 0.2 >= 0.1 warn, < 0.3 alert
    assert rows["code"]["type"] == "categorical" and rows["code"]["ks_d"] == ""


def test_numeric_threshold_of_95_percent(tmp_path):
    vals = [[str(i)] for i in range(19)] + [["x"]]  # 95% numeric -> numeric
    res, rows = _run(tmp_path, vals * 2, vals * 2)
    assert rows["x"]["type"] == "numeric" and rows["x"]["n_baseline"] == "38"
    vals2 = [[str(i)] for i in range(18)] + [["x"], ["y"]]  # 90% -> categorical
    res, rows = _run(tmp_path, vals2 * 2, vals2 * 2)
    assert rows["x"]["type"] == "categorical"


def test_default_thresholds_are_tbd_with_owner(tmp_path):
    res, _ = _run(tmp_path, [["A"]] * 40, [["A"]] * 40)
    md = (tmp_path / "out" / "drift-report.md").read_text()
    assert "[TO BE BASELINED — owner: ML engineering lead]" in md
    assert "[TO BE BASELINED — owner: Data owner]" in md
    assert "convention" in md
    for line in md.splitlines():
        if "[TO BE BASELINED" in line:
            assert "— owner: " in line


def test_input_errors_exit_2(tmp_path):
    b = _csv(tmp_path / "b.csv", ["x"], [[1]])
    assert run_script(SCRIPT, "--baseline", str(b), "--out-dir", str(tmp_path / "o")).returncode == 2
    assert run_script(SCRIPT, "--baseline", str(b), "--current", str(tmp_path / "nope.csv"),
                      "--out-dir", str(tmp_path / "o")).returncode == 2
    res = run_script(SCRIPT, "--baseline", str(b), "--current", str(b), "--features", "y",
                     "--out-dir", str(tmp_path / "o"))
    assert res.returncode == 2 and "y" in res.stderr
    (tmp_path / "t.csv").write_text("metric,warn,alert\nkl,0.1,0.2\n", encoding="utf-8")
    res = run_script(SCRIPT, "--baseline", str(b), "--current", str(b), "--thresholds", str(tmp_path / "t.csv"),
                     "--out-dir", str(tmp_path / "o"))
    assert res.returncode == 2 and "kl" in res.stderr


def test_fixture_gate_determinism_and_verify(tmp_path):
    outs = []
    for d in ("a", "b"):
        res = run_script(SCRIPT, "--baseline", str(FIX / "baseline.csv"), "--current", str(FIX / "current-drifted.csv"),
                         "--thresholds", str(FIX / "thresholds.csv"), "--out-dir", str(tmp_path / d))
        assert res.returncode == 1 and "confidence" in res.stderr
        outs.append({f: (tmp_path / d / f).read_bytes() for f in ("drift.csv", "drift-report.md", "drift.json")})
    assert outs[0] == outs[1]
    for f in ("drift.csv", "drift-report.md"):
        assert run_script(SCRIPT, "--verify", str(tmp_path / "a" / f)).returncode == 0
    # tamper: flip a status in the csv -> verify fails
    p = tmp_path / "a" / "drift.csv"
    p.write_text(p.read_text().replace("2.5567,0.5600,<0.0001,0.000,0.000,alert", "2.5567,0.5600,<0.0001,0.000,0.000,ok"))
    assert run_script(SCRIPT, "--verify", str(p)).returncode == 1


def test_no_network_imports():
    src = (REPO_ROOT / SCRIPT).read_text(encoding="utf-8")
    for bad in ("import socket", "import urllib", "import requests", "import subprocess", "urlopen("):
        assert bad not in src

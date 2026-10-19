"""Tests for ai-platform/ab-test-analysis/scripts/ab_test.py (hand-computed expectations)."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from statistics import NormalDist

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ab-test-analysis/scripts/ab_test.py"
FIX = REPO_ROOT / "skills/ai-platform/ab-test-analysis/evals/fixtures"
TBD = "[TO BE BASELINED — owner: Experiment owner]"


def _run(tmp_path, results: str | Path, config: str | None = None, name: str = "o"):
    if isinstance(results, str):
        p = tmp_path / f"{name}-results.csv"
        p.write_text(results, encoding="utf-8")
        results = p
    args = ["--results", str(results), "--out-dir", str(tmp_path / name)]
    if config is not None:
        c = tmp_path / f"{name}-config.csv"
        c.write_text("key,value\n" + config, encoding="utf-8")
        args += ["--config", str(c)]
    res = run_script(SCRIPT, *args)
    out = tmp_path / name
    rows = list(csv.DictReader((out / "ab-results.csv").open(encoding="utf-8"))) if (out / "ab-results.csv").exists() else []
    doc = json.loads((out / "ab.json").read_text(encoding="utf-8")) if (out / "ab.json").exists() else {}
    return res, rows, doc


def _row(rows, metric, variant):
    return next(r for r in rows if r["metric"] == metric and r["variant"] == variant)


def test_two_proportion_z_test_and_wald_ci_by_hand(tmp_path):
    res, rows, _ = _run(tmp_path, "variant,users,conversions\ncontrol,5000,2000\nprompt_v3,5000,2150\n")
    assert res.returncode == 0, res.stderr
    pool = 4150 / 10000
    z = 0.03 / math.sqrt(pool * (1 - pool) * (2 / 5000))
    p = math.erfc(z / math.sqrt(2))
    half = 1.959963984540054 * math.sqrt(0.4 * 0.6 / 5000 + 0.43 * 0.57 / 5000)
    r = _row(rows, "primary", "prompt_v3")
    assert r["p_value"] == f"{p:.6f}" == "0.002332"
    assert r["ci_low"] == f"{0.03 - half:.6f}" and r["ci_high"] == f"{0.03 + half:.6f}"
    assert r["rel_lift"] == "0.0750" and r["significant"] == "yes" and r["p_adj"] == r["p_value"]


def test_welch_df2_matches_closed_form_t_cdf(tmp_path):
    # n=2 per arm, both variances 1 -> SE 1, Welch df exactly 2; t = 1
    # F_2(t) = 1/2 + t / (2 sqrt(2 + t^2))  =>  two-sided p = 1 - 1/sqrt(3)
    res, rows, doc = _run(tmp_path, "variant,users,metric_sum,metric_sumsq\ncontrol,2,0,1\nnew_prompt,2,2,3\n")
    assert res.returncode == 0, res.stderr
    r = _row(rows, "primary", "new_prompt")
    assert r["p_value"] == f"{1 - 1 / math.sqrt(3):.6f}" == "0.422650"
    cmp_ = doc["metrics"][0]["comparisons"]["new_prompt"]
    assert abs(cmp_["df"] - 2.0) < 1e-9 and abs(cmp_["stat"] - 1.0) < 1e-9


def test_welch_df10_reproduces_t_table_critical_value(tmp_path):
    # n=6 per arm, equal variance 3 -> SE 1, df 10; diff = t_{0.975,10} = 2.228139 -> p = 0.05, CI low = 0
    t = 2.228138852
    s = 6 * t
    sumsq = 5 * 3 + s * s / 6
    res, rows, doc = _run(tmp_path, f"variant,users,metric_sum,metric_sumsq\ncontrol,6,0,15\nb,6,{s!r},{sumsq!r}\n")
    r = _row(rows, "primary", "b")
    assert r["p_value"] == "0.050000"
    assert abs(float(r["ci_low"])) < 2e-6
    assert abs(doc["metrics"][0]["comparisons"]["b"]["df"] - 10.0) < 1e-9


def test_srm_chi_square_matches_closed_forms_and_gates(tmp_path):
    # df 1: p = erfc(sqrt(chi2/2)); chi2 = 2 * 300^2 / 10300
    res, rows, doc = _run(tmp_path, (FIX / "results-srm.csv"))
    chi2 = 2 * 300 ** 2 / 10300
    assert res.returncode == 1 and "SRM detected" in res.stderr
    assert doc["srm"]["chi2"] == round(chi2, 4) and math.isclose(doc["srm"]["p_value"], math.erfc(math.sqrt(chi2 / 2)), rel_tol=1e-8)
    assert doc["overall"]["decision"] == "untrustworthy"
    assert (tmp_path / "o" / "ab-report.md").read_text().count("void: SRM detected") == 2
    # df 2: p = exp(-chi2/2); 3 arms at 1/1/1 with 1000/1000/1090 -> no SRM at 0.001
    res2, _, doc2 = _run(tmp_path, "variant,users,conversions\nA,1000,10\nB,1000,10\nC,1090,10\n",
                         "control,A\n", name="o2")
    e = 3090 / 3
    chi2b = 2 * (1000 - e) ** 2 / e + (1090 - e) ** 2 / e
    assert res2.returncode == 0 and math.isclose(doc2["srm"]["p_value"], math.exp(-chi2b / 2), rel_tol=1e-8)


def test_holm_power_and_sample_size_on_fixture(tmp_path):
    res, rows, doc = _run(tmp_path, FIX / "results-agg.csv",
                          (FIX / "config.csv").read_text().split("\n", 2)[2], name="cfg")
    assert res.returncode == 0, res.stderr
    v3, ms = _row(rows, "resolved", "prompt_v3"), _row(rows, "resolved", "model_swap")
    assert float(v3["p_adj"]) == round(2 * float(v3["p_value"]), 6) == 0.004664   # Holm: 2 x smallest
    assert ms["p_adj"] == ms["p_value"]                                            # max(p, previous) = p
    nd = NormalDist()
    za, zb = nd.inv_cdf(0.975), nd.inv_cdf(0.8)
    n_needed = math.ceil((za + zb) ** 2 * (0.4 * 0.6 + 0.42 * 0.58) / 0.02 ** 2)
    pw = doc["metrics"][0]["power"]["prompt_v3"]
    assert pw["n_per_arm_needed"] == n_needed == 9490
    se = math.sqrt(0.4 * 0.6 / 5000 + 0.42 * 0.58 / 5000)
    assert abs(pw["achieved_power"] - (nd.cdf(0.02 / se - za) + nd.cdf(-0.02 / se - za))) < 1e-7
    assert doc["overall"] == {"decision": "ship", "variant": "prompt_v3",
                              "reason": "primary metric significantly better and no guardrail significantly worse"}
    assert doc["decisions"]["model_swap"]["decision"] == "inconclusive"


def test_decision_rule_guardrail_breach_and_worse(tmp_path):
    data = ("metric,variant,users,conversions\nresolved,control,5000,2000\nresolved,b,5000,2200\n"
            "escalated,control,5000,400\nescalated,b,5000,500\n")
    res, _, doc = _run(tmp_path, data, "guardrails,escalated:lower_better\n")
    assert doc["decisions"]["b"]["decision"] == "don't ship" and doc["decisions"]["b"]["guardrail_breaches"] == ["escalated"]
    res2, _, doc2 = _run(tmp_path, data, "guardrails,escalated\n", name="nodir")
    assert doc2["decisions"]["b"]["decision"] == "inconclusive" and TBD in doc2["decisions"]["b"]["reason"]
    res3, _, doc3 = _run(tmp_path, "variant,users,conversions\ncontrol,5000,2200\nb,5000,2000\n", name="worse")
    assert doc3["overall"]["decision"] == "don't ship"
    res4, _, doc4 = _run(tmp_path, "variant,users,conversions\ncontrol,5000,2200\nb,5000,2000\n",
                         "direction,lower_better\n", name="lower")
    assert doc4["overall"] == {"decision": "ship", "variant": "b", "reason":
                               "primary metric significantly better and no guardrail significantly worse"}


def test_missing_mde_and_guardrails_are_tbd_with_owner(tmp_path):
    res, _, doc = _run(tmp_path, "variant,users,conversions\ncontrol,5000,2000\nb,5000,2010\n")
    md = (tmp_path / "o" / "ab-report.md").read_text(encoding="utf-8")
    assert res.returncode == 0
    assert f"| mde | {TBD} | not supplied |" in md and f"No guardrail metrics declared: {TBD}" in md
    assert "| alpha | 0.05 | default |" in md and "| control | control | default |" in md
    for line in md.splitlines():
        if "[TO BE BASELINED" in line:
            assert "— owner: Experiment owner]" in line
    assert doc["metrics"][0]["power"]["b"]["n_per_arm_needed"] is None


def test_unit_level_matches_aggregated_and_relative_mde(tmp_path):
    lines = ["variant,unit_id,converted"]
    for v, n, c in (("control", 200, 80), ("b", 200, 100)):
        lines += [f"{v},{v}-{i},{1 if i < c else 0}" for i in range(n)]
    res, rows, doc = _run(tmp_path, "\n".join(lines) + "\n", "mde,10%\n")
    res2, rows2, _ = _run(tmp_path, "variant,users,conversions\ncontrol,200,80\nb,200,100\n", "mde,10%\n", name="agg")
    assert res.returncode == 0, res.stderr
    strip = lambda rs: [{k: v for k, v in r.items() if k != "metric"} for r in rs]  # noqa: E731
    assert strip(rows) == strip(rows2)
    assert abs(doc["metrics"][0]["power"]["b"]["mde_abs"] - 0.04) < 1e-12   # 10% of 0.40


def test_malformed_inputs_exit_2(tmp_path):
    assert run_script(SCRIPT, "--out-dir", str(tmp_path / "x")).returncode == 2
    assert run_script(SCRIPT, "--results", str(tmp_path / "nope.csv"), "--out-dir", str(tmp_path / "x")).returncode == 2
    bad = {
        "header": ("a,b\n1,2\n", None),
        "conv>users": ("variant,users,conversions\ncontrol,10,11\nb,10,1\n", None),
        "one variant": ("variant,users,conversions\ncontrol,10,1\n", None),
        "unknown key": ("variant,users,conversions\ncontrol,10,1\nb,10,2\n", "alhpa,0.05\n"),
        "split parts": ("variant,users,conversions\ncontrol,10,1\nb,10,2\n", "expected_split,50/25/25\n"),
        "dup unit": ("variant,unit_id,converted\ncontrol,u1,1\nb,u1,0\n", None),
        "empty": ("", None),
    }
    for name, (data, cfg) in bad.items():
        res, _, _ = _run(tmp_path, data, cfg, name=name.replace(" ", "_").replace(">", "_"))
        assert res.returncode == 2, name
        assert res.stderr.startswith("error:"), name


def test_deterministic_and_verify_mode(tmp_path):
    cfg = (FIX / "config.csv").read_text().split("\n", 2)[2]
    _run(tmp_path, FIX / "results-agg.csv", cfg, name="a")
    _run(tmp_path, FIX / "results-agg.csv", cfg, name="b")
    for f in ("ab-results.csv", "ab-report.md", "ab.json"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes()
        ok = run_script(SCRIPT, "--verify", str(tmp_path / "a" / f), "--results", str(FIX / "results-agg.csv"))
        assert ok.returncode == 0, ok.stdout
    rep = tmp_path / "a" / "ab-report.md"
    rep.write_text(rep.read_text().replace("0.004664", "0.000100"), encoding="utf-8")
    bad = run_script(SCRIPT, "--verify", str(rep), "--results", str(FIX / "results-agg.csv"))
    assert bad.returncode == 1 and "does not match" in bad.stdout


def test_no_network_imports():
    src = (REPO_ROOT / SCRIPT).read_text(encoding="utf-8")
    for bad in ("import socket", "import urllib", "import requests", "import subprocess", "urlopen("):
        assert bad not in src

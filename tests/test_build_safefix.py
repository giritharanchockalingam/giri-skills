"""Tests for build/safe-fix/scripts/safefix.py."""
from __future__ import annotations

import json
import shutil

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/safe-fix/scripts/safefix.py"
FX = REPO_ROOT / "skills/build/safe-fix/evals/fixtures"
CMD = "python3 -m pytest -q -p no:cacheprovider"


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0
    assert run_script(SCRIPT, "baseline", "--help").returncode == 0


def test_baseline_records_counts_and_exit(tmp_path):
    out = tmp_path / "baseline.json"
    r = run_script(SCRIPT, "baseline", "--target", str(FX / "repo-green"), "--cmd", CMD, "--out", str(out))
    assert r.returncode == 0, r.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["mode"] == "baseline" and data["exit_code"] == 0
    assert data["counts"]["passed"] == 2
    assert "2 passed" in data["stdout"]


def test_verify_no_collateral_exits_0(tmp_path):
    b = tmp_path / "baseline.json"
    run_script(SCRIPT, "baseline", "--target", str(FX / "repo-green"), "--cmd", CMD, "--out", str(b))
    v = tmp_path / "verify.json"
    r = run_script(SCRIPT, "verify", "--target", str(FX / "repo-green"), "--cmd", CMD, "--out", str(v))  # default baseline beside --out
    assert r.returncode == 0, r.stderr
    data = json.loads(v.read_text(encoding="utf-8"))
    assert data["ok"] is True and data["collateral"] == [] and data["fixed"] == []


def test_verify_detects_collateral_exits_1(tmp_path):
    v = tmp_path / "verify.json"
    r = run_script(SCRIPT, "verify", "--target", str(FX / "repo-collateral"), "--cmd", CMD,
                   "--baseline", str(FX / "baseline-green.json"), "--out", str(v))
    assert r.returncode == 1
    assert "COLLATERAL" in r.stderr and "test_calc.py::test_multiply" in r.stderr
    data = json.loads(v.read_text(encoding="utf-8"))
    assert data["ok"] is False and data["collateral"] == ["test_calc.py::test_multiply"]


def test_verify_reports_fixed_tests(tmp_path):
    # baseline on the broken repo, verify on the green one -> test_multiply is "fixed"
    b = tmp_path / "b.json"
    run_script(SCRIPT, "baseline", "--target", str(FX / "repo-collateral"), "--cmd", CMD, "--out", str(b))
    v = tmp_path / "v.json"
    r = run_script(SCRIPT, "verify", "--target", str(FX / "repo-green"), "--cmd", CMD, "--baseline", str(b), "--out", str(v))
    assert r.returncode == 0, r.stderr
    data = json.loads(v.read_text(encoding="utf-8"))
    assert data["fixed"] == ["test_calc.py::test_multiply"] and data["collateral"] == []


def test_verbose_pytest_names_every_test(tmp_path):
    out = tmp_path / "b.json"
    r = run_script(SCRIPT, "baseline", "--target", str(FX / "repo-green"), "--cmd", CMD.replace("-q", "-v"), "--out", str(out))
    assert r.returncode == 0, r.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["parser"] == "pytest"
    assert set(data["tests"]) == {"test_calc.py::test_add", "test_calc.py::test_multiply"}


def test_generic_count_drop_is_collateral(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(FX / "repo-green", repo)
    baseline = {"cmd": "x", "exit_code": 0, "tests": {}, "counts": {"passed": 3, "failed": 0, "skipped": None}}
    b = tmp_path / "b.json"
    b.write_text(json.dumps(baseline), encoding="utf-8")
    v = tmp_path / "v.json"
    r = run_script(SCRIPT, "verify", "--target", str(repo), "--cmd", CMD, "--baseline", str(b), "--out", str(v))
    assert r.returncode == 1
    assert "passed count dropped from 3 to 2" in json.loads(v.read_text(encoding="utf-8"))["collateral"][0]


def test_bad_input_exits_1(tmp_path):
    assert run_script(SCRIPT, "baseline", "--target", str(tmp_path / "nope"), "--cmd", CMD, "--out", str(tmp_path / "b.json")).returncode == 1
    assert run_script(SCRIPT, "verify", "--target", str(FX / "repo-green"), "--cmd", CMD,
                      "--baseline", str(tmp_path / "missing.json"), "--out", str(tmp_path / "v.json")).returncode == 1
    r = run_script(SCRIPT, "baseline", "--target", str(FX / "repo-green"), "--cmd", "no-such-runner-xyz", "--out", str(tmp_path / "b.json"))
    assert r.returncode == 1 and "cannot run" in r.stderr

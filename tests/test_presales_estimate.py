"""Tests for presales/effort-estimator/scripts/estimate.py."""
from __future__ import annotations

import json
from pathlib import Path

from conftest import copy_asset, run_script

SCRIPT = "skills/presales/effort-estimator/scripts/estimate.py"
WBS = "skills/presales/effort-estimator/assets/wbs-template.csv"
RATES = "skills/presales/effort-estimator/assets/rate-card.example.csv"

EXPECTED_JSON_KEYS = {"total", "phases", "basis_mix", "unresolved", "cost"}


def _estimate(tmp_path: Path, *extra: str):
    wbs = copy_asset(WBS, tmp_path)
    return run_script(SCRIPT, "--iterations", "2000", "--seed", "42", *extra, str(wbs))


def test_help_exits_zero():
    r = run_script(SCRIPT, "--help")
    assert r.returncode == 0


def test_happy_path_json(tmp_path):
    r = _estimate(tmp_path, "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert EXPECTED_JSON_KEYS <= set(data)
    assert data["total"]["50"] > 0


def test_seed_is_deterministic(tmp_path):
    a = _estimate(tmp_path, "--json")
    b = _estimate(tmp_path, "--json")
    assert a.returncode == 0 and b.returncode == 0
    assert json.loads(a.stdout)["total"] == json.loads(b.stdout)["total"]


def test_with_rate_card(tmp_path):
    wbs = copy_asset(WBS, tmp_path)
    rates = copy_asset(RATES, tmp_path)
    r = run_script(
        SCRIPT, "--iterations", "1000", "--seed", "7", "--json",
        "--rates", str(rates), str(wbs),
    )
    assert r.returncode == 0, r.stderr
    assert "cost" in json.loads(r.stdout)


def test_missing_wbs_file(tmp_path):
    r = run_script(SCRIPT, "--iterations", "100", str(tmp_path / "nope.csv"))
    assert r.returncode == 2


def test_missing_required_columns(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("task_id,phase,role\n1,Phase 1,Engineer\n", encoding="utf-8")
    r = run_script(SCRIPT, "--iterations", "100", str(bad))
    assert r.returncode == 2

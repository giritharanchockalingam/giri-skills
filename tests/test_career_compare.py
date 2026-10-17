"""Tests for career/offer-evaluator/scripts/compare.py."""
from __future__ import annotations

import json
from pathlib import Path

from conftest import copy_asset, run_script

SCRIPT = "skills/career/offer-evaluator/scripts/compare.py"
CSV = "skills/career/offer-evaluator/assets/offer-comparison.csv"


def test_help_exits_zero():
    r = run_script(SCRIPT, "--help")
    assert r.returncode == 0


def test_happy_path_compares_offers(tmp_path):
    f = copy_asset(CSV, tmp_path)
    r = run_script(SCRIPT, "--file", str(f))
    assert r.returncode == 0, r.stderr
    assert "annualized_total" in r.stdout


def test_json_output(tmp_path):
    f = copy_asset(CSV, tmp_path)
    r = run_script(SCRIPT, "--file", str(f), "--json")
    assert r.returncode == 0, r.stderr
    json.loads(r.stdout)  # must be parseable JSON


def test_missing_file(tmp_path):
    r = run_script(SCRIPT, "--file", str(tmp_path / "nope.csv"))
    assert r.returncode == 2


def test_no_rows_rejected(tmp_path):
    example = copy_asset(CSV, tmp_path)
    header = example.read_text(encoding="utf-8").splitlines()[0]
    empty = tmp_path / "empty.csv"
    empty.write_text(header + "\n", encoding="utf-8")
    r = run_script(SCRIPT, "--file", str(empty))
    assert r.returncode == 2

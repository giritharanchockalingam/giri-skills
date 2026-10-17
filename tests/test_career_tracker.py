"""Tests for career/application-tracker/scripts/tracker.py."""
from __future__ import annotations

from pathlib import Path

from conftest import copy_asset, run_script

SCRIPT = "skills/career/application-tracker/scripts/tracker.py"
CSV = "skills/career/application-tracker/assets/tracker.csv"


def test_help_exits_zero():
    r = run_script(SCRIPT, "--help")
    assert r.returncode == 0


def test_add_and_list(tmp_path):
    f = copy_asset(CSV, tmp_path)
    r = run_script(
        SCRIPT, "add", "--file", str(f),
        "--company", "Initech", "--role", "Engineer",
        "--stage", "Applied", "--date", "2026-10-17",
    )
    assert r.returncode == 0, r.stderr
    assert "added" in r.stdout
    r2 = run_script(SCRIPT, "list", "--file", str(f))
    assert r2.returncode == 0, r2.stderr
    assert "Initech" in r2.stdout


def test_bad_date_rejected(tmp_path):
    f = copy_asset(CSV, tmp_path)
    r = run_script(
        SCRIPT, "add", "--file", str(f),
        "--company", "X", "--role", "Y",
        "--stage", "Applied", "--date", "17-10-2026",
    )
    assert r.returncode == 1


def test_header_mismatch_rejected(tmp_path):
    f = tmp_path / "tracker.csv"
    f.write_text("id,company\n1,Acme\n", encoding="utf-8")
    r = run_script(SCRIPT, "list", "--file", str(f))
    assert r.returncode == 1


def test_update_unknown_id(tmp_path):
    f = copy_asset(CSV, tmp_path)
    r = run_script(
        SCRIPT, "update", "--file", str(f), "--id", "9999", "--stage", "Offer"
    )
    assert r.returncode == 1

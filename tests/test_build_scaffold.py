"""Tests for build/project-bootstrap/scripts/scaffold.py."""
from __future__ import annotations

from pathlib import Path

from conftest import run_script

SCRIPT = "skills/build/project-bootstrap/scripts/scaffold.py"


def test_help_exits_zero():
    r = run_script(SCRIPT, "--help")
    assert r.returncode == 0


def test_dry_run_writes_nothing(tmp_path):
    target = tmp_path / "proj"
    r = run_script(SCRIPT, "--target", str(target), "--name", "demo-app", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "would write" in r.stdout
    assert not target.exists() or not any(target.rglob("*"))


def test_happy_path_scaffolds_project(tmp_path):
    target = tmp_path / "proj"
    r = run_script(SCRIPT, "--target", str(target), "--name", "demo-app")
    assert r.returncode == 0, r.stderr
    spec = target / "docs" / "SPEC.md"
    assert spec.exists()
    assert "demo-app" in spec.read_text(encoding="utf-8")


def test_idempotent_never_overwrites(tmp_path):
    target = tmp_path / "proj"
    r1 = run_script(SCRIPT, "--target", str(target), "--name", "demo-app")
    assert r1.returncode == 0, r1.stderr
    spec = target / "docs" / "SPEC.md"
    spec.write_text("USER EDIT - must survive", encoding="utf-8")
    r2 = run_script(SCRIPT, "--target", str(target), "--name", "demo-app")
    assert r2.returncode == 0, r2.stderr
    assert spec.read_text(encoding="utf-8") == "USER EDIT - must survive"


def test_missing_name(tmp_path):
    r = run_script(SCRIPT, "--target", str(tmp_path / "proj"))
    assert r.returncode == 2

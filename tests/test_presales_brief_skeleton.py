"""Tests for presales/client-research-brief/scripts/brief_skeleton.py."""
from __future__ import annotations

from pathlib import Path

from conftest import run_script

SCRIPT = "skills/presales/client-research-brief/scripts/brief_skeleton.py"

NOTES = """# Acme Corp overview
Acme Corp is a Fortune 500 manufacturer of industrial pumps.
https://example.com/news/acme-expansion

## Leadership
Jane Doe became CEO in 2024.

## Recent news
Acme announced a new plant in Ohio.
"""


def _notes(tmp_path: Path, text: str = NOTES) -> Path:
    p = tmp_path / "notes.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_help_exits_zero():
    r = run_script(SCRIPT, "--help")
    assert r.returncode == 0


def test_happy_path_builds_skeleton(tmp_path):
    notes = _notes(tmp_path)
    r = run_script(SCRIPT, "--notes", str(notes), "--company", "Acme Corp")
    assert r.returncode == 0, r.stderr
    assert "Acme Corp" in r.stdout
    assert "## " in r.stdout  # markdown sections emitted


def test_out_file(tmp_path):
    notes = _notes(tmp_path)
    out = tmp_path / "brief.md"
    r = run_script(
        SCRIPT, "--notes", str(notes), "--company", "Acme Corp", "--out", str(out)
    )
    assert r.returncode == 0, r.stderr
    assert out.exists()
    assert "Acme Corp" in out.read_text(encoding="utf-8")


def test_missing_notes_file(tmp_path):
    r = run_script(
        SCRIPT, "--notes", str(tmp_path / "nope.md"), "--company", "Acme Corp"
    )
    assert r.returncode == 2


def test_empty_notes_file(tmp_path):
    notes = _notes(tmp_path, "")
    r = run_script(SCRIPT, "--notes", str(notes), "--company", "Acme Corp")
    assert r.returncode == 2

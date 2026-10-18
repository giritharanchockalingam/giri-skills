"""Tests for presales/discovery-interview/scripts/synthesize.py."""
from __future__ import annotations

import csv
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/presales/discovery-interview/scripts/synthesize.py"
FX = REPO_ROOT / "skills/presales/discovery-interview/evals/fixtures"


def run(tmp_path, notes):
    pm, fc = tmp_path / "pm.csv", tmp_path / "fc.md"
    return run_script(SCRIPT, str(notes), "--pain-matrix", str(pm), "--five-closes", str(fc)), pm, fc


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_notes_to_matrix_and_closes(tmp_path):
    r, pm, fc = run(tmp_path, FX / "notes.md")
    assert r.returncode == 0, r.stderr
    rows = list(csv.DictReader(pm.open(encoding="utf-8")))
    assert {"pain", "impact", "urgency", "evidence", "owner"} <= set(rows[0])
    assert len(rows) == 4 and all(r_["evidence"] for r_ in rows)
    cost = next(r_ for r_ in rows if "$1.4M" in r_["pain"])
    assert cost["impact"] == "H" and cost["owner"] == "CTO" and cost["evidence"].startswith('CTO: "')
    text = fc.read_text(encoding="utf-8")
    assert "## Five closes" in text
    assert "| Decision owner | \"Maria Chen (CTO) signs off" in text
    assert "| Incumbents / alternatives | TBD — owner: ___ |" in text
    assert "Captured 3 of 5 closes" in text
    assert "office move" in text.split("## Parked")[1]


def test_thin_notes_do_not_infer(tmp_path):
    r, pm, fc = run(tmp_path, FX / "notes-thin.md")
    assert r.returncode == 0, r.stderr
    text = fc.read_text(encoding="utf-8")
    assert text.count("TBD — owner: ___") == 5 and "Captured 0 of 5" in text
    rows = list(csv.DictReader(pm.open(encoding="utf-8")))
    assert len(rows) == 1 and rows[0]["impact"] == "TBD"


def test_bad_input_exits_1(tmp_path):
    assert run(tmp_path, tmp_path / "missing.md")[0].returncode == 1
    empty = tmp_path / "e.md"
    empty.write_text("# title only\n\n", encoding="utf-8")
    assert run(tmp_path, empty)[0].returncode == 1

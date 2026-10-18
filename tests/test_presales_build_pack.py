"""Tests for presales/discovery-interview/scripts/build_pack.py."""
from __future__ import annotations

from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/presales/discovery-interview/scripts/build_pack.py"
BANKS = REPO_ROOT / "skills/presales/discovery-interview/references/question-banks"


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_retail_pack_budget_and_filter(tmp_path):
    out, fc, pm = tmp_path / "pack.md", tmp_path / "fc.md", tmp_path / "pm.csv"
    r = run_script(SCRIPT, "--vertical", "retail", "--personas", "CIO,VP Digital", "--minutes", "45",
                   "--banks", str(BANKS), "--out", str(out), "--five-closes", str(fc), "--pain-matrix", str(pm))
    assert r.returncode == 0, r.stderr
    text = out.read_text(encoding="utf-8")
    assert "## Time budget (45 min; 20% reserved for their questions)" in text
    assert "| Their questions (reserved) | 9 |" in text and "| Five closes | 10 |" in text
    assert "| **Total** | **45** |" in text
    plan = [ln for ln in text.splitlines() if ln.startswith("| ") and "| R" in ln and "| H? |" in ln]
    assert 5 <= len(plan) <= 8
    assert all(("CIO" in ln or "VP Digital" in ln) for ln in plan)   # persona filter
    assert "| Decision owner |" in text and "## Five closes" in text
    assert "## Branches" in text and "## Pre-reads to request" in text
    assert "| Decision owner | TBD — owner: ___ |" in fc.read_text(encoding="utf-8")
    assert pm.read_text(encoding="utf-8") == "pain,impact,urgency,evidence,owner\n"


def test_every_vertical_builds(tmp_path):
    for v in ("edtech", "retail", "manufacturing", "travel"):
        r = run_script(SCRIPT, "--vertical", v, "--personas", "CIO", "--minutes", "60", "--banks", str(BANKS),
                       "--out", str(tmp_path / f"{v}.md"))
        assert r.returncode == 0, (v, r.stderr)


def test_bad_input_exits_1(tmp_path):
    out = str(tmp_path / "p.md")
    assert run_script(SCRIPT, "--vertical", "banking", "--personas", "CIO", "--minutes", "45", "--out", out).returncode != 0
    r = run_script(SCRIPT, "--vertical", "retail", "--personas", "Astronaut", "--minutes", "45", "--banks", str(BANKS), "--out", out)
    assert r.returncode == 1 and "bank personas" in r.stderr
    assert run_script(SCRIPT, "--vertical", "retail", "--personas", "CIO", "--minutes", "5", "--banks", str(BANKS), "--out", out).returncode == 1
    assert run_script(SCRIPT, "--vertical", "retail", "--personas", "CIO", "--minutes", "45", "--banks", str(tmp_path), "--out", out).returncode == 1

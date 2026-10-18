"""Tests for presales/orals-prep/scripts/orals.py."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/presales/orals-prep/scripts/orals.py"
SK = REPO_ROOT / "skills/presales/orals-prep"
FX = SK / "evals/fixtures"
BANK = SK / "references/question-bank-and-red-team.md"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import check_output  # noqa: E402


def run(tmp_path, proposal, minutes="60", speakers="Giri,Priya,Alex"):
    s, r_, q = tmp_path / "script.md", tmp_path / "reg.csv", tmp_path / "q.md"
    r = run_script(SCRIPT, str(proposal), "--minutes", minutes, "--speakers", speakers, "--question-bank", str(BANK),
                   "--script", str(s), "--registry", str(r_), "--questions", str(q))
    return r, s, r_, q


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_timed_script_registry_questions(tmp_path):
    r, s, reg, q = run(tmp_path, FX / "proposal.md")
    assert r.returncode == 0, r.stderr
    text = s.read_text(encoding="utf-8")
    assert "Format: 60 min total · 42:00 presentation · 18:00 Q&A" in text
    rows = [ln for ln in text.split("## Timed script")[1].split("## Airtime")[0].splitlines() if ln.startswith("| 0") or ln[:1] == "|" and ln[2:3].isdigit()]
    assert rows[0].startswith("| 0:00 | 1:30 | Opening | Giri |")
    assert "| Close | Alex | last |" in text and "| Q&A | all" in text
    assert "| 1:30 | 3:00 | Executive summary | Giri |" in text and "| Scope and deliverables | Priya |" in text   # round-robin
    # timed segments are contiguous and end at the slot
    times = [ln.split("|")[1:3] for ln in text.splitlines() if ln.startswith("| ") and ":" in ln.split("|")[1]]
    assert all(times[i][1].strip() == times[i + 1][0].strip() for i in range(len(times) - 1))
    assert times[-1][1].strip() == "60:00"
    assert check_output.run_check(f"numbers_trace_to:{reg}", str(s), mode="real")["pass"]
    regs = list(csv.DictReader(reg.open(encoding="utf-8")))
    assert {"number", "section", "context"} <= set(regs[0])
    assert ("180,000", "Pricing") in {(x["number"], x["section"]) for x in regs}
    assert not any(x["number"] == "2026" for x in regs)               # dates are not numbers
    assert "|" not in "".join(x["context"] for x in regs)
    qt = q.read_text(encoding="utf-8")
    assert "What is the biggest risk to this program" in qt
    assert 'What if "118 interfaces in scope per inventory export" is wrong?' in qt


def test_thin_proposal_markers_become_questions(tmp_path):
    r, s, reg, q = run(tmp_path, FX / "proposal-thin.md", "30", "Giri")
    assert r.returncode == 0, r.stderr
    assert "What is the number for:" in q.read_text(encoding="utf-8")
    text = s.read_text(encoding="utf-8")
    assert "[TO BE BASELINED — owner: ___]" in text
    assert check_output.run_check(f"numbers_trace_to:{reg}", str(s), mode="real")["pass"]


def test_bad_input_exits_1(tmp_path):
    assert run(tmp_path, tmp_path / "missing.md")[0].returncode == 1
    assert run(tmp_path, FX / "proposal.md", "5")[0].returncode == 1
    assert run(tmp_path, FX / "proposal.md", "60", " , ")[0].returncode == 1
    nosec = tmp_path / "n.md"
    nosec.write_text("# Title\njust text\n", encoding="utf-8")
    r = run(tmp_path, nosec)[0]
    assert r.returncode == 1 and "sections" in r.stderr

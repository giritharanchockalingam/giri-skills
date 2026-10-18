"""Tests for presales/rfp-compliance-matrix/scripts/score_matrix.py."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/presales/rfp-compliance-matrix/scripts/score_matrix.py"
FX = REPO_ROOT / "skills/presales/rfp-compliance-matrix/evals/fixtures"

REQS = (
    "req_id,client_id,section,page,text,mdo_hint,keyword,source_file\n"
    "REQ-001,3.1,Technical,1,The Supplier shall migrate all integrations to an API gateway.,M,shall,rfp.md\n"
    "REQ-002,3.2,Technical,1,The Supplier should provide automated regression testing.,D,should,rfp.md\n"
    "REQ-003,4.1,Delivery,2,The Supplier shall complete the migration within twelve months.,M,shall,rfp.md\n"
    "REQ-004,3.3,Technical,1,The solution must support mutual TLS.,M,must,rfp.md\n"
)
CAPS = (
    "capability_id,keywords,status,evidence,owner,gap_condition,mitigation,category\n"
    "CAP-01,migrate||integrations||gateway,C,Accelerator MF-1,Priya,,,TEC\n"
    "CAP-02,regression testing,P,,Lena,REST only,custom-build,TEC\n"
    "CAP-03,mutual tls,C,,Daniel,,,SEC\n"
)


def _files(tmp_path: Path):
    r = tmp_path / "reqs.csv"; r.write_text(REQS, encoding="utf-8")
    c = tmp_path / "caps.csv"; c.write_text(CAPS, encoding="utf-8")
    return r, c


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_scores_matrix_gaps_and_summary(tmp_path):
    r, c = _files(tmp_path)
    out, gaps, summ = tmp_path / "m.csv", tmp_path / "g.md", tmp_path / "s.json"
    res = run_script(SCRIPT, str(r), "--capabilities", str(c), "--out", str(out),
                     "--gaps", str(gaps), "--summary", str(summ))
    assert res.returncode == 0, res.stderr
    rows = {row["req_id"]: row for row in csv.DictReader(out.open(encoding="utf-8"))}
    assert rows["REQ-001"]["compliance"] == "C" and rows["REQ-001"]["owner"] == "Priya"
    assert rows["REQ-002"]["compliance"] == "P" and rows["REQ-002"]["mitigation"] == "custom-build"
    assert rows["REQ-003"]["compliance"] == "Q" and rows["REQ-003"]["clarification_id"] == "CQ-001"
    # C with empty evidence is downgraded to P (scoring §1)
    assert rows["REQ-004"]["compliance"] == "P" and "downgraded" in rows["REQ-004"]["gap_condition"]
    text = gaps.read_text(encoding="utf-8")
    assert "## Bottom line" in text and "## Clarification questions" in text and "CQ-001" in text
    s = json.loads(summ.read_text(encoding="utf-8"))
    assert s["requirements"] == 4 and s["gate"]["mandatory_N"] == 0
    assert "provisional" in s["gate"]["verdict"]
    assert s["gate"]["open_gate_tests"]["deadline_feasibility"].startswith("[TO BE BASELINED")


def test_fixture_runs(tmp_path):
    reqs = tmp_path / "reqs.csv"
    ext = run_script("skills/presales/rfp-compliance-matrix/scripts/extract_requirements.py",
                     str(FX / "rfp.md"), "--out", str(reqs))
    assert ext.returncode == 0, ext.stderr
    res = run_script(SCRIPT, str(reqs), "--capabilities", str(FX / "capabilities.csv"),
                     "--out", str(tmp_path / "m.csv"))
    assert res.returncode == 0, res.stderr


def test_bad_input_exits_1(tmp_path):
    r, c = _files(tmp_path)
    assert run_script(SCRIPT, str(tmp_path / "nope.csv"), "--capabilities", str(c),
                      "--out", str(tmp_path / "m.csv")).returncode == 1
    bad = tmp_path / "bad.csv"; bad.write_text("a,b\n1,2\n", encoding="utf-8")
    res = run_script(SCRIPT, str(r), "--capabilities", str(bad), "--out", str(tmp_path / "m.csv"))
    assert res.returncode == 1 and "missing columns" in res.stderr

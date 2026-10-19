"""presales/rfp-compliance-matrix: --previous matrix carry-over (addendum / re-bid)."""
from __future__ import annotations

import csv
import json

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/presales/rfp-compliance-matrix"
FX = SK / "evals/fixtures"


def run(tmp_path, *extra):
    req = tmp_path / "req.csv"
    run_script(SK / "scripts/extract_requirements.py", str(FX / "rfp.md"), "--out", str(req), "--min-words", "4")
    m, g, s = tmp_path / "m.csv", tmp_path / "g.md", tmp_path / "s.json"
    r = run_script(SK / "scripts/score_matrix.py", str(req), "--capabilities", str(FX / "capabilities.csv"),
                   "--out", str(m), "--gaps", str(g), "--summary", str(s), *extra)
    rows = {x["client_id"]: x for x in csv.DictReader(m.open(encoding="utf-8"))} if m.exists() else {}
    return r, rows, (g.read_text(encoding="utf-8") if g.exists() else ""), (json.loads(s.read_text()) if s.exists() else {})


def test_carry_changed_new_withdrawn(tmp_path):
    r, rows, gaps, summary = run(tmp_path, "--previous", str(FX / "matrix-previous.csv"))
    assert r.returncode == 0, r.stderr
    assert rows["4.1"]["flags"] == "carried" and rows["4.1"]["compliance"] == "P" and rows["4.1"]["status"] == "reviewed"
    assert rows["4.1"]["mitigation"] == "client dependency written into the assumptions register"
    assert rows["3.1"]["evidence"].endswith("case study CS-12")               # reviewed evidence kept
    assert rows["3.5"]["flags"].endswith("changed (was C)") and rows["3.5"]["status"] == "drafted"
    assert rows["5.2"]["flags"].endswith("new")
    assert "| 5.3 | withdrawn |" in gaps and "fictional" not in gaps
    assert summary["changes"] == {"carried": 8, "changed": 1, "new": 1, "withdrawn": 1}


def test_carried_answer_feeds_the_gate(tmp_path):
    prev = tmp_path / "prev.csv"
    prev.write_text("req_id,client_id,text,compliance,owner,status\n"
                    "REQ-006,4.1,The Supplier shall complete the migration within twelve months of contract signature.,C,PMO,approved\n",
                    encoding="utf-8")
    _, rows, _, summary = run(tmp_path, "--previous", str(prev))
    assert rows["4.1"]["compliance"] == "C" and rows["4.1"]["clarification_id"] == ""
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    _, _, _, base = run(base_dir)
    assert summary["gate"]["mandatory_C"] == base["gate"]["mandatory_C"] + 1


def test_without_previous_no_changes(tmp_path):
    _, rows, gaps, summary = run(tmp_path)
    assert "## Changes since the previous matrix" not in gaps and "changes" not in summary
    assert all("carried" not in x["flags"] for x in rows.values())


def test_previous_missing_columns_fails(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("id,text\n1,x\n", encoding="utf-8")
    r, _, _, _ = run(tmp_path, "--previous", str(bad))
    assert r.returncode != 0 and "previous matrix missing columns" in (r.stderr + r.stdout)

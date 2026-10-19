"""Tests for score_portfolio.py --previous (re-review of an existing portfolio)."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-strategy-coe/scripts/score_portfolio.py"
FX = REPO_ROOT / "skills/ai-platform/ai-strategy-coe/evals/fixtures"


def rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_previous_adds_movement(tmp_path):
    r = run_script(SCRIPT, str(FX / "use-cases.csv"), "--previous", str(FX / "previous-portfolio.csv"),
                   "--out-dir", str(tmp_path), "--org", "Northwind")
    assert r.returncode == 0, r.stderr
    by_id = {x["id"]: x for x in rows(tmp_path / "portfolio.csv")}
    assert (by_id["UC-003"]["previous_rank"], by_id["UC-003"]["movement"], by_id["UC-003"]["previous_band"]) == ("2", "down 2", "Now")
    assert by_id["UC-001"]["movement"] == "same"
    assert by_id["UC-009"]["movement"] == "new" and by_id["UC-009"]["previous_rank"] == ""
    md = (tmp_path / "portfolio.md").read_text(encoding="utf-8")
    assert "(8 ranked then, 9 ranked now). 2 new, 2 changed band." in md
    assert "| UC-010 | Field service visit summariser | 5 | — | no longer in the list | Later | — |" in md


def test_previous_row_now_unscored_is_named(tmp_path):
    src = (FX / "use-cases.csv").read_text(encoding="utf-8").splitlines()
    src = [ln.replace("HR Ops,CHRO,3,3,3,2,", "HR Ops,CHRO,3,3,,2,") for ln in src]
    cur = tmp_path / "cur.csv"
    cur.write_text("\n".join(src) + "\n", encoding="utf-8")
    r = run_script(SCRIPT, str(cur), "--previous", str(FX / "previous-portfolio.csv"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "UC-003" in {x["id"] for x in rows(tmp_path / "unscored.csv")}
    md = (tmp_path / "portfolio.md").read_text(encoding="utf-8")
    assert "| UC-003 | Internal policy assistant (RAG) | 2 | — | now unscored (see Unscored) | Now | — |" in md


def test_without_previous_columns_unchanged(tmp_path):
    r = run_script(SCRIPT, str(FX / "use-cases.csv"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    with open(tmp_path / "portfolio.csv", encoding="utf-8") as f:
        assert "movement" not in f.readline()
    assert "Changes since last review" not in (tmp_path / "portfolio.md").read_text(encoding="utf-8")


def test_previous_must_be_a_portfolio(tmp_path):
    bad = tmp_path / "prev.csv"
    bad.write_text("id,use_case\nUC-001,x\n", encoding="utf-8")
    r = run_script(SCRIPT, str(FX / "use-cases.csv"), "--previous", str(bad), "--out-dir", str(tmp_path))
    assert r.returncode == 1 and "needs columns rank,id,band" in r.stderr
    dup = tmp_path / "dup.csv"
    dup.write_text("rank,id,band\n1,UC-001,Now\n2,UC-001,Next\n", encoding="utf-8")
    r = run_script(SCRIPT, str(FX / "use-cases.csv"), "--previous", str(dup), "--out-dir", str(tmp_path))
    assert r.returncode == 1 and "duplicate id" in r.stderr

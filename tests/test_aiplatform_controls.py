"""Tests for ai-platform/ai-controls-mapping/scripts/map_controls.py (hand-computed coverage)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from conftest import REPO_ROOT, run_script

SKILL = REPO_ROOT / "skills/ai-platform/ai-controls-mapping"
SCRIPT = "skills/ai-platform/ai-controls-mapping/scripts/map_controls.py"
FIX = SKILL / "evals/fixtures"
TBD = "[TO BE BASELINED — owner: AI risk lead]"


def _ev(tmp_path: Path, rows: list[str], name="ev.csv") -> Path:
    p = tmp_path / name
    p.write_text("subcategory_id,status,evidence,owner\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return p


def _run(tmp_path, ev: Path, *extra, out="out"):
    o = tmp_path / out
    res = run_script(SCRIPT, "--evidence", str(ev), "--out-dir", str(o), *extra)
    cov = json.loads((o / "coverage.json").read_text()) if (o / "coverage.json").exists() else None
    rows = list(csv.DictReader((o / "controls.csv").open(encoding="utf-8"))) if (o / "controls.csv").exists() else []
    return res, cov, rows, o


def test_catalogue_has_72_subcategories_19_18_22_13():
    lines = [ln for ln in (SKILL / "assets/nist-ai-rmf-1.0.csv").read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    rows = list(csv.DictReader(lines))
    assert len(rows) == 72 and len({r["subcategory_id"] for r in rows}) == 72
    counts = {fn: sum(1 for r in rows if r["function"] == fn) for fn in ("GOVERN", "MAP", "MEASURE", "MANAGE")}
    assert counts == {"GOVERN": 19, "MAP": 18, "MEASURE": 22, "MANAGE": 13}
    assert len({r["category"] for r in rows}) == 19
    assert rows[-1]["subcategory_id"] == "MANAGE 4.3" and any(r["subcategory_id"] == "MEASURE 2.13" for r in rows)


def test_coverage_formula_hand_computed(tmp_path):
    # MANAGE: 13 subcategories. 2 implemented, 1 partial, 1 planned, 1 n/a, 8 missing -> (2 + 0.5) / 12 = 0.208
    ev = _ev(tmp_path, ["MANAGE 1.1,implemented,doc-1,A", "MANAGE 1.2,implemented,doc-2,A", "MANAGE 1.3,partial,doc-3,A",
                        "MANAGE 1.4,planned,,A", "MANAGE 3.2,not_applicable,no pre-trained models,A"])
    res, cov, rows, _ = _run(tmp_path, ev)
    m = cov["functions"]["MANAGE"]
    assert (m["implemented"], m["partial"], m["planned"], m["not_applicable"], m["missing"], m["applicable"]) == (2, 1, 1, 1, 8, 12)
    assert m["coverage"] == 0.208
    assert cov["functions"]["GOVERN"]["coverage"] == 0.0 and cov["overall"]["applicable"] == 71
    assert cov["overall"]["coverage"] == round(2.5 / 71, 3)
    assert len([r for r in rows if r["function"] != "ERROR"]) == 72


def test_all_not_applicable_function_is_na(tmp_path):
    ids = [f"MANAGE {x}" for x in ("1.1", "1.2", "1.3", "1.4", "2.1", "2.2", "2.3", "2.4", "3.1", "3.2", "4.1", "4.2", "4.3")]
    res, cov, _, o = _run(tmp_path, _ev(tmp_path, [f"{i},not_applicable,out of scope,A" for i in ids]))
    assert cov["functions"]["MANAGE"]["coverage"] is None
    assert "| MANAGE | 0 | 0 | 0 | 13 | 0 | 0 | n/a |" in (o / "controls-report.md").read_text()


def test_fixture_values_and_boundary_gate(tmp_path):
    ev = FIX / "evidence-northwind.csv"
    res, cov, _, _ = _run(tmp_path, ev, "--min-coverage", "0.5")
    assert res.returncode == 0 and cov["overall"]["coverage"] == 0.5 and cov["gate"] == "pass"
    assert [cov["functions"][f]["coverage"] for f in ("GOVERN", "MAP", "MEASURE", "MANAGE")] == [0.667, 0.583, 0.357, 0.385]
    res2, cov2, _, o2 = _run(tmp_path, ev, "--min-coverage", "0.501", out="o2")
    assert res2.returncode == 1 and cov2["gate"] == "fail" and (o2 / "controls-report.md").exists()


def test_missing_owner_on_gap_is_tbd(tmp_path):
    res, cov, rows, o = _run(tmp_path, _ev(tmp_path, ["GOVERN 1.1,planned,backlog,", "GOVERN 1.2,implemented,doc,Lead (fictional)"]))
    by = {r["subcategory_id"]: r for r in rows}
    assert by["GOVERN 1.1"]["owner"] == TBD and by["GOVERN 1.1"]["gap"] == "yes"
    assert by["GOVERN 1.3"]["owner"] == TBD and by["GOVERN 1.3"]["status"] == "missing"
    assert by["GOVERN 1.2"]["gap"] == "no"
    assert run_script(SCRIPT, "--verify", str(o / "controls-report.md")).returncode == 0


def test_flags_claims_without_evidence(tmp_path):
    res, cov, _, _ = _run(tmp_path, _ev(tmp_path, ["MAP 1.1,implemented,,A", "MEASURE 2.2,not_applicable,,A"]))
    assert cov["claims_without_evidence"] == ["MAP 1.1"] and cov["na_without_justification"] == ["MEASURE 2.2"]


def test_unknown_id_reported_as_error_and_exit_1(tmp_path):
    res, cov, rows, _ = _run(tmp_path, _ev(tmp_path, ["govern  1.1,implemented,doc,A", "GOVERN 7.1,implemented,doc,A"]))
    assert res.returncode == 1 and "GOVERN 7.1" in res.stderr
    err = [r for r in rows if r["function"] == "ERROR"]
    assert len(err) == 1 and err[0]["status"] == "error"
    assert cov["functions"]["GOVERN"]["implemented"] == 1  # normalised id counted, unknown id excluded


def test_invalid_inputs_exit_2(tmp_path):
    assert _run(tmp_path, _ev(tmp_path, ["GOVERN 1.1,done,doc,A"]))[0].returncode == 2
    assert _run(tmp_path, _ev(tmp_path, ["GOVERN 1.1,implemented,a,A", "GOVERN 1.1,partial,b,A"]))[0].returncode == 2
    assert _run(tmp_path, _ev(tmp_path, ["GOVERN 1.1,implemented,a,A"]), "--min-coverage", "1.5")[0].returncode == 2
    hdr = tmp_path / "h.csv"
    hdr.write_text("id,status\nGOVERN 1.1,implemented\n", encoding="utf-8")
    assert _run(tmp_path, hdr)[0].returncode == 2
    assert _run(tmp_path, tmp_path / "missing.csv")[0].returncode == 2
    assert run_script(SCRIPT, "--out-dir", str(tmp_path / "o")).returncode == 2


def test_template_rows_count_as_missing(tmp_path):
    res, cov, _, _ = _run(tmp_path, SKILL / "assets/evidence-template.csv")
    assert res.returncode == 0 and cov["overall"]["missing"] == 72 and cov["overall"]["coverage"] == 0.0


def test_aiact_obligation_support(tmp_path):
    ev = _ev(tmp_path, ["GOVERN 2.2,implemented,lms,A", "MEASURE 2.8,planned,,A"])
    res, cov, _, o = _run(tmp_path, ev, "--obligations", str(FIX / "obligations-northwind.csv"))
    sup = {x["obligation_id"]: x["support"] for x in cov["aiact_obligations"]}
    assert sup == {"TR-50-1": "none", "TR-50-2": "none"}  # AI-LIT is done -> skipped
    assert cov["aiact_open_without_evidence"] == 2
    assert "skill's own mapping" in (o / "controls-report.md").read_text()
    ev2 = _ev(tmp_path, ["GOVERN 1.3,implemented,a,A", "MAP 5.1,partial,b,A", "MANAGE 1.3,implemented,c,A"], "ev2.csv")
    _, cov2, _, _ = _run(tmp_path, ev2, "--obligations", str(FIX / "obligations-credit.csv"), out="o2")
    sup2 = {x["obligation_id"]: x["support"] for x in cov2["aiact_obligations"]}
    assert sup2["HR-RMS"] == "partial" and sup2["HR-ACC"] == "none"


def test_deterministic_and_verify_detects_tamper(tmp_path):
    ev = FIX / "evidence-northwind.csv"
    _run(tmp_path, ev, "--obligations", str(FIX / "obligations-credit.csv"), out="a")
    _run(tmp_path, ev, "--obligations", str(FIX / "obligations-credit.csv"), out="b")
    for f in ("controls.csv", "coverage.json", "controls-report.md"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes()
    assert run_script(SCRIPT, "--verify", str(tmp_path / "a")).returncode == 0
    p = tmp_path / "a" / "controls.csv"
    p.write_text(p.read_text().replace("MAP 1.2,MAP,MAP 1,missing", "MAP 1.2,MAP,MAP 1,implemented"), encoding="utf-8")
    bad = run_script(SCRIPT, "--verify", str(p))
    assert bad.returncode == 1 and "MAP" in bad.stdout

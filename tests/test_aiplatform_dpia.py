"""Tests for ai-platform/dpia/scripts/dpia.py (hand-checked screening, scoring, gate)."""
from __future__ import annotations

import csv
import json

import pytest
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/dpia/scripts/dpia.py"
FIX = REPO_ROOT / "skills/ai-platform/dpia/evals/fixtures"
TBD = "[TO BE BASELINED — owner: Data protection officer]"


def _kv(p: Path, facts: dict[str, str]) -> Path:
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["key", "value"])
        for k, v in facts.items():
            w.writerow([k, v])
    return p


def _run(tmp_path, facts=None, risks: str | None = None, inventory: str | None = None, processing: Path | None = None):
    proc = processing or _kv(tmp_path / "proc.csv", facts or {})
    out = tmp_path / "out"
    args = ["--processing", str(proc), "--out-dir", str(out)]
    if risks is not None:
        (tmp_path / "risks.csv").write_text(risks, encoding="utf-8")
        args += ["--risks", str(tmp_path / "risks.csv")]
    if inventory is not None:
        (tmp_path / "inv.csv").write_text(inventory, encoding="utf-8")
        args += ["--pii-inventory", str(tmp_path / "inv.csv")]
    res = run_script(SCRIPT, *args)
    scr = json.loads((out / "screening.json").read_text()) if (out / "screening.json").exists() else {}
    rows = list(csv.DictReader((out / "dpia-risks.csv").open(encoding="utf-8"))) if (out / "dpia-risks.csv").exists() else []
    return res, scr, rows, out


ALL_NO = {k: "no" for k in ("evaluation_scoring", "automated_decision_making", "systematic_monitoring",
                            "special_categories", "criminal_data", "highly_personal_data", "large_scale",
                            "combining_datasets", "vulnerable_subjects", "new_technology",
                            "prevents_rights_or_service", "publicly_accessible_area")}


def test_screening_one_criterion_not_required(tmp_path):
    res, scr, _, _ = _run(tmp_path, {**ALL_NO, "large_scale": "yes"})
    assert res.returncode == 0, res.stderr
    assert scr["criteria_met"] == 1 and scr["criteria_unanswered"] == 0 and scr["required"] is False


def test_screening_two_criteria_required(tmp_path):
    res, scr, _, _ = _run(tmp_path, {**ALL_NO, "large_scale": "yes", "new_technology": "yes"})
    assert scr["criteria_met"] == 2 and scr["required"] is True and not scr["art35_3_cases"]


def test_art35_3b_case(tmp_path):
    res, scr, _, _ = _run(tmp_path, {**ALL_NO, "large_scale": "yes", "special_categories": "yes"})
    assert scr["required"] is True and len(scr["art35_3_cases"]) == 1
    assert scr["art35_3_cases"][0].startswith("Art. 35(3)(b)")


def test_precautionary_when_unanswered(tmp_path):
    facts = dict(ALL_NO)
    facts["large_scale"] = "yes"
    del facts["vulnerable_subjects"]
    res, scr, _, _ = _run(tmp_path, facts)
    assert scr["criteria_met"] == 1 and scr["criteria_unanswered"] == 1 and scr["required"] is True
    assert "unclear" in scr["basis"]


def test_payment_card_inventory_meets_c4(tmp_path):
    inv = "column,pii_types,match_rate,rows_scanned,handling,matches,basis\ncard,payment_card,1.000,4,tokenize,4,pattern\n"
    facts = {k: v for k, v in ALL_NO.items() if k != "highly_personal_data"}
    res, scr, rows, _ = _run(tmp_path, facts, inventory=inv)
    c4 = [c for c in scr["criteria"] if c["id"] == "C4"][0]
    assert c4["met"] is True and "payment_card" in c4["basis"]
    assert rows[0]["risk"] == "Risks to rights and freedoms not yet identified"  # tokenize handled -> no auto risk


def test_score_level_and_residual_rules(tmp_path):
    risks = ("risk,likelihood,severity,measure,owner,residual\n"
             "A,1,2,m,o,low\nB,2,2,,,\nC,3,2,m,o,\nD,1,1,,o,\n")
    res, scr, rows, _ = _run(tmp_path, ALL_NO, risks=risks)
    assert res.returncode == 0, res.stderr
    got = {r["risk"]: (r["score"], r["level"], r["residual"]) for r in rows}
    assert got == {"A": ("2", "low", "low"), "B": ("4", "medium", "medium"),
                   "C": ("6", "high", TBD), "D": ("1", "low", "low")}
    assert scr["prior_consultation_required"] is False


def test_gate_high_residual_without_measure_exit_1(tmp_path):
    risks = "risk,likelihood,severity,measure,owner,residual\nX,3,3,,owner,\nY,3,3,measure,owner,high\n"
    res, scr, rows, out = _run(tmp_path, ALL_NO, risks=risks)
    assert res.returncode == 1 and "X" in res.stderr
    assert scr["gate_blockers"] == ["X"] and scr["signoff_status"] == "blocked"
    assert scr["prior_consultation_required"] is True
    md = (out / "dpia.md").read_text()
    assert "GATE — cannot sign off" in md and "Prior consultation required (Art. 36(1))" in md


def test_high_residual_with_measure_flags_art36_but_passes(tmp_path):
    res, scr, _, _ = _run(tmp_path, ALL_NO, risks="risk,likelihood,severity,measure,owner,residual\nY,3,3,m,o,high\n")
    assert res.returncode == 0 and scr["prior_consultation_required"] is True and scr["gate_blockers"] == []


def test_tbd_inventory_columns_become_risks_and_blanks_are_owned(tmp_path):
    inv = ("column,pii_types,match_rate,rows_scanned,handling,matches,basis\n"
           "dob,dob,1.000,4,[TO BE BASELINED — owner: Privacy officer],4,pattern\n"
           "mail,email,1.000,4,,4,pattern\nid,none,0.000,4,n/a,0,\nph,phone,1.000,4,mask,4,pattern\n")
    res, scr, rows, out = _run(tmp_path, {"system_name": "Fictional"}, inventory=inv)
    assert [r["source"] for r in rows] == ["pii_inventory:dob", "pii_inventory:mail"]
    assert all(r["level"] == "unscored" and r["owner"] == TBD for r in rows)
    md = (out / "dpia.md").read_text()
    assert f"| Controller | {TBD} |" in md
    assert "[TO BE BASELINED]" not in md


def test_invalid_inputs_exit_2(tmp_path):
    res, *_ = _run(tmp_path, {"large_scale": "maybe"})
    assert res.returncode == 2 and "large_scale" in res.stderr
    res2, *_ = _run(tmp_path, ALL_NO, risks="risk,likelihood,severity,measure,owner,residual\nA,4,1,,,\n")
    assert res2.returncode == 2 and "likelihood" in res2.stderr
    res3, *_ = _run(tmp_path, ALL_NO, risks="risk,likelihood,severity,measure,owner,residual\nA,1,1,,,critical\n")
    assert res3.returncode == 2
    assert run_script(SCRIPT, "--out-dir", str(tmp_path / "o")).returncode == 2
    assert run_script(SCRIPT, "--processing", str(tmp_path / "nope.csv"), "--out-dir", str(tmp_path / "o")).returncode == 2
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    assert run_script(SCRIPT, "--processing", str(empty), "--out-dir", str(tmp_path / "o")).returncode == 2


def test_fixture_happy_path_and_deterministic(tmp_path):
    outs = []
    for n in ("a", "b"):
        out = tmp_path / n
        res = run_script(SCRIPT, "--processing", str(FIX / "processing.csv"), "--pii-inventory",
                         str(FIX / "pii-inventory.csv"), "--risks", str(FIX / "risks.csv"), "--out-dir", str(out))
        assert res.returncode == 0, res.stderr
        outs.append({f: (out / f).read_bytes() for f in ("dpia.md", "dpia-risks.csv", "screening.json")})
    assert outs[0] == outs[1]
    scr = json.loads(outs[0]["screening.json"])
    assert scr["criteria_met"] == 5 and scr["required"] is True and scr["signoff_status"] == "incomplete"


def test_verify_ok_and_detects_tamper(tmp_path):
    res, _, _, out = _run(tmp_path, ALL_NO, risks="risk,likelihood,severity,measure,owner,residual\nA,2,3,m,o,low\n")
    assert run_script(SCRIPT, "--verify", str(out / "dpia-risks.csv")).returncode == 0
    p = out / "dpia-risks.csv"
    p.write_text(p.read_text().replace(",6,high,", ",5,high,"), encoding="utf-8")
    bad = run_script(SCRIPT, "--verify", str(p))
    assert bad.returncode == 1 and "score" in bad.stderr
    assert run_script(SCRIPT, "--verify", str(tmp_path / "missing")).returncode == 2


# ---------------------------------------------------------------- audit 2026-10-19 regressions

AUDIT_PROCESSING = {
    "system_name": "HR attrition predictor", "controller": "Acme GmbH", "data_subjects": "Employees",
    "evaluation_scoring": "yes", "automated_decision_making": "no", "systematic_monitoring": "no",
    "special_categories": "no", "criminal_data": "no", "highly_personal_data": "", "large_scale": "no",
    "combining_datasets": "yes", "vulnerable_subjects": "yes", "new_technology": "",
    "prevents_rights_or_service": "no", "international_transfers": "yes"}
AUDIT_RISKS = ('risk,likelihood,severity,measure,owner,residual\n'
               'Discriminatory predictions against protected groups,3,3,,HR lead,low\n'
               '"=HYPERLINK(""http://evil"",""Re-identification"")",2,3,Pseudonymise,"=1+1",\n'
               'Excessive retention,2,2,Delete after 12 months,DPO,\n'
               'Covert monitoring perception,3,3,,Works council,\n')


def test_audit_stated_low_residual_without_measure_is_gated_and_flags_art36(tmp_path):
    res, scr, rows, out = _run(tmp_path, AUDIT_PROCESSING, risks=AUDIT_RISKS)
    assert res.returncode == 1
    disc = "Discriminatory predictions against protected groups"
    assert disc in scr["gate_blockers"] and disc in scr["residual_overrides"]
    assert scr["prior_consultation_required"] is True
    by = {r["risk"]: r for r in rows}
    assert by[disc]["residual"] == "high" and by[disc]["measure"] == TBD
    md = (out / "dpia.md").read_text(encoding="utf-8")
    assert "stated residual 'low' is not credible" in md and "Stated residual not accepted" in md
    assert run_script(SCRIPT, "--verify", str(out)).returncode == 0


def test_audit_medium_inherent_low_stated_no_measure_overridden(tmp_path):
    res, scr, rows, _ = _run(tmp_path, ALL_NO, risks="risk,likelihood,severity,measure,owner,residual\nM,2,2,,o,low\n")
    assert res.returncode == 0 and rows[0]["residual"] == "medium" and scr["residual_overrides"] == ["M"]


def test_audit_verify_rejects_residual_below_inherent_without_measure(tmp_path):
    res, _, _, out = _run(tmp_path, ALL_NO, risks="risk,likelihood,severity,measure,owner,residual\nM,2,2,,o,\n")
    p = out / "dpia-risks.csv"
    p.write_text(p.read_text(encoding="utf-8").replace(",o,medium", ",o,low"), encoding="utf-8")
    bad = run_script(SCRIPT, "--verify", str(p))
    assert bad.returncode == 1 and "below inherent" in bad.stderr


def test_audit_csv_injection_escaped_and_verify_agrees(tmp_path):
    res, scr, rows, out = _run(tmp_path, AUDIT_PROCESSING, risks=AUDIT_RISKS)
    reid = [r for r in rows if "HYPERLINK" in r["risk"]][0]
    assert reid["risk"].startswith("'=HYPERLINK") and reid["owner"] == "'=1+1"
    assert all(r["score"].isdigit() for r in rows)  # numbers untouched
    for r in rows:
        for v in r.values():
            assert not v.startswith(("=", "+", "-", "@", "\t", "\r"))
    assert run_script(SCRIPT, "--verify", str(out / "dpia-risks.csv")).returncode == 0


def test_audit_gate_blocker_with_formula_name_verifies(tmp_path):
    res, scr, rows, out = _run(tmp_path, ALL_NO, risks="risk,likelihood,severity,measure,owner,residual\n=X,3,3,,o,\n")
    assert res.returncode == 1 and scr["gate_blockers"] == ["=X"] and rows[0]["risk"] == "'=X"
    assert run_script(SCRIPT, "--verify", str(out)).returncode == 0


def test_audit_one_criterion_result_is_qualified(tmp_path):
    facts = dict(AUDIT_PROCESSING, highly_personal_data="no", combining_datasets="no", vulnerable_subjects="no",
                 new_technology="no")
    res, scr, _, out = _run(tmp_path, facts)
    assert res.returncode == 0 and scr["required"] is False and scr["criteria_met"] == 1
    md = (out / "dpia.md").read_text(encoding="utf-8")
    assert "Result: **DPIA not required**" not in md
    assert "not required on the WP248 two-criteria rule" in md
    assert "single criterion can suffice" in md and "Art. 35(4)" in md


def test_audit_non_utf8_input_exit_2_no_traceback(tmp_path):
    for name, data in (("bin.csv", b"\x89PNG\r\n\x1a\n\x00\x00\xff\xfe\xfd"), ("cp.csv", b"key,value\nsystem_name,Caf\xe9\n")):
        p = tmp_path / name
        p.write_bytes(data)
        res = run_script(SCRIPT, "--processing", str(p), "--out-dir", str(tmp_path / "o"))
        assert res.returncode == 2 and "Traceback" not in res.stderr and "UTF-8" in res.stderr
    bom = tmp_path / "bom.csv"
    bom.write_bytes("﻿key,value\nlarge_scale,yes\n".encode("utf-8"))
    assert run_script(SCRIPT, "--processing", str(bom), "--out-dir", str(tmp_path / "o2")).returncode == 0


@pytest.mark.parametrize("placeholder", ["none", "TBD", "n/a", "[TO BE BASELINED — owner: DPO]", "-"])
def test_placeholder_measure_cannot_clear_the_gate(tmp_path, placeholder):
    """Re-audit finding: a score-9 risk with a placeholder measure and a stated 'low' residual passed the gate."""
    fix = REPO_ROOT / "skills/ai-platform/dpia/evals/fixtures"
    risks = tmp_path / "risks.csv"
    risks.write_text("risk,likelihood,severity,measure,owner,residual\n"
                     f"Re-identification from model outputs,3,3,{placeholder},DPO,low\n", encoding="utf-8")
    res = run_script("skills/ai-platform/dpia/scripts/dpia.py", "--processing", str(fix / "processing.csv"),
                     "--risks", str(risks), "--out-dir", str(tmp_path / "o"))
    assert res.returncode == 1, res.stdout + res.stderr
    assert json.loads((tmp_path / "o" / "screening.json").read_text()) is not None
    assert "Art. 36" in (tmp_path / "o" / "dpia.md").read_text(encoding="utf-8")

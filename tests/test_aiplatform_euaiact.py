"""Tests for ai-platform/eu-ai-act-classifier/scripts/classify.py (hand-checked classifications)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from conftest import REPO_ROOT, run_script

SKILL = REPO_ROOT / "skills/ai-platform/eu-ai-act-classifier"
SCRIPT = "skills/ai-platform/eu-ai-act-classifier/scripts/classify.py"
FIX = SKILL / "evals/fixtures"
TBD = "[TO BE BASELINED — owner: AI compliance lead]"


def _keys() -> list[str]:
    lines = [ln for ln in (SKILL / "assets/system-questionnaire.csv").read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    return [r["key"] for r in csv.DictReader(lines)]


def _system(tmp_path: Path, **over) -> Path:
    """All-'no' fictional provider system, with overrides (None drops the key)."""
    vals = {k: "no" for k in _keys()}
    vals.update(system_name="Test System (fictional)", role="provider", intended_purpose="test",
                placed_on_market="2026-09-01", accountable_owner="Owner (fictional)")
    vals.update(over)
    p = tmp_path / "system.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["key", "value", "source", "notes"])
        for k, v in vals.items():
            if v is not None:
                w.writerow([k, v, "test", ""])
    return p


def _run(tmp_path, system: Path, *extra, out="out"):
    o = tmp_path / out
    res = run_script(SCRIPT, "--system", str(system), "--out-dir", str(o), *extra)
    cls = json.loads((o / "classification.json").read_text()) if (o / "classification.json").exists() else None
    obl = list(csv.DictReader((o / "obligations.csv").open(encoding="utf-8"))) if (o / "obligations.csv").exists() else []
    return res, cls, {r["obligation_id"]: r for r in obl}, o


def test_minimal_when_all_no(tmp_path):
    res, cls, obl, _ = _run(tmp_path, _system(tmp_path))
    assert res.returncode == 0, res.stderr
    assert cls["tier"] == "minimal" and cls["unanswered_keys"] == []
    assert list(obl) == ["AI-LIT"] and obl["AI-LIT"]["applies_from"] == "2025-02-02"


def test_prohibited_exits_1_and_writes_outputs(tmp_path):
    res, cls, obl, o = _run(tmp_path, _system(tmp_path, p_social_scoring="yes", a3_employment="yes"))
    assert res.returncode == 1 and "p_social_scoring" in res.stderr
    assert cls["tier"] == "prohibited" and cls["gate"] == "fail"
    assert obl["PRO-5-1-C"]["applies_from"] == "2025-02-02"
    assert (o / "ai-act-report.md").exists()


def test_new_omnibus_prohibition_date(tmp_path):
    res, cls, obl, _ = _run(tmp_path, _system(tmp_path, p_non_consensual_intimate_content="yes"))
    assert res.returncode == 1 and obl["PRO-5-1-BA"]["applies_from"] == "2026-12-02"


def test_annex3_high_risk_dates_and_profiling_overrides_derogation(tmp_path):
    res, cls, obl, _ = _run(tmp_path, _system(tmp_path, a3_employment="yes", d63_preparatory="yes", d63_profiling="yes"))
    assert res.returncode == 0 and cls["tier"] == "high-risk" and cls["high_risk_routes"] == ["annex3"]
    assert obl["HR-RMS"]["applies_from"] == "2027-12-02"
    assert "HR-DEP" not in obl  # provider role only


def test_annex1_route_uses_2028_date(tmp_path):
    res, cls, obl, _ = _run(tmp_path, _system(tmp_path, annex1_safety_component="yes"))
    assert cls["high_risk_routes"] == ["annex1"] and obl["HR-QMS"]["applies_from"] == "2028-08-02"


def test_derogation_applies_without_profiling(tmp_path):
    res, cls, obl, _ = _run(tmp_path, _system(tmp_path, a3_education="yes", d63_narrow_procedural="yes"))
    assert cls["tier"] == "minimal" and cls["art_6_3_derogation_applied"] is True
    assert obl["DER-6-4"]["applies_from"] == "2027-12-02" and "HR-RMS" not in obl


def test_blank_tier_changing_answer_is_undetermined_with_owner(tmp_path):
    res, cls, obl, o = _run(tmp_path, _system(tmp_path, a3_employment="", t_interacts_with_persons="yes"))
    assert res.returncode == 0
    assert cls["tier"] == "undetermined" and cls["provisional_tier"] == "limited-transparency"
    assert cls["tier_open_keys"] == ["a3_employment"]
    rep = (o / "ai-act-report.md").read_text()
    assert f"| a3_employment | Annex III point 4 |" in rep and TBD in rep


def test_blank_transparency_does_not_change_high_risk_tier(tmp_path):
    res, cls, _, _ = _run(tmp_path, _system(tmp_path, annex1_safety_component="yes", t_deepfake=""))
    assert cls["tier"] == "high-risk"
    assert [u["key"] for u in cls["unanswered_keys"]] == ["t_deepfake"]
    assert cls["unanswered_keys"][0]["could_change_tier"] is False


def test_art50_2_transition_and_as_of(tmp_path):
    sysp = _system(tmp_path, t_synthetic_content="yes", t_interacts_with_persons="yes", placed_on_market="2026-03-01")
    res, cls, obl, _ = _run(tmp_path, sysp, "--as-of", "2026-10-18")
    assert obl["TR-50-2"]["applies_from"] == "2026-12-02" and obl["TR-50-2"]["in_force"] == "no"
    assert obl["TR-50-1"]["in_force"] == "yes" and cls["obligations_in_force"] == 2
    res2, _, obl2, _ = _run(tmp_path, _system(tmp_path, t_synthetic_content="yes", placed_on_market="2026-09-01"), out="o2")
    assert obl2["TR-50-2"]["applies_from"] == "2026-08-02" and obl2["TR-50-2"]["in_force"] == "not assessed (no --as-of)"


def test_gpai_legacy_model_date_and_missing_pom_tbd(tmp_path):
    res, _, obl, _ = _run(tmp_path, _system(tmp_path, is_gpai="yes", gpai_systemic_risk="yes", placed_on_market="2025-03-01"))
    assert obl["GP-53"]["applies_from"] == "2027-08-02" and obl["GP-55"]["applies_from"] == "2027-08-02"
    res2, _, obl2, _ = _run(tmp_path, _system(tmp_path, is_gpai="yes", placed_on_market=None), out="o2")
    assert TBD in obl2["GP-53"]["applies_from"]


def test_deployer_role_filters_obligations(tmp_path):
    # fria_scope=yes added (audit 2026-10-19): Art. 27(1) FRIA only for in-scope deployers.
    res, _, obl, _ = _run(tmp_path, _system(tmp_path, role="deployer", a3_essential_services="yes", t_deepfake="yes",
                                            fria_scope="yes"))
    assert {"HR-DEP", "HR-FRIA", "TR-50-4-D", "AI-LIT"} <= set(obl) and "HR-RMS" not in obl


def test_evidence_sets_status_and_owner(tmp_path):
    res, _, obl, _ = _run(tmp_path, _system(tmp_path), "--evidence", str(FIX / "evidence.csv"))
    assert obl["AI-LIT"]["status"] == "done" and obl["AI-LIT"]["owner"] == "HR Learning Lead (fictional)"


def test_invalid_inputs_exit_2(tmp_path):
    assert _run(tmp_path, _system(tmp_path, role="vendor"))[0].returncode == 2
    assert _run(tmp_path, _system(tmp_path, a3_education="maybe"))[0].returncode == 2
    assert _run(tmp_path, tmp_path / "nope.csv")[0].returncode == 2
    bad = tmp_path / "ev.csv"
    bad.write_text("obligation_id,status,evidence,owner\nXX-1,done,,\n", encoding="utf-8")
    res = run_script(SCRIPT, "--system", str(_system(tmp_path)), "--evidence", str(bad), "--out-dir", str(tmp_path / "o"))
    assert res.returncode == 2 and "XX-1" in res.stderr
    res = run_script(SCRIPT, "--system", str(_system(tmp_path)), "--as-of", "18/10/2026", "--out-dir", str(tmp_path / "o"))
    assert res.returncode == 2
    assert run_script(SCRIPT, "--out-dir", str(tmp_path / "o")).returncode == 2


def test_questionnaire_template_is_all_open(tmp_path):
    res, cls, obl, _ = _run(tmp_path, SKILL / "assets/system-questionnaire.csv")
    assert res.returncode == 0 and cls["tier"] == "undetermined"
    assert len(cls["unanswered_keys"]) == len(_keys())


def test_deterministic_and_verify(tmp_path):
    sysp = FIX / "system-northwind.csv"
    _run(tmp_path, sysp, "--as-of", "2026-10-18", out="a")
    _run(tmp_path, sysp, "--as-of", "2026-10-18", out="b")
    for f in ("classification.json", "obligations.csv", "ai-act-report.md"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes()
    assert run_script(SCRIPT, "--verify", str(tmp_path / "a" / "obligations.csv")).returncode == 0
    rep = tmp_path / "a" / "ai-act-report.md"
    rep.write_text(rep.read_text().replace("| TR-50-2 |", "| XX |"), encoding="utf-8")
    bad = run_script(SCRIPT, "--verify", str(rep))
    assert bad.returncode == 1 and "TR-50-2" in bad.stdout


# ---------------------------------------------------------------- audit 2026-10-19 regressions

def _cv(tmp_path, role="provider", profiling="no", name="cv.csv", **over) -> Path:
    """The auditor's CV-screener questionnaire (formula in accountable_owner)."""
    p = _system(tmp_path, system_name="CV screener", role=role, intended_purpose="Rank job applicants",
                placed_on_market="2026-03-01", accountable_owner='=HYPERLINK("http://evil","HR")',
                a3_employment="yes", d63_preparatory="yes", d63_profiling=profiling,
                t_interacts_with_persons="yes", t_synthetic_content="yes", **over)
    return p.rename(tmp_path / name)


def test_audit_owner_formula_escaped_in_obligations_csv(tmp_path):
    res, cls, obl, o = _run(tmp_path, _cv(tmp_path), "--as-of", "2026-10-18")
    assert res.returncode == 0 and obl
    assert all(r["owner"] == "'=HYPERLINK(\"http://evil\",\"HR\")" for r in obl.values())
    assert run_script(SCRIPT, "--verify", str(o)).returncode == 0


def test_audit_evidence_text_escaped(tmp_path):
    ev = tmp_path / "ev.csv"
    ev.write_text('obligation_id,status,evidence,owner\nAI-LIT,done,"+cmd|calc","@SUM(A1)"\n', encoding="utf-8")
    res, _, obl, _ = _run(tmp_path, _system(tmp_path), "--evidence", str(ev))
    assert obl["AI-LIT"]["evidence"] == "'+cmd|calc" and obl["AI-LIT"]["owner"] == "'@SUM(A1)"


def test_audit_bom_questionnaire_classified_like_plain(tmp_path):
    plain = _cv(tmp_path)
    bom = tmp_path / "cv-bom.csv"
    bom.write_bytes(b"\xef\xbb\xbf" + plain.read_bytes())
    r1, c1, o1, _ = _run(tmp_path, plain, out="a")
    r2, c2, o2, _ = _run(tmp_path, bom, out="b")
    assert r2.returncode == 0, r2.stderr
    assert c1["tier"] == c2["tier"] and set(o1) == set(o2)


def test_audit_non_utf8_input_exit_2_no_traceback(tmp_path):
    p = tmp_path / "bin.csv"
    p.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\xff\xfe\xfd")
    res, *_ = _run(tmp_path, p)
    assert res.returncode == 2 and "Traceback" not in res.stderr and "UTF-8" in res.stderr
    ev = tmp_path / "ev.csv"
    ev.write_bytes(b"obligation_id,status,evidence,owner\nAI-LIT,done,caf\xe9,x\n")
    res2, *_ = _run(tmp_path, _system(tmp_path), "--evidence", str(ev), out="o2")
    assert res2.returncode == 2 and "Traceback" not in res2.stderr


def test_audit_ai_literacy_wording_as_amended():
    cat = (SKILL / "assets/obligations-catalogue.csv").read_text(encoding="utf-8")
    row = [ln for ln in cat.splitlines() if ln.startswith("AI-LIT,")][0]
    assert "take measures to support the development of ai literacy" in row.lower()
    assert "sufficient level" not in row


def test_audit_fria_only_in_art27_scope(tmp_path):
    res, cls, obl, o = _run(tmp_path, _cv(tmp_path, role="deployer", profiling="yes", fria_scope=None), "--as-of", "2026-10-18")
    assert cls["tier"] == "high-risk" and "HR-DEP" in obl and "HR-FRIA" not in obl
    assert cls["fria_pending"] is True and "fria_scope" in [u["key"] for u in cls["unanswered_keys"]]
    assert "HR-FRIA (Art. 27" in (o / "ai-act-report.md").read_text(encoding="utf-8")
    _, _, obl_no, _ = _run(tmp_path, _cv(tmp_path, role="deployer", profiling="yes", fria_scope="no", name="n.csv"), out="no")
    assert "HR-FRIA" not in obl_no
    _, _, obl_yes, _ = _run(tmp_path, _cv(tmp_path, role="deployer", profiling="yes", fria_scope="yes", name="y.csv"), out="yes")
    assert "HR-FRIA" in obl_yes
    _, cls_p, _, _ = _run(tmp_path, _cv(tmp_path, profiling="yes", fria_scope=None, name="p.csv"), out="prov")
    assert "fria_scope" not in [u["key"] for u in cls_p["unanswered_keys"]]  # Art. 27 binds deployers only

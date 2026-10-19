"""Tests for ai-platform/ai-governance-risk/scripts/risk_register.py."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-governance-risk/scripts/risk_register.py"
FX = REPO_ROOT / "skills/ai-platform/ai-governance-risk/evals/fixtures"
TBD = "[TO BE BASELINED — owner: AI risk lead]"


def rows(path):
    with path.open(encoding="utf-8") as f:
        return {r["category"]: r for r in csv.DictReader(f)}


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_register_from_medium_canvas(tmp_path):
    r = run_script(SCRIPT, str(FX / "use-case-canvas.md"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    rs = rows(tmp_path / "risk-register.csv")
    assert len(rs) == 9
    assert rs["privacy"]["likelihood"] == "3" and rs["privacy"]["impact"] == "3" and rs["privacy"]["rating"] == "Medium"
    assert rs["privacy"]["owner"] == "HR Ops Lead" and rs["privacy"]["control_id"].startswith("C01; C02; C03; C04")
    assert rs["hallucination"]["rating"] == "Medium" and rs["transparency"]["rating"] == "Medium"
    assert rs["bias"]["likelihood"] == TBD and rs["bias"]["rating"] == "TBD" and "C08" in rs["bias"]["control_id"]
    assert all(x["control"] for x in rs.values())
    card = (tmp_path / "model-card.md").read_text(encoding="utf-8")
    assert "# Model Card — Benefits enquiry assistant — v0.1" in card
    assert "| Risk tier (internal / EU AI Act summary) | medium / [TO BE BASELINED — owner: AI risk lead] |" in card
    assert "| Retrieval sources | HR policy library (SharePoint) |" in card
    assert "| C02 — Data classification and minimization" in card           # tier minimum control set
    assert "| C08 —" not in card                                             # high-tier-only control not required
    assert "legal review required" in card
    assert "[TO BE BASELINED — owner: AI risk lead]" in card and "[TO BE BASELINED]" not in card.replace(TBD, "")


def test_high_risk_without_control_exits_1(tmp_path):
    r = run_script(SCRIPT, str(FX / "use-case-canvas-high.md"), "--out-dir", str(tmp_path),
                   "--controls", str(FX / "controls-catalog-no-security.md"))
    assert r.returncode == 1 and "without a mapped control: ['security']" in r.stderr
    rs = rows(tmp_path / "risk-register.csv")
    assert rs["security"]["rating"] == "High" and rs["security"]["control_id"] == ""
    assert rs["bias"]["rating"] == "High" and rs["bias"]["control_id"]
    ok = run_script(SCRIPT, str(FX / "use-case-canvas-high.md"), "--out-dir", str(tmp_path / "ok"))
    assert ok.returncode == 0


def test_thin_canvas_invents_nothing(tmp_path):
    r = run_script(SCRIPT, str(FX / "use-case-canvas-thin.md"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    rs = rows(tmp_path / "risk-register.csv")
    assert all(x["rating"] == "TBD" and x["likelihood"] == TBD and x["impact"] == TBD for x in rs.values())
    assert all(x["control_id"] for x in rs.values())
    card = (tmp_path / "model-card.md").read_text(encoding="utf-8")
    assert "(tier not stated in canvas)" in card


def test_bad_input_exits_1(tmp_path):
    assert run_script(SCRIPT, str(tmp_path / "no.md"), "--out-dir", str(tmp_path)).returncode == 1
    nobox = tmp_path / "nobox.md"
    nobox.write_text("# Canvas\nno table here\n", encoding="utf-8")
    assert run_script(SCRIPT, str(nobox), "--out-dir", str(tmp_path)).returncode == 1
    nocat = tmp_path / "nocat.md"
    nocat.write_text("# Controls\n", encoding="utf-8")
    assert run_script(SCRIPT, str(FX / "use-case-canvas.md"), "--out-dir", str(tmp_path), "--controls", str(nocat)).returncode == 1


# ---------------------------------------------------------------- existing register (--existing)

def diff_rows(path):
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_new_register_writes_empty_diff(tmp_path):
    r = run_script(SCRIPT, str(FX / "use-case-canvas.md"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "register-diff.csv").read_text(encoding="utf-8").strip() == \
        "risk_id,category,field,previous,current,change"


def test_existing_register_carried_forward(tmp_path):
    r = run_script(SCRIPT, str(FX / "use-case-canvas.md"), "--out-dir", str(tmp_path),
                   "--existing", str(FX / "risk-register-2026q2.csv"))
    assert r.returncode == 0, r.stderr
    rs = rows(tmp_path / "risk-register.csv")
    # stable ids from the existing register; a category it lacked gets a non-colliding id
    assert [rs[c]["risk_id"] for c in ("bias", "privacy", "transparency")] == ["R-101", "R-102", "R-108"]
    assert rs["safety"]["risk_id"] == "R-009"
    # canvas gives no likelihood for bias: the reviewed score and owner carry forward, labelled
    assert rs["bias"]["likelihood"] == "2" and rs["bias"]["impact"] == "3" and rs["bias"]["rating"] == "Low"
    assert rs["bias"]["owner"] == "Head of HR Analytics (fictional)"
    assert "likelihood 2 carried forward from existing register `risk-register-2026q2.csv` R-101 (re-confirm)" in rs["bias"]["basis"]
    # the canvas wins where it supports a value
    assert rs["privacy"]["likelihood"] == "3" and rs["privacy"]["owner"] == "HR Ops Lead"
    # previously accepted controls still in the catalog stay mapped; unknown ids are not carried
    assert rs["security"]["control_id"].endswith("; C12") and "C99" not in rs["security"]["control_id"]
    assert rs["ip"]["likelihood"] == TBD and rs["ip"]["rating"] == "TBD"
    d = diff_rows(tmp_path / "register-diff.csv")
    changes = {(x["risk_id"], x["field"]): x for x in d}
    assert changes[("R-102", "likelihood")]["previous"] == "4" and changes[("R-102", "likelihood")]["current"] == "3"
    assert changes[("R-109", "row")]["change"].startswith("not carried: category not in the taxonomy")
    assert changes[("R-009", "row")]["change"] == "new: category not in the existing register"
    assert any(x["field"] == "control_id" and x["previous"] == "C99" and x["change"].startswith("not carried") for x in d)
    card = (tmp_path / "model-card.md").read_text(encoding="utf-8")
    assert "bias: " not in card  # Low ratings stay out of the limitations list


def test_existing_register_rerates_and_high_gate(tmp_path):
    ex = tmp_path / "ex.csv"
    ex.write_text("risk_id,category,likelihood,impact,owner\nR-001,bias,5,3,Fairness lead\n", encoding="utf-8")
    out = tmp_path / "o"
    r = run_script(SCRIPT, str(FX / "use-case-canvas.md"), "--out-dir", str(out), "--existing", str(ex))
    assert r.returncode == 0, r.stderr
    rs = rows(out / "risk-register.csv")
    assert rs["bias"]["likelihood"] == "5" and rs["bias"]["rating"] == "High" and rs["bias"]["control_id"]
    assert ("R-001", "rating") not in {(x["risk_id"], x["field"]) for x in diff_rows(out / "register-diff.csv")}
    # privacy's default id R-002 is free, so it is kept; the existing row's id R-001 stays on bias
    assert rs["privacy"]["risk_id"] == "R-002"
    # a carried-forward High with no control in the catalog fails the gate
    hi = tmp_path / "hi.csv"
    hi.write_text("risk_id,category,likelihood,impact\nR-005,security,5,5\n", encoding="utf-8")
    r = run_script(SCRIPT, str(FX / "use-case-canvas-thin.md"), "--out-dir", str(tmp_path / "g"), "--existing", str(hi),
                   "--controls", str(FX / "controls-catalog-no-security.md"))
    assert r.returncode == 1 and "['security']" in r.stderr


def test_existing_template_layout_aliases(tmp_path):
    ex = tmp_path / "ex.csv"
    ex.write_text("risk_id,use_case,category,likelihood_1_5,impact_1_5,control_ids,control_owner\n"
                  "R-001,x,misuse,2,4,C13,Ops manager\n", encoding="utf-8")
    out = tmp_path / "o"
    assert run_script(SCRIPT, str(FX / "use-case-canvas-thin.md"), "--out-dir", str(out), "--existing", str(ex)).returncode == 0
    rs = rows(out / "risk-register.csv")
    assert rs["misuse"]["likelihood"] == "2" and rs["misuse"]["impact"] == "4" and rs["misuse"]["rating"] == "Medium"
    assert rs["misuse"]["owner"] == "Ops manager"
    assert rs["bias"]["risk_id"] != "R-001"  # default id taken by the existing misuse row -> reassigned


def test_existing_register_bad_input_exits_1(tmp_path):
    assert run_script(SCRIPT, str(FX / "use-case-canvas.md"), "--out-dir", str(tmp_path),
                      "--existing", str(tmp_path / "none.csv")).returncode == 1
    bad = tmp_path / "bad.csv"
    bad.write_text("id,score\n1,2\n", encoding="utf-8")
    r = run_script(SCRIPT, str(FX / "use-case-canvas.md"), "--out-dir", str(tmp_path), "--existing", str(bad))
    assert r.returncode == 1 and "category column" in r.stderr

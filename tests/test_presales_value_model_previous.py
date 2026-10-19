"""presales/value-case-builder: --previous value case comparison."""
from __future__ import annotations

import json
import sys

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/presales/value-case-builder"
SCRIPT = SK / "scripts/value_model.py"
FX = SK / "evals/fixtures"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import check_output  # noqa: E402


def vm(tmp_path, *extra, benefits=FX / "benefits.csv"):
    j, md = tmp_path / "v.json", tmp_path / "v.md"
    r = run_script(SCRIPT, str(benefits), str(FX / "costs.csv"), "--discount-rate", "0.08", "--p80-cost-uplift", "0.15",
                   "--json", str(j), "--out", str(md), *extra)
    return r, (json.loads(j.read_text()) if j.exists() else None), (md.read_text(encoding="utf-8") if md.exists() else "")


def test_change_rows_and_traceability(tmp_path):
    r, m, md = vm(tmp_path, "--previous", str(FX / "value-model-previous.json"))
    assert r.returncode == 0, r.stderr
    rows = {x["item"]: x for x in m["change"]["rows"]}
    assert rows["Payback month"] == {"item": "Payback month", "previous": 28, "now": 25, "delta": -3}
    assert rows["Net (undiscounted)"]["delta"] == 729000.0
    status = {b["benefit_id"]: b["status"] for b in m["change"]["benefits"]}
    assert status == {"B-01": "re-estimated", "B-02": "unchanged", "B-03": "added", "B-04": "added"}
    assert "| Payback month | 28 | 25 | −3 |" in md
    res = check_output.run_check("numbers_trace_to:v.json", str(tmp_path / "v.md"), mode="real", cwd=str(tmp_path))
    assert res["pass"], res["evidence"]


def test_newly_baselined_and_removed(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    vm(base)                                  # previous run: B-04 unbaselined
    b2 = tmp_path / "b2.csv"
    lines = (FX / "benefits.csv").read_text(encoding="utf-8").splitlines()
    lines = [ln for ln in lines if not ln.startswith("B-03")]
    lines = [("B-04,Reduced peak overtime,Store operations cost,40,1000,100,100,100,Store ops report 2026-09"
              if ln.startswith("B-04") else ln) for ln in lines]
    b2.write_text("\n".join(lines) + "\n", encoding="utf-8")
    r, m, _ = vm(tmp_path, "--previous", str(base / "v.json"), benefits=b2)
    assert r.returncode == 0, r.stderr
    status = {b["benefit_id"]: b["status"] for b in m["change"]["benefits"]}
    assert status["B-04"] == "now baselined (enters the headline)" and status["B-03"] == "removed"


def test_bad_previous_exits_2(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"totals": 1}', encoding="utf-8")
    r, _, _ = vm(tmp_path, "--previous", str(bad))
    assert r.returncode == 2 and "not a value-model.json" in r.stderr
    r, _, _ = vm(tmp_path, "--previous", str(tmp_path / "none.json"))
    assert r.returncode == 2 and "previous value model not found" in r.stderr

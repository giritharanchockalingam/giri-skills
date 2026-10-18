"""Tests for ai-platform/ai-incident-runbook/scripts/runbook.py (fixtures are fictional)."""
from __future__ import annotations

import json

import pytest

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-incident-runbook/scripts/runbook.py"
SKILL = REPO_ROOT / "skills/ai-platform/ai-incident-runbook"
FX = SKILL / "evals/fixtures"


def _run(tmp_path, incident, matrix=None):
    out = tmp_path / "out"
    args = ["--incident", str(incident), "--out-dir", str(out)] + (["--matrix", str(matrix)] if matrix else [])
    r = run_script(SCRIPT, *args)
    rec = json.loads((out / "incident.json").read_text(encoding="utf-8")) if (out / "incident.json").exists() else None
    md = (out / "runbook.md").read_text(encoding="utf-8") if (out / "runbook.md").exists() else ""
    return r, rec, md


def _incident(tmp_path, **kv):
    p = tmp_path / "inc.csv"
    p.write_text("# fictional fixture\nkey,value\n" + "".join(f"{k},{v}\n" for k, v in kv.items()), encoding="utf-8")
    return p


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_data_leak_regulated_is_sev1_with_reasoning(tmp_path):
    r, rec, md = _run(tmp_path, FX / "incident-data-leak.csv")
    assert r.returncode == 0, r.stderr
    assert rec["severity"] == "SEV1"
    assert [f["rule_id"] for f in rec["fired_rules"]] == ["D01", "D04", "D05", "D13"]
    assert "default matrix" in rec["matrix_source"]
    assert rec["time_to_detect_min"] == 75.0                     # 14:05 -> 15:20
    assert rec["communications"]["regulator"] and rec["communications"]["regulator_basis"] == "regulated_data = yes"
    assert set(rec["playbook"]["sections"]) >= {"contain", "eradicate", "recover", "verify"}
    for sec in ("## Severity", "## Immediate actions", "## Containment", "## Recovery", "## Communications", "## Postmortem"):
        assert sec in md
    assert "IC Rota (fictional)" in md and "Comms lead" not in rec["owners"]["Comms lead"]


def test_unknowns_escalate_and_are_not_invented(tmp_path):
    r, rec, md = _run(tmp_path, FX / "incident-injection-unknowns.csv")
    assert r.returncode == 0
    assert rec["severity"] == "SEV2"
    assert {"D03", "D08", "D12", "D13"} == {f["rule_id"] for f in rec["fired_rules"]}
    assert "unknown escalates" in rec["communications"]["regulator_basis"]
    assert set(rec["unknowns"]) >= {"users_affected", "data_exposed", "regulated_data", "detected_at"}
    assert rec["owners"]["Incident commander"] == "[TO BE BASELINED — owner: On-call engineering manager]"
    assert rec["owners"]["Legal / privacy"] == "[TO BE BASELINED — owner: Incident commander]"
    assert rec["time_to_detect_min"] is None
    # only the supplied time appears in the timeline
    assert [t["time"] for t in rec["timeline"] if not t["time"].startswith("[TO BE BASELINED")] == ["2026-10-03T08:00:00+00:00"]
    assert "owner: ___" not in md


def test_regulator_track_only_when_regulated_yes_or_unknown(tmp_path):
    r, rec, md = _run(tmp_path, FX / "incident-cost-spike.csv")
    assert r.returncode == 0
    assert rec["severity"] == "SEV4" and [f["rule_id"] for f in rec["fired_rules"]] == ["D13"]
    assert rec["communications"]["regulator"] == [] and "no regulator track" in rec["communications"]["regulator_basis"]
    assert rec["communications"]["customer"] == []               # users_affected = 0
    assert "Not required: users_affected = 0." in md


@pytest.mark.parametrize("users,expected", [("1500", "SEV2"), ("150", "SEV3"), ("5", "SEV3"), ("unknown", "SEV3")])
def test_blast_radius_rows(tmp_path, users, expected):
    inc = _incident(tmp_path, category="outage", users_affected=users, data_exposed="no", regulated_data="no",
                    started_at="2026-10-01T00:00:00Z")
    r, rec, _ = _run(tmp_path, inc)
    assert r.returncode == 0 and rec["severity"] == expected


def test_custom_matrix_used_and_no_fire_exits_1(tmp_path):
    r, rec, _ = _run(tmp_path, FX / "incident-cost-spike.csv", FX / "matrix-no-baseline.csv")
    assert r.returncode == 1 and "baseline row" in r.stderr
    assert rec["severity"] is None and rec["fired_rules"] == []
    r2, rec2, _ = _run(tmp_path, FX / "incident-data-leak.csv", FX / "matrix-no-baseline.csv")
    assert r2.returncode == 0 and rec2["severity"] == "SEV1" and rec2["matrix_source"].startswith("supplied")


def test_every_category_has_a_complete_playbook(tmp_path):
    for cat in ("hallucination", "data-leak", "prompt-injection", "outage", "cost-spike", "harmful-output"):
        inc = _incident(tmp_path, category=cat, started_at="2026-10-01T00:00:00Z")
        r, rec, _ = _run(tmp_path, inc)
        assert r.returncode == 0, (cat, r.stderr)
        assert all(rec["playbook"]["sections"].get(s) for s in ("contain", "eradicate", "recover", "verify")), cat


def test_missing_and_invalid_inputs_exit_2(tmp_path):
    assert run_script(SCRIPT, "--out-dir", str(tmp_path)).returncode == 2
    assert _run(tmp_path, tmp_path / "missing.csv")[0].returncode == 2
    assert _run(tmp_path, _incident(tmp_path, category="outage"))[0].returncode == 2              # no started_at
    assert _run(tmp_path, _incident(tmp_path, category="aliens", started_at="2026-10-01T00:00:00Z"))[0].returncode == 2
    assert _run(tmp_path, _incident(tmp_path, category="outage", started_at="yesterday"))[0].returncode == 2
    assert _run(tmp_path, _incident(tmp_path, category="outage", started_at="2026-10-01T00:00:00Z",
                                    data_exposed="maybe"))[0].returncode == 2
    bad = tmp_path / "m.csv"
    bad.write_text("rule_id,conditions,severity,reason\nX,category~outage,SEV1,bad\n")
    assert _run(tmp_path, FX / "incident-cost-spike.csv", bad)[0].returncode == 2

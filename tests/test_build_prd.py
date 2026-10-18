"""Tests for build/product-spec-prd/scripts/prd.py."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/product-spec-prd/scripts/prd.py"
SK = REPO_ROOT / "skills/build/product-spec-prd"
FX = SK / "evals/fixtures"
TMPL = SK / "assets/prd-template.md"
TBD = "[TO BE BASELINED — owner: Product owner]"
SECTIONS = ["## Problem", "## Users", "## Goals", "## Non-goals", "## Metrics", "## Phases", "## Engineering handoff"]


def run(tmp_path, brief):
    out = tmp_path / "PRD.md"
    r = run_script(SCRIPT, str(brief), "--template", str(TMPL), "--out", str(out))
    return r, out.read_text(encoding="utf-8") if out.exists() else ""


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_full_brief(tmp_path):
    r, text = run(tmp_path, FX / "brief.json")
    assert r.returncode == 0, r.stderr
    assert text.startswith("# PRD — Invoice export\n\n**Invoice export: Tenant admins copy invoices")
    assert "Target Monthly active tenants using export from 0 (feature absent) to 40% of active tenants by 2027-01-31.**" in text
    for s in SECTIONS:
        assert s in text, s
    assert "| Flag | `feature.exports` |" in text
    assert "| 11 tickets in Q3 asked for an export | helpdesk report Q3 | 2026-10-01 |" in text
    assert "| Tenant admin | [TO BE BASELINED" in text
    assert "| G1 (primary) | Admins export a month of invoices in one click | Monthly active tenants using export | 0 (feature absent) | 40% of active tenants |" in text
    assert "| Support tickets asking for export | [TO BE BASELINED — owner: support lead] | -80% | helpdesk tag export |" in text
    assert "| Scheduled or emailed exports | [TO BE BASELINED" in text
    assert "| v1 | CSV export of the current filter; Admin role only; Audit entry per export | Scheduling; XLSX | 40% of active tenants exported at least once in 30 days |" in text
    assert "Constraints: No schema change to invoices; Behind feature.exports flag" in text
    assert "{{" not in text


def test_thin_brief_marks_everything_tbd(tmp_path):
    r, text = run(tmp_path, FX / "brief-thin.json")
    assert r.returncode == 0, r.stderr
    assert "brief lacked: evidence, users, goals, non_goals, metrics, phases" in r.stdout
    assert f"| G1 (primary) | {TBD} | {TBD} | {TBD} | {TBD} | {TBD} |" in text
    assert "(no evidence supplied — assumption)" in text
    assert f"| v1 | {TBD} | {TBD} | {TBD} |" in text
    assert "| Flag | `feature.invoice_export` |" in text
    assert "40%" not in text and "Tenant admin" not in text          # nothing from the other brief leaks in


def test_bad_input_exits_1(tmp_path):
    assert run(tmp_path, tmp_path / "missing.json")[0].returncode == 1
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert run(tmp_path, bad)[0].returncode == 1
    nofeature = tmp_path / "nf.json"
    nofeature.write_text(json.dumps({"problem": "x"}), encoding="utf-8")
    r, _ = run(tmp_path, nofeature)
    assert r.returncode == 1 and "feature" in r.stderr

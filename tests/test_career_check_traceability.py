"""Tests for career/resume-tailor/scripts/check_traceability.py — the TRUTH LOCK gate."""
from __future__ import annotations

import csv
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/career/resume-tailor/scripts/check_traceability.py"
MASTER = REPO_ROOT / "skills/career/resume-tailor/evals/fixtures/master-resume.md"

GOOD = """# Tailored résumé

## Summary
Technology executive with 19 years across healthcare payers and insurance. [MR-L3]

## Selected experience

### Lakeshore Health Plans — Senior Director, Enterprise Platforms (Jan 2019 – Aug 2025)
- Led the claims-platform modernization to a cloud-hosted core; auto-adjudication 71% to 88%. [MR-L12]
- Consolidated 3 ERP instances onto one SAP S/4HANA tenant; closed 2 data centers. [MR-L13]
- Owned a $38M budget with 9 direct reports and 120 staff across 4 states. [MR-L10, MR-L11]

## Skills
- SAP S/4HANA, Azure, Snowflake, Informatica [MR-L50]
"""


def run(tmp_path: Path, text: str):
    resume = tmp_path / "tailored-resume.md"
    resume.write_text(text, encoding="utf-8")
    out = tmp_path / "traceability.csv"
    r = run_script(SCRIPT, "--resume", str(resume), "--master", str(MASTER), "--out", str(out))
    rows = list(csv.DictReader(out.open(encoding="utf-8"))) if out.exists() else None
    return r, rows


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_fully_traced_resume_passes(tmp_path):
    r, rows = run(tmp_path, GOOD)
    assert r.returncode == 0, r.stderr
    assert len(rows) == 5
    assert {r_["all_ids_exist"] for r_ in rows} == {"yes"}
    assert {r_["numbers_in_bullet_found_in_cited_lines"] for r_ in rows} == {"yes"}
    assert rows[3]["cited_ids"] == "MR-L10;MR-L11"


def test_invented_dollar_figure_fails(tmp_path):
    r, rows = run(tmp_path, GOOD.replace("$38M budget", "$40M budget"))
    assert r.returncode == 1
    assert "40" in r.stderr and "TRUTH LOCK" in r.stderr
    bad = [x for x in rows if x["numbers_in_bullet_found_in_cited_lines"] == "no"]
    assert len(bad) == 1 and bad[0]["cited_ids"] == "MR-L10;MR-L11"


def test_uncited_bullet_fails(tmp_path):
    r, rows = run(tmp_path, GOOD + "- Delivered a Boomi migration for 12 partners.\n")
    assert r.returncode == 1 and "no citation" in r.stderr
    assert rows[-1]["cited_ids"] == "" and rows[-1]["all_ids_exist"] == "no"


def test_unknown_id_fails(tmp_path):
    r, rows = run(tmp_path, GOOD.replace("[MR-L50]", "[MR-L99]"))
    assert r.returncode == 1 and "MR-L99" in r.stderr
    assert rows[-1]["all_ids_exist"] == "no"


def test_percent_not_in_cited_line_fails(tmp_path):
    r, _ = run(tmp_path, GOOD.replace("71% to 88%", "71% to 92%"))
    assert r.returncode == 1 and "92" in r.stderr


def test_dry_run_template_passes_with_zero_bullets(tmp_path):
    r, rows = run(tmp_path, "## Summary\n\n## Selected experience\n\n## Skills\n<!-- dry-run: template unfilled -->\n")
    assert r.returncode == 0, r.stderr
    assert "dry-run template" in r.stdout and rows == []


def test_empty_resume_without_marker_fails(tmp_path):
    r, rows = run(tmp_path, "## Summary\n\n## Skills\n")
    assert r.returncode == 1 and rows == []


def test_missing_files_exit_1(tmp_path):
    r = run_script(SCRIPT, "--resume", str(tmp_path / "nope.md"), "--master", str(MASTER), "--out", str(tmp_path / "t.csv"))
    assert r.returncode == 1

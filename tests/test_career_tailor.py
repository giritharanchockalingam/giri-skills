"""Tests for career/resume-tailor/scripts/tailor.py."""
from __future__ import annotations

import csv
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/career/resume-tailor/scripts/tailor.py"
SK = REPO_ROOT / "skills/career/resume-tailor"
FX = SK / "evals/fixtures"


def run(tmp_path: Path, jd: Path, master: Path):
    km, gl, cb = tmp_path / "keyword-map.csv", tmp_path / "gap-list.md", tmp_path / "candidate-bullets.md"
    r = run_script(SCRIPT, "--jd", str(jd), "--master", str(master), "--keyword-map", str(km),
                   "--gap-list", str(gl), "--bullets", str(cb))
    return r, km, gl, cb


def rows(km: Path) -> dict[str, dict]:
    return {r["jd_keyword"]: r for r in csv.DictReader(km.open(encoding="utf-8"))}


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_keyword_map_cites_master_lines(tmp_path):
    r, km, gl, cb = run(tmp_path, FX / "jd.txt", FX / "master-resume.md")
    assert r.returncode == 0, r.stderr
    m = rows(km)
    assert set(m["FinOps"].values()) >= {"yes", "MR-L14", "must"}
    assert m["ERP consolidation"]["present_in_master"] == "yes" and "MR-L13" in m["ERP consolidation"]["master_line_ids"]
    assert m["$25M budget"]["present_in_master"] == "yes" and "MR-L10" in m["$25M budget"]["master_line_ids"]
    assert m["SAP S/4HANA"]["weight"] == "nice"            # "(SAP S/4HANA preferred)" inside a must line
    assert m["MBA"]["weight"] == "nice"
    assert all(r_["present_in_master"] in ("yes", "no") for r_ in m.values())
    text = cb.read_text(encoding="utf-8")
    assert "- [MR-L12] Led the claims-platform modernization from a 1990s mainframe" in text   # verbatim
    assert "## JD must-haves with support" in text


def test_unsupported_keywords_go_to_gap_list_never_invented(tmp_path):
    r, km, gl, cb = run(tmp_path, FX / "jd-cert.txt", FX / "master-resume.md")
    assert r.returncode == 0, r.stderr
    m = rows(km)
    assert m["CISSP certification"]["present_in_master"] == "no" and m["CISSP certification"]["master_line_ids"] == ""
    assert m["SOX ITGC"]["present_in_master"] == "no"
    gaps = gl.read_text(encoding="utf-8")
    assert "| CISSP certification | must |" in gaps and "SOX ITGC" in gaps
    bullets = cb.read_text(encoding="utf-8")
    assert "### CISSP" not in bullets                        # no supporting section is fabricated
    assert "- CISSP certification" in bullets                # listed as unsupported only


def test_substring_is_not_evidence(tmp_path):
    # "ERP" must not match "Enterprise"; "erp" stem must be word-bounded
    jd = tmp_path / "jd.txt"
    jd.write_text("Requirements:\n- ERP experience required\n", encoding="utf-8")
    master = tmp_path / "master.md"
    master.write_text("MR-L1 | Senior Director, Enterprise Technology\nMR-L2 | Owned three ERP instances\n", encoding="utf-8")
    r, km, gl, cb = run(tmp_path, jd, master)
    assert r.returncode == 0, r.stderr
    assert rows(km)["ERP"]["master_line_ids"] == "MR-L2"


def test_bad_input_exits_1(tmp_path):
    assert run(tmp_path, tmp_path / "missing.txt", FX / "master-resume.md")[0].returncode == 1
    no_ids = tmp_path / "plain.md"
    no_ids.write_text("Just a résumé with no line ids\n", encoding="utf-8")
    r = run(tmp_path, FX / "jd.txt", no_ids)[0]
    assert r.returncode == 1 and "MR-L" in r.stderr

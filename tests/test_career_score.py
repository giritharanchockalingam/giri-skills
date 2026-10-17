"""Tests for career/jd-fit-scorer/scripts/score.py."""
from __future__ import annotations

import json
from pathlib import Path

from conftest import copy_asset, run_script

SCRIPT = "skills/career/jd-fit-scorer/scripts/score.py"
PROFILE = "skills/career/jd-fit-scorer/assets/profile-keywords.example.txt"

JD = """Senior Director of Engineering - Acme Corp (Austin, TX)

Must have:
- 10+ years building backend systems in Python
- Led teams of 20+ engineers
- Kubernetes in production

Nice to have:
- AWS experience

We offer $250k base. On-site 3 days/week.
"""


def _jd(tmp_path: Path, text: str = JD) -> Path:
    p = tmp_path / "jd.txt"
    p.write_text(text, encoding="utf-8")
    return p


def test_help_exits_zero():
    r = run_script(SCRIPT, "--help")
    assert r.returncode == 0


def test_happy_path_scores_jd(tmp_path):
    jd = _jd(tmp_path)
    profile = copy_asset(PROFILE, tmp_path)
    r = run_script(SCRIPT, "--jd", str(jd), "--profile", str(profile))
    assert r.returncode == 0, r.stderr
    assert "verdict" in r.stdout.lower()


def test_json_output(tmp_path):
    jd = _jd(tmp_path)
    profile = copy_asset(PROFILE, tmp_path)
    r = run_script(SCRIPT, "--jd", str(jd), "--profile", str(profile), "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert "verdict" in data
    assert "buckets" in data


def test_missing_jd_file(tmp_path):
    profile = copy_asset(PROFILE, tmp_path)
    r = run_script(SCRIPT, "--jd", str(tmp_path / "nope.txt"), "--profile", str(profile))
    assert r.returncode == 2


def test_missing_profile_file(tmp_path):
    jd = _jd(tmp_path)
    r = run_script(SCRIPT, "--jd", str(jd), "--profile", str(tmp_path / "nope.txt"))
    assert r.returncode == 2

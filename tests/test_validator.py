"""Tests for scripts/validate.py (agentskills.io spec + repo rules validator)."""
from __future__ import annotations

import shutil
from pathlib import Path

from conftest import REPO_ROOT, run_script

GOOD_SKILL = """---
name: my-skill
description: A perfectly fine test skill.
---

# My Skill

Body text.
"""


def make_repo(tmp_path: Path, skills: dict[str, str], with_evals: bool = True) -> Path:
    """Build a minimal repo layout around a copy of validate.py.

    validate.py derives its repo root from its own location, so the copy
    validates the tmp layout instead of the real repo.
    """
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(REPO_ROOT / "scripts/validate.py", root / "scripts" / "validate.py")
    for dirname, md in skills.items():
        skill = root / "skills" / dirname
        (skill / "evals").mkdir(parents=True)
        (skill / "SKILL.md").write_text(md, encoding="utf-8")
        if with_evals:
            (skill / "evals" / "evals.json").write_text(
                '{"skill": "x", "cases": []}', encoding="utf-8"
            )
    return root / "scripts" / "validate.py"


def test_validator_passes_on_real_repo():
    r = run_script("scripts/validate.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Checked 40 skills, 0 errors" in r.stdout


def test_validator_rejects_bad_name(tmp_path):
    md = GOOD_SKILL.replace("name: my-skill", "name: My_Skill")
    validator = make_repo(tmp_path, {"My_Skill": md})
    r = run_script(validator)
    assert r.returncode == 1
    assert "bad name format" in r.stdout


def test_validator_rejects_name_dir_mismatch(tmp_path):
    validator = make_repo(tmp_path, {"other-dir": GOOD_SKILL})
    r = run_script(validator)
    assert r.returncode == 1
    assert "!= dir" in r.stdout


def test_validator_rejects_long_skill_md(tmp_path):
    body = "\n".join(f"filler line {i}" for i in range(600))
    md = "---\nname: my-skill\ndescription: Fine.\n---\n\n" + body + "\n"
    validator = make_repo(tmp_path, {"my-skill": md})
    r = run_script(validator)
    assert r.returncode == 1
    assert "lines (>500)" in r.stdout


def test_validator_rejects_missing_evals(tmp_path):
    validator = make_repo(tmp_path, {"my-skill": GOOD_SKILL}, with_evals=False)
    r = run_script(validator)
    assert r.returncode == 1
    assert "evals/evals.json missing" in r.stdout

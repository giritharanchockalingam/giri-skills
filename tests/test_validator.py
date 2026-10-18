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
    for name in ("validate.py", "skillmeta.py", "check_output.py"):
        shutil.copy(REPO_ROOT / "scripts" / name, root / "scripts" / name)
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
    assert "Checked 40 skills" in r.stdout and "0 errors" in r.stdout


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


AGENT_SKILL = """---
name: my-skill
description: An agent skill.
metadata:
  version: 0.2.0
  agent:
    inputs:
      - {name: data, type: csv, required: true}
    run:
      - {step: go, kind: script, cmd: "python3 -I scripts/go.py {data} --out {out}/x.json"}
    outputs:
      - {path: "{out}/x.json", checks: [exists, json]}
---

# My Skill
"""

AGENT_EVALS = """{"skill": "my-skill", "cases": [
  {"id": "c1", "prompt": "p", "expected": ["e"], "inputs": {"data": "evals/fixtures/d.csv"}, "checks": ["exit:0"]}
]}"""


def make_agent_repo(tmp_path: Path, md: str = AGENT_SKILL, evals: str = AGENT_EVALS,
                    with_script: bool = True, with_fixture: bool = True) -> Path:
    validator = make_repo(tmp_path, {"my-skill": md})
    skill = validator.parents[1] / "skills" / "my-skill"
    (skill / "evals" / "evals.json").write_text(evals, encoding="utf-8")
    if with_script:
        (skill / "scripts").mkdir()
        (skill / "scripts" / "go.py").write_text("print(1)\n", encoding="utf-8")
    if with_fixture:
        (skill / "evals" / "fixtures").mkdir()
        (skill / "evals" / "fixtures" / "d.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    return validator


def test_validator_accepts_wired_agent_skill(tmp_path):
    r = run_script(make_agent_repo(tmp_path))
    assert r.returncode == 0, r.stdout


def test_validator_requires_agent_block_at_0_2_0(tmp_path):
    md = GOOD_SKILL.replace("description: A perfectly fine test skill.",
                            "description: Fine.\nmetadata:\n  version: 0.2.0")
    r = run_script(make_agent_repo(tmp_path, md=md))
    assert r.returncode == 1
    assert "metadata.agent missing" in r.stdout


def test_validator_rejects_unknown_check(tmp_path):
    md = AGENT_SKILL.replace("checks: [exists, json]", "checks: [exists, bogus]")
    r = run_script(make_agent_repo(tmp_path, md=md))
    assert r.returncode == 1
    assert "unknown check 'bogus'" in r.stdout


def test_validator_rejects_missing_fixture(tmp_path):
    r = run_script(make_agent_repo(tmp_path, with_fixture=False))
    assert r.returncode == 1
    assert "fixture missing" in r.stdout


def test_validator_rejects_missing_script(tmp_path):
    r = run_script(make_agent_repo(tmp_path, with_script=False))
    assert r.returncode == 1
    assert "references missing file: scripts/go.py" in r.stdout


def test_validator_requires_run_step_and_check(tmp_path):
    md = AGENT_SKILL.replace("      - {step: go, kind: script, cmd: \"python3 -I scripts/go.py {data} --out {out}/x.json\"}\n", "")
    md = md.replace("checks: [exists, json]", "checks: []")
    r = run_script(make_agent_repo(tmp_path, md=md))
    assert r.returncode == 1
    assert "run has no steps" in r.stdout
    assert "outputs has no checks" in r.stdout

"""Tests for scripts/behavioral_evals.py (dry provider: no key, no network)."""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "behavioral_evals.py"
SKILLS = ["skills/career/jd-fit-scorer", "skills/career/offer-evaluator"]

TRIGGER_HEADER = ["skill", "case_id", "run", "selected", "correct"]
QUALITY_HEADER = ["skill", "case_id", "run", "mode", "expected_idx", "pass", "evidence"]


def run_eval(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    if env_extra:
        env.update(env_extra)
    cmd = [sys.executable, "-I", str(SCRIPT), *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(REPO))


def dry_run(tmp_path: Path, *extra: str):
    out = tmp_path / "out"
    args = ["all", "--provider", "dry", "--runs", "1", "--out", str(out)]
    for s in SKILLS:
        args += ["--skills", s]
    args += list(extra)
    return run_eval(*args), out


def test_dry_end_to_end_two_skills(tmp_path):
    r, out = dry_run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (out / "trigger.csv").exists()
    assert (out / "quality.csv").exists()
    assert (out / "scorecard.md").exists()
    assert (out / "raw" / "calls.jsonl").exists()


def test_csv_schemas(tmp_path):
    r, out = dry_run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    with (out / "trigger.csv").open(encoding="utf-8") as f:
        assert next(csv.reader(f)) == TRIGGER_HEADER
    with (out / "quality.csv").open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == QUALITY_HEADER
    assert len(rows) > 1  # header + data rows
    modes = {row[3] for row in rows[1:]}
    assert modes == {"without", "with"}


def test_verdict_rule_in_scorecard(tmp_path):
    # dry provider: router always answers "none" (trigger acc 0.0) and the
    # canned judge passes everything in both modes (lift 0.0) -> BOTH.
    r, out = dry_run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    scorecard = (out / "scorecard.md").read_text(encoding="utf-8")
    assert "| BOTH |" in scorecard
    for skill in ("career/jd-fit-scorer", "career/offer-evaluator"):
        assert skill in scorecard


def test_budget_abort(tmp_path):
    r, _ = dry_run(tmp_path, "--budget-usd", "0.000001")
    assert r.returncode == 1
    assert "budget" in (r.stdout + r.stderr).lower()


def test_budget_yes_overrides(tmp_path):
    r, out = dry_run(tmp_path, "--budget-usd", "0.000001", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (out / "scorecard.md").exists()


def test_key_never_appears_in_logs_or_outputs(tmp_path):
    # Built via concatenation so the literal "sk-ant-" pattern never appears
    # in this source file (keeps `git grep -i "sk-ant\|sk-"` clean); the
    # runtime values still have realistic key shapes.
    fake_anthropic = "sk-" + "ant-test-fake-key-999"
    fake_openai = "openai-test-fake-key-999"
    # run with the fake keys present in the environment
    env_extra = {"ANTHROPIC_API_KEY": fake_anthropic, "OPENAI_API_KEY": fake_openai}
    env = dict(os.environ)
    env.update(env_extra)
    args = ["all", "--provider", "dry", "--runs", "1", "--out", str(tmp_path / "out2")]
    for s in SKILLS:
        args += ["--skills", s]
    cmd = [sys.executable, "-I", str(SCRIPT), *args]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(REPO))
    assert r.returncode == 0, r.stdout + r.stderr
    assert fake_anthropic not in r.stdout
    assert fake_anthropic not in r.stderr
    assert fake_openai not in r.stdout
    for p in (tmp_path / "out2").rglob("*"):
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="ignore")
            assert fake_anthropic not in text, f"key leaked in {p}"
            assert fake_openai not in text, f"key leaked in {p}"


def test_skills_glob_filter(tmp_path):
    # regression: argparse append + list default used to match everything
    out = tmp_path / "out3"
    args = ["trigger", "--provider", "dry", "--runs", "1",
            "--skills", "skills/career/*", "--out", str(out)]
    r = run_eval(*args)
    assert r.returncode == 0, r.stdout + r.stderr
    with (out / "trigger.csv").open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert len(rows) > 1
    for row in rows[1:]:
        assert row[0] == "(negative)" or row[0].startswith("career/"), row


def test_negative_set_and_judge_prompt():
    prompts = json.loads((REPO / "evals" / "negative-set.json").read_text())["prompts"]
    assert len(prompts) == 10
    assert all(isinstance(p, str) and p.strip() for p in prompts)
    template = (REPO / "evals" / "judge-prompt.md").read_text(encoding="utf-8")
    assert "{output}" in template
    assert "{expected_items}" in template


AGENT_HEADER = ["skill", "case_id", "check", "pass", "evidence"]


def test_agent_mode_dry(tmp_path):
    out = tmp_path / "agent"
    r = run_eval("agent", "--provider", "dry", "--out", str(out),
                 "--skills", "skills/career/jd-fit-scorer", "--skills", "skills/build/safe-fix")
    assert r.returncode == 0, r.stdout + r.stderr
    with (out / "agent.csv").open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == AGENT_HEADER
    assert {row[0] for row in rows[1:]} == {"career/jd-fit-scorer"}
    assert all(row[3] == "1" for row in rows[1:]), rows
    scorecard = (out / "scorecard.md").read_text(encoding="utf-8")
    assert "| agent pass | agent verdict |" in scorecard
    assert "| career/jd-fit-scorer |  |  |  |  |  |  | 1.00 | Works |" in scorecard
    # unwired skill: present, blank agent cells, not failing
    assert "| build/safe-fix |  |  |  |  |  |  |  |  |" in scorecard
    assert (out / "runs").is_dir()


def test_agent_mode_merges_into_existing_scorecard(tmp_path):
    r, out = dry_run(tmp_path)  # trigger + quality first
    assert r.returncode == 0, r.stdout + r.stderr
    r2 = run_eval("agent", "--provider", "dry", "--out", str(out), "--skills", "skills/career/jd-fit-scorer")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    scorecard = (out / "scorecard.md").read_text(encoding="utf-8")
    line = next(l for l in scorecard.splitlines() if l.startswith("| career/jd-fit-scorer |"))
    cells = [c.strip() for c in line.strip("|").split("|")]
    assert cells[6] == "BOTH" and cells[7] == "1.00" and cells[8] == "Works"  # old verdict kept
    assert (out / "trigger.csv").exists() and (out / "quality.csv").exists()

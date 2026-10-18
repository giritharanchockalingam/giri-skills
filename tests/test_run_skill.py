"""End-to-end tests for scripts/run_skill.py with the dry provider (no key, no network).

Every wired skill is run against its own evals.json agent cases (the ones that carry
`inputs`), from a cwd outside the repo, into a tmp dir. Also: needs_input exit 2,
--assume labelling, --list / --explain, and that no API key reaches the output dir.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT

RUNNER = REPO_ROOT / "scripts" / "run_skill.py"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import skillmeta  # noqa: E402

WIRED = [
    "presales/effort-estimator", "presales/rfp-compliance-matrix",
    "presales/integration-migration-assessor", "presales/client-research-brief",
    "build/project-bootstrap", "build/supabase-schema-rls",
    "ai-platform/llm-eval-harness", "ai-platform/rag-pipeline-design",
    "ai-platform/infra-gpu-sizing", "career/jd-fit-scorer",
    "career/application-tracker", "career/offer-evaluator",
    # phases 1-2
    "presales/value-case-builder", "presales/proposal-writer", "presales/sow-drafter",
    "presales/discovery-interview", "presales/solution-architecture-doc", "presales/exec-deck-redline",
    "presales/competitive-positioning", "presales/account-plan", "presales/orals-prep",
    # phase 5
    "career/resume-tailor", "career/interview-prep", "career/outreach-and-followup",
]
FAKE_KEY = "sk-ant-TESTKEY-not-a-real-key-0000000000"


def run_skill(*args: str, cwd: Path | None = None, env_extra: dict | None = None):
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    if env_extra:
        env.update(env_extra)
    cmd = [sys.executable, "-I", str(RUNNER), *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(cwd or Path("/")))


def agent_cases(key: str):
    skill_dir = REPO_ROOT / "skills" / key
    data = json.loads((skill_dir / "evals" / "evals.json").read_text(encoding="utf-8"))
    return skill_dir, [c for c in data["cases"] if "inputs" in c]


def inputs_args(skill_dir: Path, case: dict) -> list[str]:
    args = []
    for k, v in case["inputs"].items():
        v = str(v)
        if v.startswith("evals/"):
            v = str(skill_dir / v)
        args += ["--input", f"{k}={v}"]
    return args


def happy_case(key: str):
    skill_dir, cases = agent_cases(key)
    case = next(c for c in cases if "exit:0" in c.get("checks", []))
    return skill_dir, case


# ---------------------------------------------------------------- wiring

def test_list_shows_every_wired_skill():
    r = run_skill("--list")
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith(f"{len(WIRED)} agent skills")
    for key in WIRED:
        assert key in r.stdout


@pytest.mark.parametrize("key", WIRED)
def test_explain(key):
    r = run_skill("--explain", key)
    assert r.returncode == 0, r.stderr
    assert "Inputs:" in r.stdout and "Outputs and checks:" in r.stdout


@pytest.mark.parametrize("key", WIRED)
def test_metadata_agent_is_wired(key):
    s = skillmeta.load_skill(REPO_ROOT / "skills" / key)
    a = skillmeta.agent_block(s)
    assert a and a["run"] and a["outputs"]
    assert skillmeta.version_tuple(s["metadata"]["version"]) >= (0, 2, 0)
    assert "## How to run" in s["body"]


# ---------------------------------------------------------------- dry runs

@pytest.mark.parametrize("key", WIRED)
def test_dry_run_happy_path(key, tmp_path):
    skill_dir, case = happy_case(key)
    out = tmp_path / "out"
    r = run_skill(key, *inputs_args(skill_dir, case), "--out", str(out), "--provider", "dry")
    assert r.returncode == 0, r.stdout + r.stderr
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert run["ok"] is True
    assert run["skill"] == key
    assert run["steps"] and all(s["ok"] for s in run["steps"])
    assert run["checks"] and all(c["pass"] for c in run["checks"])
    for c in run["checks"]:
        assert Path(c["path"]).exists(), c
    assert (out / "logs").is_dir()


@pytest.mark.parametrize("key", WIRED)
def test_dry_run_missing_required_input_exits_2(key, tmp_path):
    skill_dir, cases = agent_cases(key)
    case = next(c for c in cases if "exit:2" in c.get("checks", []))
    expected = next(c for c in case["checks"] if str(c).startswith("needs_input:")).split(":", 1)[1]
    out = tmp_path / "out"
    r = run_skill(key, *inputs_args(skill_dir, case), "--out", str(out))
    assert r.returncode == 2, r.stdout + r.stderr
    needs = json.loads((out / "needs_input.json").read_text(encoding="utf-8"))
    assert expected in [m["name"] for m in needs["missing"]]
    assert not (out / "run.json").exists()


def test_assume_is_labelled_in_run_json(tmp_path):
    key = "presales/effort-estimator"
    skill_dir = REPO_ROOT / "skills" / key
    out = tmp_path / "out"
    r = run_skill(key, "--input", f"wbs={skill_dir / 'evals/fixtures/wbs.csv'}",
                  "--assume", "client=Acme", "--out", str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert run["assumptions"] == {"client": "[ASSUMED: client = Acme]"}
    assert run["inputs"]["client"] == "Acme"


def test_dry_llm_step_writes_template_with_marker(tmp_path):
    skill_dir, case = happy_case("presales/effort-estimator")
    out = tmp_path / "out"
    r = run_skill("presales/effort-estimator", *inputs_args(skill_dir, case), "--out", str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    memo = (out / "estimate-memo.md").read_text(encoding="utf-8")
    assert memo.rstrip().endswith("<!-- dry-run: template unfilled -->")
    template = (skill_dir / "assets" / "estimate-summary-template.md").read_text(encoding="utf-8")
    assert memo.startswith(template.rstrip("\n"))


def test_failed_check_exits_1_with_evidence(tmp_path):
    skill_dir = REPO_ROOT / "skills" / "build" / "supabase-schema-rls"
    out = tmp_path / "out"
    r = run_skill("build/supabase-schema-rls",
                  "--input", f"migrations={skill_dir / 'evals/fixtures/migrations-bad'}",
                  "--out", str(out))
    assert r.returncode == 1
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert run["ok"] is False
    failed = [c for c in run["checks"] if not c["pass"]]
    assert failed and failed[0]["check"].startswith("cmd:")


def test_optional_input_skips_group_and_step(tmp_path):
    # effort-estimator without rates: the [--rates {rates}] group is dropped, no price.
    skill_dir = REPO_ROOT / "skills" / "presales" / "effort-estimator"
    out = tmp_path / "out"
    r = run_skill("presales/effort-estimator", "--input", f"wbs={skill_dir / 'evals/fixtures/wbs.csv'}",
                  "--input", "client=Acme", "--out", str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert "--rates" not in run["steps"][0]["cmd"]
    assert "No rate card supplied" in (out / "estimate.md").read_text(encoding="utf-8")
    # llm-eval-harness without --input outputs: the `evals` step is skipped, evals-recorded runs.
    skill_dir = REPO_ROOT / "skills" / "ai-platform" / "llm-eval-harness"
    out2 = tmp_path / "out2"
    r = run_skill("ai-platform/llm-eval-harness", "--input", f"cases={skill_dir / 'evals/fixtures/cases.csv'}",
                  "--out", str(out2))
    assert r.returncode == 0, r.stdout + r.stderr
    steps = {s["step"]: s for s in json.loads((out2 / "run.json").read_text())["steps"]}
    assert steps["evals"].get("skipped") is True
    assert steps["evals-recorded"]["ok"] and not steps["evals-recorded"].get("skipped")


def test_not_an_agent_skill_exits_3(tmp_path):
    r = run_skill("build/safe-fix", "--out", str(tmp_path / "o"))
    assert r.returncode == 3
    assert "not an agent skill" in r.stderr


def test_unknown_skill_fails_clearly(tmp_path):
    r = run_skill("presales/does-not-exist", "--out", str(tmp_path / "o"))
    assert r.returncode != 0
    assert "skill not found" in r.stderr


def test_key_never_written_to_output_dir(tmp_path):
    skill_dir, case = happy_case("career/jd-fit-scorer")
    out = tmp_path / "out"
    r = run_skill("career/jd-fit-scorer", *inputs_args(skill_dir, case), "--out", str(out),
                  env_extra={"ANTHROPIC_API_KEY": FAKE_KEY, "OPENAI_API_KEY": FAKE_KEY})
    assert r.returncode == 0, r.stdout + r.stderr
    for f in out.rglob("*"):
        if f.is_file():
            assert FAKE_KEY not in f.read_text(encoding="utf-8", errors="replace"), f
    assert FAKE_KEY not in r.stdout + r.stderr

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
    assert {row[0] for row in rows[1:]} == {"career/jd-fit-scorer", "build/safe-fix"}
    assert all(row[3] == "1" for row in rows[1:]), rows
    scorecard = (out / "scorecard.md").read_text(encoding="utf-8")
    assert "| agent pass | agent verdict |" in scorecard
    assert "| career/jd-fit-scorer |  |  |  |  |  |  | 1.00 | Works |" in scorecard
    # all 40 skills are agents now; a second wired skill must also score
    assert "| build/safe-fix |  |  |  |  |  |  | 1.00 | Works |" in scorecard
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


def _module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("behavioral_evals_mod", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return mod


def test_case_prompt_carries_the_case_inputs(tmp_path):
    mod = _module()
    (tmp_path / "evals" / "fixtures" / "repo").mkdir(parents=True)
    (tmp_path / "evals" / "fixtures" / "jd.txt").write_text("Senior Director, Apps\nMust: ERP", encoding="utf-8")
    (tmp_path / "evals" / "fixtures" / "repo" / "a.py").write_text("print(1)\n", encoding="utf-8")
    skill = {"dir": tmp_path}
    plain = {"prompt": "Score this.", "expected": ["x"]}
    assert mod.case_user_prompt(skill, plain) == "Score this."
    case = {"prompt": "Score this.", "inputs": {"jd": "evals/fixtures/jd.txt", "repo": "evals/fixtures/repo", "client": "Acme", "out": "{out}/x"}}
    text = mod.case_user_prompt(skill, case)
    assert text.startswith("Score this.\n\nInputs supplied with this request:")
    assert "Must: ERP" in text and "evals/fixtures/repo/a.py" in text and "print(1)" in text
    assert "client: Acme" in text and "out: {out}/x" in text


def test_case_prompt_caps_long_files(tmp_path):
    mod = _module()
    (tmp_path / "evals" / "fixtures").mkdir(parents=True)
    (tmp_path / "evals" / "fixtures" / "big.csv").write_text("x" * (mod.ATTACH_FILE_CHARS + 50), encoding="utf-8")
    text = mod.case_user_prompt({"dir": tmp_path}, {"prompt": "p", "inputs": {"data": "evals/fixtures/big.csv"}})
    assert "[... 50 more characters not shown]" in text


def test_quality_bar_lift_or_normalised_gain_near_a_ceiling():
    mod = _module()
    assert mod.quality_ok(0.30, 0.50)                       # lift +0.20
    assert not mod.quality_ok(0.50, 0.67)                   # lift 0.17, gain 0.34
    assert mod.quality_ok(0.88, 1.00)                       # ceiling: lift 0.12, gain 1.00, with 1.00
    assert mod.quality_ok(0.80, 0.90)                       # gain 0.50, with 0.90
    assert not mod.quality_ok(0.60, 0.75)                   # gain 0.375
    assert not mod.quality_ok(0.95, 0.90) and not mod.quality_ok(1.0, 1.0)   # never by getting worse or with no gain
    assert mod.skill_verdict(0.79, 0.30, 0.60) == "DESC" and mod.skill_verdict(0.79, 0.5, 0.5) == "BOTH"


def test_boundary_case_routes_to_its_target():
    mod = _module()
    skill = {"name": "drift-monitor"}
    assert mod.routing_target(skill, {"id": "x"}) == "drift-monitor"
    assert mod.routing_target(skill, {"id": "y", "routes_to": "ai-slo-definition"}) == "ai-slo-definition"


def test_restate_recomputes_routing_with_routes_to(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("merge_mod", REPO / "scripts" / "merge_eval_results.py")
    m = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        spec.loader.exec_module(m)
    finally:
        sys.path.pop(0)
    rows = [{"skill": "ai-platform/drift-monitor", "case_id": "prompt-latency-slo-routed", "selected": "ai-slo-definition"},
            {"skill": "ai-platform/drift-monitor", "case_id": "happy-path", "selected": "drift-monitor"},
            {"skill": "(negative)", "case_id": "neg-01", "selected": "none"}]
    assert m.trigger_accuracy(rows) == {"ai-platform/drift-monitor": 1.0}


def test_confidence_intervals_and_borderline_flag():
    mod = _module()
    lo, hi = mod.wilson_interval(14, 14)
    assert 0.78 < lo < 0.79 and hi == 1.0                     # 14/14 cannot rule out < 0.8 routing
    rows = []
    for i in range(30):                                        # 30 cases: with passes all, without fails all
        rows += [{"case_id": f"c{i}", "mode": "with", "pass": "PASS"}, {"case_id": f"c{i}", "mode": "without", "pass": "FAIL"}]
    assert mod.lift_interval(rows) == (1.0, 1.0)
    c = mod.skill_confidence([True] * 60, rows)
    assert c["confidence"] == "solid" and c["cases"] == 30
    noisy = []
    for i in range(6):                                         # 6 cases, half improve: lift 0.5 but wide
        noisy += [{"case_id": f"c{i}", "mode": "with", "pass": "PASS" if i % 2 else "FAIL"}, {"case_id": f"c{i}", "mode": "without", "pass": "FAIL"}]
    lo, hi = mod.lift_interval(noisy)
    assert lo < 0.2 < hi
    assert mod.skill_confidence([True] * 12, noisy)["confidence"] == "borderline"
    assert mod.lift_interval(noisy) == mod.lift_interval(noisy)   # fixed seed: reproducible


# ---- local reasoning models (Ollama: qwen3, gemma) -------------------------------------------------------------

def test_strip_reasoning_keeps_only_the_answer():
    mod = _module()
    assert mod.strip_reasoning("<think>pick one\nmaybe x</think>\naccount-plan") == "account-plan"
    assert mod.strip_reasoning("<thinking>a</thinking>1. PASS - ok") == "1. PASS - ok"
    assert mod.strip_reasoning("<think>ran out of tokens while thinking") == ""   # no answer at all
    assert mod.strip_reasoning(None) == "" and mod.strip_reasoning("  plain  ") == "plain"


def test_local_endpoint_detection(monkeypatch):
    mod = _module()
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert not mod.local_endpoint()
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    assert not mod.local_endpoint()
    monkeypatch.setenv("OPENAI_BASE_URL", "http://192.168.1.5:11434/v1")
    assert mod.local_endpoint()


def test_empty_replies_mark_the_run_invalid(tmp_path, monkeypatch, capsys):
    """A model that answers nothing must not produce a scorecard that reads as a verdict on the skills."""
    mod = _module()

    class Silent(mod.LLM):
        name = "dry"

        def complete(self, system, user, temperature=1.0, max_tokens=1500):
            return "<think>never finishes"

    monkeypatch.setattr(mod, "make_provider", lambda name, model: Silent())
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["behavioral_evals.py", "all", "--provider", "dry", "--runs", "1",
                                      "--skills", SKILLS[0], "--out", str(out)])
    assert mod.main() == 2
    assert "INVALID RUN" in (out / "scorecard.md").read_text(encoding="utf-8")
    assert "INVALID RUN" in capsys.readouterr().err


def test_dry_run_is_valid(tmp_path):
    proc, out = dry_run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "INVALID RUN" not in (out / "scorecard.md").read_text(encoding="utf-8")


def test_local_endpoint_projects_zero_cost(monkeypatch):
    mod = _module()
    calls = [{"system": "x" * 400, "user": "y" * 400, "max_tokens": 100}]
    monkeypatch.setenv("OPENAI_BASE_URL", "http://10.0.0.2:11434/v1")
    assert mod.project_cost(calls, "qwen3:14b", "openai")[2] == 0
    monkeypatch.delenv("OPENAI_BASE_URL")
    assert mod.project_cost(calls, "gpt-4.1-mini", "openai")[2] > 0


def test_resume_reuses_recorded_replies_and_only_asks_for_the_rest(tmp_path, monkeypatch, capsys):
    """A run that stopped part-way (out of credits) continues from its raw log without calling the model again."""
    mod = _module()
    calls = {"n": 0}

    class Counting(mod.DryLLM):
        def complete(self, system, user, temperature=1.0, max_tokens=1500):
            calls["n"] += 1
            return super().complete(system, user, temperature, max_tokens)

    monkeypatch.setattr(mod, "make_provider", lambda name, model: Counting())
    out = tmp_path / "out"
    argv = ["behavioral_evals.py", "all", "--provider", "dry", "--runs", "1", "--skills", SKILLS[0], "--out", str(out)]
    monkeypatch.setattr(sys, "argv", argv)
    assert mod.main() == 0
    first = calls["n"]
    assert first > 0
    log = out / "raw" / "calls.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines()
    # simulate the crash: keep the first 60% of the recorded replies
    keep = lines[: int(len(lines) * 0.6)]
    log.write_text("\n".join(keep) + "\n", encoding="utf-8")
    calls["n"] = 0
    monkeypatch.setattr(sys, "argv", argv + ["--resume"])
    assert mod.main() == 0
    assert 0 < calls["n"] < first, (calls["n"], first)        # only the missing replies were asked
    assert calls["n"] == first - len(keep)
    assert "resume:" in capsys.readouterr().out
    assert (out / "scorecard.md").exists()


def test_load_recorded_calls_skips_truncated_and_ambiguous(tmp_path):
    mod = _module()
    p = tmp_path / "calls.jsonl"
    rows = [
        {"mode": "router", "skill": "s", "case_id": "c", "run": 1, "judge_for": None, "output": "x"},
        {"mode": "gen_with", "skill": "s", "case_id": "c", "run": 1, "judge_for": None, "output": "y" * 8000},   # truncated
        {"mode": "gen_without", "skill": "s", "case_id": "c", "run": 1, "judge_for": None, "output": "plain answer without the skill"},
        {"mode": "judge", "skill": "s", "case_id": "c", "run": 1, "output": "1. PASS - old log", "user": "OUTPUT:\nplain answer without the skill\nITEMS"},   # old log, attributable
        {"mode": "judge", "skill": "s", "case_id": "c", "run": 1, "output": "1. FAIL - old log", "user": "OUTPUT:\nsomething never generated\nITEMS"},   # old log, ambiguous → re-ask
        {"mode": "judge", "skill": "s", "case_id": "c", "run": 1, "judge_for": "with", "output": "1. PASS - ok"},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n", encoding="utf-8")
    got = mod.load_recorded_calls(p)
    assert set(got) == {("router", "s", "c", 1, None), ("gen_without", "s", "c", 1, None), ("judge", "s", "c", 1, "without"), ("judge", "s", "c", 1, "with")}
    assert got[("judge", "s", "c", 1, "without")] == "1. PASS - old log"


def test_workers_give_identical_results_to_sequential(tmp_path):
    """Parallel calls change only the wall clock: rows are recorded in call order, judges wait for generations."""
    a, out_a = dry_run(tmp_path / "a", "--workers", "6")
    b, out_b = dry_run(tmp_path / "b")
    assert a.returncode == 0 and b.returncode == 0
    assert (out_a / "trigger.csv").read_text() == (out_b / "trigger.csv").read_text()
    assert (out_a / "quality.csv").read_text() == (out_b / "quality.csv").read_text()
    assert (out_a / "scorecard.md").read_text().splitlines()[3:] == (out_b / "scorecard.md").read_text().splitlines()[3:]


def test_local_model_name_without_base_url_is_refused_before_any_call(tmp_path):
    out = tmp_path / "out"
    proc = run_eval("all", "--provider", "openai", "--model", "qwen3:14b", "--runs", "1", "--yes", "--skills", SKILLS[0], "--out", str(out),
                    env_extra={"OPENAI_API_KEY": "ollama"})
    assert proc.returncode != 0
    assert "OPENAI_BASE_URL is not set" in proc.stderr

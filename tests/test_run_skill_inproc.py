"""Acceptance test for the runner's in-process mode (what the browser Run view uses).

For every wired skill: `--demo <skill> --provider dry` once in subprocess mode and once with
`--inproc`, then every file under both out dirs must be byte-identical. Only run.json's
timing fields and the out-dir path are normalised. Also: provider `none` skips llm steps with
a recorded reason, and `cmd:` checks report honestly when no subprocess exists.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT
from test_run_skill import WIRED

RUNNER = REPO_ROOT / "scripts" / "run_skill.py"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import check_output  # noqa: E402

TIMING_KEYS = {"duration_s"}
# git commit hashes depend on the commit second: handoff-and-thread-close builds a real throwaway repo,
# so two runs a second apart legitimately differ there and nowhere else. Normalised, not ignored.
SHA_RE = re.compile(rb"`[0-9a-f]{7,40}`|\b(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")
# skills that create a throwaway git repo: an abbreviated hash can be all digits (~1 in 25 runs), so any 7-40 hex run counts
GIT_SKILLS = {"build/handoff-and-thread-close", "build/safe-fix"}
ANY_SHA_RE = re.compile(rb"\b[0-9a-f]{7,40}\b")


def run(args: list[str], cwd: Path, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    env.pop("RUN_SKILL_INPROC", None)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, "-I", str(RUNNER), *args], capture_output=True, text=True,
                          cwd=str(cwd), env=env)


def _strip_timing(obj):
    if isinstance(obj, dict):
        return {k: _strip_timing(v) for k, v in obj.items() if k not in TIMING_KEYS}
    if isinstance(obj, list):
        return [_strip_timing(x) for x in obj]
    return obj


def normalise(path: Path, root: Path, git: bool = False) -> bytes:
    data = path.read_bytes()
    if path.name == "run.json":
        text = data.decode("utf-8").replace(str(root), "<OUT>")
        text = re.sub(r"in \d+\.\d+s\b", "in <t>s", text)  # a cmd: check's evidence may quote pytest's own timing
        return json.dumps(_strip_timing(json.loads(text)), indent=2, sort_keys=True).encode("utf-8")
    # the out-dir path appears inside some outputs (logs, run summaries): normalise it only
    data = SHA_RE.sub(b"<sha>", data.replace(str(root).encode("utf-8"), b"<OUT>"))
    data = re.sub(rb"in \d+\.\d+s\b", b"in <t>s", data)  # outputs that quote a test run's own timing (safe-fix verify.json)
    return ANY_SHA_RE.sub(b"<sha>", data) if git else data


def tree(root: Path, git: bool = False) -> dict[str, bytes]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and ".git" not in p.parts:
            out[str(p.relative_to(root))] = normalise(p, root, git)
    return out


@pytest.mark.parametrize("key", WIRED)
def test_inproc_outputs_are_byte_identical(key: str, tmp_path: Path):
    a, b = tmp_path / "sub", tmp_path / "inproc"
    ra = run(["--demo", key, "--provider", "dry", "--out", str(a)], cwd=tmp_path)
    rb = run(["--demo", key, "--provider", "dry", "--out", str(b), "--inproc"], cwd=tmp_path)
    assert ra.returncode == rb.returncode, f"exit codes differ: {ra.returncode} vs {rb.returncode}\n{ra.stderr}\n{rb.stderr}"
    ta, tb = tree(a, key in GIT_SKILLS), tree(b, key in GIT_SKILLS)
    assert set(ta) == set(tb), f"file sets differ: only subprocess={sorted(set(ta) - set(tb))} only inproc={sorted(set(tb) - set(ta))}"
    for rel in ta:
        assert ta[rel] == tb[rel], f"{key}: {rel} differs between subprocess and in-process runs"
    # the runner's own summary line must match too (it is what the browser log shows)
    strip = lambda s: re.sub(r"/\S*(sub|inproc)", "<OUT>", s)  # noqa: E731
    assert strip(ra.stdout) == strip(rb.stdout)


def test_inproc_env_var_equals_flag(tmp_path: Path):
    a, b = tmp_path / "flag", tmp_path / "env"
    run(["--demo", "presales/value-case-builder", "--out", str(a), "--inproc"], cwd=tmp_path)
    run(["--demo", "presales/value-case-builder", "--out", str(b)], cwd=tmp_path, env_extra={"RUN_SKILL_INPROC": "1"})
    assert tree(a) == tree(b)


def test_provider_none_skips_llm_step_and_fails_its_checks(tmp_path: Path):
    out = tmp_path / "o"
    r = run(["--demo", "career/resume-tailor", "--provider", "none", "--out", str(out), "--inproc"], cwd=tmp_path)
    assert r.returncode == 1
    run_json = json.loads((out / "run.json").read_text(encoding="utf-8"))
    draft = next(s for s in run_json["steps"] if s["step"] == "draft")
    assert draft["skipped"] is True and draft["ok"] is False
    assert draft["skipped_reason"] == "no provider key (LLM step not run)"
    assert not (out / "tailored-resume.md").exists()
    resume_checks = [c for c in run_json["checks"] if c["path"].endswith("tailored-resume.md")]
    assert resume_checks and all(c["pass"] is False for c in resume_checks)
    assert run_json["ok"] is False and run_json["model"] == ""


def test_jsbridge_without_callback_is_no_provider_key(tmp_path: Path):
    out = tmp_path / "o"
    r = run(["--demo", "career/resume-tailor", "--provider", "jsbridge", "--out", str(out)], cwd=tmp_path)
    assert r.returncode == 1
    draft = next(s for s in json.loads((out / "run.json").read_text())["steps"] if s["step"] == "draft")
    assert draft["skipped"] is True and "no provider key" in draft["skipped_reason"]


def test_jsbridge_callback_is_used(tmp_path: Path, monkeypatch):
    import behavioral_evals
    calls = []

    def cb(system, user, model, max_tokens, temperature):
        calls.append((model, max_tokens, temperature))
        assert "Template" in user and "Big 4" in system
        return "# Summary\nfilled"
    monkeypatch.setattr(behavioral_evals, "JS_LLM_CALLBACK", cb)
    p = behavioral_evals.make_provider("jsbridge", "m-test")
    assert p.complete("Big 4 system", "## Template", temperature=0.2, max_tokens=10) == "# Summary\nfilled"
    assert calls == [("m-test", 10, 0.2)]


def test_cmd_check_reports_skipped_when_no_subprocess(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUN_SKILL_INPROC", "1")
    monkeypatch.setenv("RUN_SKILL_NO_SUBPROCESS", "1")
    f = tmp_path / "x.txt"
    f.write_text("hi")
    r = check_output.run_check('cmd:"python3 -m pytest -q"', str(f), mode="real", cwd=str(tmp_path))
    assert r["pass"] is False and r["evidence"] == "skipped: subprocess unavailable in-process"
    # a plain python script still runs in-process
    script = tmp_path / "ok.py"
    script.write_text("import sys; print('fine'); sys.exit(0)")
    r = check_output.run_check(f'cmd:"python3 -I {script} {{path}}"', str(f), mode="real", cwd=str(tmp_path))
    assert r["pass"] is True and r["evidence"] == "exit 0: fine"


def test_run_inproc_matches_interpreter_exit_semantics(tmp_path: Path):
    s = tmp_path / "s.py"
    s.write_text("import sys\nprint('out', sys.argv[1:])\nsys.exit('usage: bad')\n")
    code, out, err = check_output.run_inproc([str(s), "a", "b"], tmp_path)
    assert (code, out, err) == (1, "out ['a', 'b']\n", "usage: bad\n")
    s.write_text("raise ValueError('boom')\n")
    code, out, err = check_output.run_inproc([str(s)], tmp_path)
    assert code == 1 and "ValueError: boom" in err
    s.write_text("import os; print(os.getcwd())\n")
    code, out, _ = check_output.run_inproc([str(s)], tmp_path)
    assert code == 0 and out.strip() == str(tmp_path)
    assert "s" not in sys.modules  # nothing leaks from the script run

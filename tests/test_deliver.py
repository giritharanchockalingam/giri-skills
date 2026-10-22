"""scripts/deliver.py — dry end-to-end runs of the pipeline templates on the fixture repo (no model, no network)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import REPO_ROOT, run_script

SCRIPT = "scripts/deliver.py"
FIX = REPO_ROOT / "tests" / "fixtures"
REPO = FIX / "delivery-repo"
BRIEF = FIX / "delivery-build" / "brief.json"
PATCH = FIX / "delivery-build" / "diff.patch"
RISKY_PATCH = REPO_ROOT / "skills" / "build" / "code-review-runner" / "evals" / "fixtures" / "change-risky.patch"
REQUEST = "Export orders as CSV"
STAGES = ["requirements", "architecture", "build", "evaluate", "deploy", "operate"]


def deliver(out: Path, *extra: str, pipeline: str = "feature-delivery", request: str = REQUEST, repo: Path = REPO,
            brief: Path | None = BRIEF):
    args = [pipeline, "--repo", str(repo), "--request", request, "--out", str(out), "--provider", "dry", "--dry"]
    if brief:
        args += ["--brief", str(brief)]
    return run_script(SCRIPT, *args, *extra)


def run_json(out: Path) -> dict:
    return json.loads((out / "run.json").read_text())


def stage_status(out: Path) -> dict:
    return {s["id"]: s["status"] for s in run_json(out)["stages"]}


@pytest.fixture(scope="module")
def happy(tmp_path_factory):
    out = tmp_path_factory.mktemp("happy")
    r = deliver(out, "--builder", "manual", "--patch", str(PATCH), "--approve-all")
    return out, r


def test_happy_path_every_stage_passes(happy):
    out, r = happy
    assert r.returncode == 0, r.stdout + r.stderr
    assert "6 stages passed" in r.stdout
    assert stage_status(out) == {s: "passed" for s in STAGES}
    rj = run_json(out)
    assert rj["status"] == "passed" and rj["exit_code"] == 0 and rj["dry"] is True
    assert rj["stack_profile"]["framework"] == "nextjs" and rj["stack_profile"]["flavour"] == "js"


def test_evidence_md_has_one_row_per_stage(happy):
    out, _ = happy
    md = (out / "evidence" / "EVIDENCE.md").read_text()
    rows = [ln for ln in md.splitlines() if ln.startswith("| ") and not ln.startswith("| Stage")]
    assert [r.split("|")[1].strip() for r in rows] == STAGES
    assert "| Stage | Role | Gate | Verdict | Evidence |" in md
    assert md.count("PASS") >= 5 and "RECORDED" in md     # deploy gate is external: recorded, not judged
    assert str(out) not in md                              # relative links only: the bundle travels


def test_evidence_bundle_layout_and_hashes(happy):
    out, _ = happy
    ev = out / "evidence"
    assert (ev / "stack-profile.json").is_file()
    for n, sid in enumerate(STAGES, 1):
        gate = json.loads((ev / f"{n:02d}-{sid}" / "gate.json").read_text())
        assert set(gate) == {"verdict", "kind", "detail", "role", "approved_by", "at"}
        assert gate["verdict"] in ("pass", "recorded")
    assert (ev / "02-architecture" / "plan-approval" / "approval.json").is_file()
    assert (ev / "03-build" / "code" / "diff.patch").read_text() == PATCH.read_text()
    assert json.loads((ev / "05-deploy" / "pr" / "pr.json").read_text())["dry"] is True
    files = run_json(out)["files"]
    assert "evidence/EVIDENCE.md" in files and "evidence/stack-profile.json" in files and "build/diff.patch" in files
    assert all(len(h) == 64 for h in files.values())
    for step in ("brief", "prd"):
        assert any(k.startswith(f"evidence/01-requirements/{step}/") for k in files)


def test_compose_steps_derive_spec_and_feature_from_real_outputs(happy):
    out, _ = happy
    ev = out / "evidence"
    spec = (ev / "02-architecture" / "spec" / "spec.md").read_text()
    assert "## Order CSV export" in spec and "(files: lib/orders.js,app/api/orders/export/route.js)" in spec
    assert json.loads((ev / "02-architecture" / "spec" / "spec.json").read_text())["section"] == "Order CSV export"
    tasks = (ev / "02-architecture" / "plan" / "tasks.csv").read_text()
    assert "T1,CSV export of the current order list" in tasks
    feature = (ev / "03-build" / "feature" / "feature.md").read_text()
    assert feature.startswith("# Order CSV export\n") and feature.count("\n- ") == 3
    fj = json.loads((ev / "03-build" / "feature" / "feature.json").read_text())
    assert fj == {"title": "Order CSV export", "files": "lib/orders.js,app/api/orders/export/route.js", "criteria": 3, "files_source": "tasks.csv"}
    report = json.loads((ev / "03-build" / "tests" / "scaffold-report.json").read_text())
    assert "tests/unit/lib-orders.test.js" in report["written"]


def test_manual_builder_records_the_diff_and_files_changed(happy):
    out, _ = happy
    fc = json.loads((out / "evidence" / "03-build" / "code" / "files-changed.json").read_text())
    assert fc["files"] == ["app/api/orders/export/route.js", "lib/orders.js", "tests/unit/lib/orders.test.js"]
    assert fc["plan_files"] == ["app/api/orders/export/route.js", "lib/orders.js"] and fc["outside_plan"] == []
    summary = (out / "evidence" / "03-build" / "code" / "agent-summary.md").read_text()
    assert "builder: manual" in summary and "applied to the dry working copy" in summary
    assert (out / "repo" / "app" / "api" / "orders" / "export" / "route.js").is_file()   # landed on the copy only
    assert not (REPO / "app" / "api" / "orders").exists()                                 # the fixture is untouched


def test_fixture_repo_is_never_modified(happy):
    assert not (REPO / "tests").exists() and not (REPO / ".github" / "ci-additions.yml").exists()
    assert not (REPO / ".git").exists()


def test_dry_run_is_deterministic(happy, tmp_path):
    out1, _ = happy
    out2 = tmp_path / "again"
    r = deliver(out2, "--builder", "manual", "--patch", str(PATCH), "--approve-all")
    assert r.returncode == 0
    assert (out1 / "evidence" / "EVIDENCE.md").read_text() == (out2 / "evidence" / "EVIDENCE.md").read_text()
    assert run_json(out1)["run_id"] == run_json(out2)["run_id"]
    for rel in ("01-requirements/prd/prd-final.md", "02-architecture/plan/plan.md", "03-build/feature/feature.md",
                "04-evaluate/review/review.md", "04-evaluate/ui/report.md", "05-deploy/ci/ci-report.md"):
        assert (out1 / "evidence" / rel).read_text() == (out2 / "evidence" / rel).read_text(), rel


def test_gate_failure_stops_with_exit_1_and_evidence_so_far(tmp_path):
    out = tmp_path / "gate"
    r = deliver(out, "--builder", "manual", "--patch", str(RISKY_PATCH), "--approve-all")
    assert r.returncode == 1
    assert "stopped at stage 'evaluate' (failed)" in r.stdout
    st = stage_status(out)
    assert st == {"requirements": "passed", "architecture": "passed", "build": "passed", "evaluate": "failed"}
    gate = json.loads((out / "evidence" / "04-evaluate" / "gate.json").read_text())
    assert gate["verdict"] == "fail" and 'Verdict: **PASS**' in gate["detail"] and "[fail]" in gate["detail"]
    md = (out / "evidence" / "EVIDENCE.md").read_text()
    assert "| evaluate | ai-quality-red-team | all | FAIL |" in md and "| deploy" not in md


def test_approval_blocks_with_exit_3(tmp_path):
    out = tmp_path / "appr"
    r = deliver(out, "--builder", "none")
    assert r.returncode == 3
    need = json.loads((out / "needs_approval.json").read_text())
    assert need["stage"] == "architecture" and need["step"] == "plan-approval" and need["role"] == "ai-solution-architect"
    assert "evidence/02-architecture/plan/plan.md" in need["review"]
    assert stage_status(out) == {"requirements": "passed", "architecture": "awaiting_approval"}
    assert json.loads((out / "evidence" / "02-architecture" / "gate.json").read_text())["verdict"] == "pending"


def test_builder_none_blocks_with_exit_4(tmp_path):
    out = tmp_path / "builder"
    r = deliver(out, "--builder", "none", "--approve-all")
    assert r.returncode == 4
    need = json.loads((out / "needs_builder.json").read_text())
    assert need["stage"] == "build" and need["step"] == "code" and need["expected"] == str(out / "build" / "diff.patch")
    assert need["plan"].endswith("02-architecture/plan/plan.md") and need["tests"].endswith("03-build/tests/test-plan.md")
    assert any(c.endswith("shared/stack-conventions.md") for c in need["constraints"])
    assert stage_status(out)["build"] == "awaiting_builder"
    steps = {s["id"]: s["status"] for s in run_json(out)["stages"][-1]["steps"]}
    assert steps == {"feature": "ok", "tests": "ok", "code": "awaiting_builder"}


def test_resume_continues_from_the_first_incomplete_stage(tmp_path):
    out = tmp_path / "resume"
    assert deliver(out, "--builder", "none").returncode == 3                       # blocked at the approval
    approvals = tmp_path / "approvals.json"
    approvals.write_text(json.dumps({"approvals": [{"step": "plan-approval", "by": "giri", "note": "plan ok"}]}))
    r = deliver(out, "--builder", "none", "--resume", "--approvals", str(approvals))
    assert r.returncode == 4                                                           # now blocked at the builder
    ap = json.loads((out / "evidence" / "02-architecture" / "plan-approval" / "approval.json").read_text())
    assert ap["by"] == "giri" and ap["status"] == "approved"
    (out / "build").mkdir(exist_ok=True)
    shutil.copy(PATCH, out / "build" / "diff.patch")
    r = deliver(out, "--builder", "none", "--resume", "--approvals", str(approvals))
    assert r.returncode == 0, r.stdout + r.stderr
    rj = run_json(out)
    assert rj["resumed"] is True and stage_status(out) == {s: "passed" for s in STAGES}
    build = next(s for s in rj["stages"] if s["id"] == "build")
    reused = {t["id"]: t.get("resumed", False) for t in build["steps"]}
    assert reused == {"feature": True, "tests": True, "code": False, "conventions": False}
    assert len([ln for ln in (out / "evidence" / "EVIDENCE.md").read_text().splitlines() if ln.startswith("| ") and "Stage" not in ln]) == 6


def test_run_json_refuses_a_second_run_without_resume(tmp_path):
    out = tmp_path / "twice"
    assert deliver(out, "--builder", "none").returncode == 3
    r = deliver(out, "--builder", "none")
    assert r.returncode == 2 and "--resume" in r.stderr


def test_missing_required_input_exits_2_with_needs_input(tmp_path):
    out = tmp_path / "noreq"
    r = run_script(SCRIPT, "feature-delivery", "--repo", str(REPO), "--out", str(out), "--dry", "--builder", "none")
    assert r.returncode == 2 and "needs input: --request" in r.stderr
    assert json.loads((out / "needs_input.json").read_text())["missing"][0]["name"] == "request"
    r = run_script(SCRIPT, "no-such-pipeline", "--repo", str(REPO), "--request", "x", "--out", str(out))
    assert r.returncode != 0 and "pipeline not found" in r.stderr


def test_request_only_run_without_a_brief_stops_honestly_when_no_files_are_named(tmp_path):
    out = tmp_path / "nobrief"
    r = deliver(out, "--builder", "manual", "--patch", str(PATCH), "--approve-all", brief=None)
    assert r.returncode == 1, r.stdout + r.stderr
    brief = json.loads((out / "evidence" / "01-requirements" / "brief" / "brief.json").read_text())
    assert brief["feature"] == REQUEST and brief["problem"] == REQUEST and "_composed" in brief
    fj = json.loads((out / "evidence" / "03-build" / "feature" / "feature.json").read_text())
    assert fj["files"] == "" and fj["files_source"].startswith("none")
    # test-strategy-tdd needs files the plan did not name: the step says so instead of guessing
    tests_step = next(t for s in run_json(out)["stages"] if s["id"] == "build" for t in s["steps"] if t["id"] == "tests")
    assert tests_step["status"] == "failed" and "needs input ['files']" in tests_step["error"]
    assert stage_status(out)["build"] == "failed"


def test_claude_code_builder_without_claude_on_path_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    out = tmp_path / "cc"
    r = deliver(out, "--builder", "claude-code", "--approve-all")
    assert r.returncode == 1
    code = next(t for s in run_json(out)["stages"] if s["id"] == "build" for t in s["steps"] if t["id"] == "code")
    assert code["status"] == "failed" and "`claude` is not on PATH" in code["error"]


def test_greenfield_template_dry_runs_green(tmp_path):
    out = tmp_path / "green"
    r = deliver(out, "--builder", "manual", "--patch", str(FIX / "delivery-build" / "greenfield-diff.patch"),
                "--approve-all", "--input", "name=harbourline", pipeline="greenfield-app",
                request="A portal to track harbour orders", repo=tmp_path / "new-app")
    assert r.returncode == 0, r.stdout + r.stderr
    assert stage_status(out) == {s: "passed" for s in ["bootstrap"] + STAGES}
    assert (out / "repo" / "docs" / "SPEC.md").is_file() and (out / "repo" / "app" / "page.js").is_file()
    assert not (tmp_path / "new-app").exists()      # dry: the real target directory is never created
    md = (out / "evidence" / "EVIDENCE.md").read_text()
    assert "| bootstrap | full-stack-engineer | output | PASS |" in md

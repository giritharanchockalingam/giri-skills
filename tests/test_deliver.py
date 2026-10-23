"""scripts/deliver.py — dry end-to-end runs of the pipeline templates on the fixture repo (no model, no network)."""
from __future__ import annotations

import hashlib
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
FILES = FIX / "delivery-build" / "files.txt"
PLAN_DIR = FIX / "delivery-build" / "plan"            # the architect's refined plan.md + tasks.csv (fictional)
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
    assert not (out / "needs_builder.json").exists() and not (out / "wiring_error.json").exists()


def test_files_step_is_derived_from_tasks_csv_when_every_task_names_files(happy):
    """The plan (spec-to-plan with repo=$repo) names files for every task: files.txt is derived, the builder is not asked."""
    out, _ = happy
    ev = out / "evidence"
    txt = (ev / "03-build" / "files" / "files.txt").read_text()
    assert txt.startswith("# derived by deliver.py from tasks.csv") and txt.splitlines()[1:] == ["lib/orders.js", "app/api/orders/export/route.js"]
    fj = json.loads((ev / "03-build" / "files" / "files.json").read_text())
    assert fj["derived"] is True and fj["source"] == "tasks.csv"
    assert fj["modify"] == ["lib/orders.js"] and fj["create"] == ["app/api/orders/export/route.js"]   # checked against the checkout
    build = next(s for s in run_json(out)["stages"] if s["id"] == "build")
    steps = {t["id"]: t for t in build["steps"]}
    assert list(steps) == ["feature", "files", "tests", "code", "conventions"]
    assert steps["files"]["status"] == "ok" and steps["files"]["files_source"] == "tasks.csv" and steps["files"]["files"] == 2
    assert steps["tests"]["inputs"]["files"] == "lib/orders.js,app/api/orders/export/route.js"        # $steps.files:files.txt#csv
    assert steps["code"]["allowed_files"] == ["lib/orders.js", "app/api/orders/export/route.js"]       # the code step is constrained by files.txt
    assert "03-build/files/files.txt" in build["evidence_files"]
    assert "evidence/03-build/files/files.txt" in run_json(out)["files"]


def test_plan_refine_is_skipped_when_the_scaffold_is_already_complete(happy):
    """The brief's tasks carry accept/test/files: spec-to-plan's scaffold has no TBD cell, so the architect is not
    asked — the step records `skipped`, copies the scaffold in as the plan, and the gate passes on it."""
    out, _ = happy
    ev = out / "evidence"
    arch = next(s for s in run_json(out)["stages"] if s["id"] == "architecture")
    steps = {t["id"]: t for t in arch["steps"]}
    assert list(steps) == ["spec", "plan", "plan-refine", "plan-approval"]
    assert steps["plan-refine"]["status"] == "ok" and steps["plan-refine"]["skipped"] is True
    assert steps["plan-refine"]["plan_source"] == "scaffold" and steps["plan-refine"]["tasks"] == 3 and steps["plan-refine"]["gaps"] == 0
    for f in ("plan.md", "tasks.csv"):
        assert (ev / "02-architecture" / "plan-refine" / f).read_text() == (ev / "02-architecture" / "plan" / f).read_text()
    pr = json.loads((ev / "02-architecture" / "plan-refine" / "plan-refine.json").read_text())
    assert pr["skipped"] is True and pr["source"] == "scaffold" and pr["gaps"] == []
    gate = json.loads((ev / "02-architecture" / "gate.json").read_text())
    assert gate["kind"] == "all" and gate["verdict"] == "pass"
    for check in ("csv_rows:files!empty", "csv_rows:acceptance!empty", "csv_rows:files!tbd", "csv_rows:acceptance!tbd", "csv_rows:test!tbd"):
        assert f"[pass] tasks.csv: {check}" in gate["detail"], check
    assert gate["detail"].endswith("[pass] approved by --approve-all")
    assert {"02-architecture/plan/tasks.csv", "02-architecture/plan-refine/plan.md", "02-architecture/plan-refine/tasks.csv"} <= set(arch["evidence_files"])
    build = next(s for s in run_json(out)["stages"] if s["id"] == "build")
    files = next(t for t in build["steps"] if t["id"] == "files")
    assert files["files_source"] == "tasks.csv"                                                        # derived from the refined tasks.csv
    assert not (out / "needs_builder.json").exists()


def test_scaffold_with_tbd_cells_stops_at_plan_refine_for_the_architect(tmp_path):
    """Request only, no brief: spec-to-plan's scaffold is all `[TO BE BASELINED]` — the first real run's plan. The run
    stops at plan-refine (exit 4) naming both files the architect must write; nothing is put in front of an approver."""
    out = tmp_path / "tbd"
    r = deliver(out, "--builder", "none", "--approve-all", brief=None)
    assert r.returncode == 4, r.stdout + r.stderr
    assert "stopped at stage 'architecture' (awaiting_builder): needs the architect (plan-refine)" in r.stdout
    need = json.loads((out / "needs_builder.json").read_text())
    assert need["stage"] == "architecture" and need["step"] == "plan-refine" and need["role"] == "architect" and need["builder"] == "none"
    assert need["produce"] == ["plan.md", "tasks.csv"]
    assert need["expected"] == {"plan.md": str(out / "evidence" / "02-architecture" / "plan-refine" / "plan.md"),
                                "tasks.csv": str(out / "evidence" / "02-architecture" / "plan-refine" / "tasks.csv")}
    assert need["alternative"] == {"plan.md": str(out / "build" / "plan" / "plan.md"), "tasks.csv": str(out / "build" / "plan" / "tasks.csv")}
    assert need["plan"].endswith("02-architecture/plan/plan.md") and need["tasks"].endswith("02-architecture/plan/tasks.csv")
    assert need["prd"].endswith("01-requirements/prd/prd-final.md") and need["request"] == REQUEST
    assert need["why"].startswith("the scaffold plan is not a plan yet: T1: acceptance is [TO BE BASELINED")
    assert "T1: files is [TO BE BASELINED" in need["why"] and "T1: test is [TO BE BASELINED" in need["why"]
    assert "nothing invented beyond what the PRD and the request state" in need["rule"] and "--plan <dir>" in need["how"]
    assert "id,task,acceptance,test,rollback,files,size,repo_check" in need["format"]
    assert stage_status(out) == {"requirements": "passed", "architecture": "awaiting_builder"}
    steps = {s["id"]: s["status"] for s in run_json(out)["stages"][-1]["steps"]}
    assert steps == {"spec": "ok", "plan": "ok", "plan-refine": "awaiting_builder"}
    gate = json.loads((out / "evidence" / "02-architecture" / "gate.json").read_text())
    assert gate["verdict"] == "pending" and "waiting for the architect" in gate["detail"] and "plan-refine" in gate["detail"]
    assert not (out / "needs_approval.json").exists() and not (out / "evidence" / "02-architecture" / "plan-approval" / "approval.json").exists()
    r = deliver(tmp_path / "manual", "--builder", "manual", "--patch", str(PATCH), "--approve-all", brief=None)
    assert r.returncode == 4 and json.loads((tmp_path / "manual" / "needs_builder.json").read_text())["step"] == "plan-refine"   # manual: same stop


def test_resume_after_the_architect_drops_the_refined_plan_continues_to_approval(tmp_path):
    out = tmp_path / "refined"
    assert deliver(out, "--builder", "none", brief=None).returncode == 4
    for f in ("plan.md", "tasks.csv"):                                             # the architect writes both files in place
        shutil.copy(PLAN_DIR / f, out / "evidence" / "02-architecture" / "plan-refine" / f)
    r = deliver(out, "--builder", "none", "--resume", brief=None)
    assert r.returncode == 3, r.stdout + r.stderr                                  # the plan passed the gate checks: now the approval
    assert not (out / "needs_builder.json").exists()                               # the stop it answered is gone
    need = json.loads((out / "needs_approval.json").read_text())
    assert need["step"] == "plan-approval" and "evidence/02-architecture/plan-refine/tasks.csv" in need["review"]
    arch = next(s for s in run_json(out)["stages"] if s["id"] == "architecture")
    steps = {t["id"]: t for t in arch["steps"]}
    assert [(k, v["status"]) for k, v in steps.items()] == [("spec", "ok"), ("plan", "ok"), ("plan-refine", "ok"), ("plan-approval", "awaiting_approval")]
    assert steps["spec"].get("resumed") is True and steps["plan"].get("resumed") is True and "resumed" not in steps["plan-refine"]
    assert steps["plan-refine"]["plan_source"] == "architect" and steps["plan-refine"]["skipped"] is False and steps["plan-refine"]["gaps"] == 0
    (out / "build").mkdir(exist_ok=True)
    shutil.copy(PATCH, out / "build" / "diff.patch")
    r = deliver(out, "--builder", "none", "--resume", "--approve-all", brief=None)
    assert r.returncode == 0, r.stdout + r.stderr
    assert stage_status(out) == {s: "passed" for s in STAGES}
    fj = json.loads((out / "evidence" / "03-build" / "files" / "files.json").read_text())
    assert fj["derived"] is True and fj["files"] == ["lib/orders.js", "app/api/orders/export/route.js"]   # files.txt from the refined tasks.csv
    assert "Content-Disposition" in (out / "evidence" / "03-build" / "feature" / "feature.md").read_text()


def test_gate_refuses_a_refined_tasks_csv_that_still_has_tbd_cells(tmp_path):
    """The architect hands back the scaffold unchanged: the gate refuses it with the rows and columns named, before
    anyone is asked to approve — exit 1, no needs_approval.json, no approval.json."""
    out = tmp_path / "still-tbd"
    assert deliver(out, "--builder", "none", "--approve-all", brief=None).returncode == 4
    for f in ("plan.md", "tasks.csv"):
        shutil.copy(out / "evidence" / "02-architecture" / "plan" / f, out / "evidence" / "02-architecture" / "plan-refine" / f)
    r = deliver(out, "--builder", "none", "--resume", "--approve-all", brief=None)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "stopped at stage 'architecture' (failed): gate failed" in r.stdout
    gate = json.loads((out / "evidence" / "02-architecture" / "gate.json").read_text())
    assert gate["verdict"] == "fail"
    assert "[fail] tasks.csv: csv_rows:acceptance!tbd — 1 of 1 rows still [TO BE BASELINED] in 'acceptance' (rows ['T1'])" in gate["detail"]
    assert "[fail] tasks.csv: csv_rows:files!tbd — 1 of 1 rows still [TO BE BASELINED] in 'files' (rows ['T1'])" in gate["detail"]
    assert "[fail] tasks.csv: csv_rows:test!tbd" in gate["detail"] and "[fail] not approved" in gate["detail"]
    steps = {t["id"]: t for t in run_json(out)["stages"][-1]["steps"]}
    assert steps["plan-refine"]["status"] == "ok" and steps["plan-refine"]["gaps"] == 3
    assert steps["plan-approval"]["status"] == "failed" and steps["plan-approval"]["error"].startswith("not submitted for approval — the stage gate refuses the outputs")
    assert not (out / "needs_approval.json").exists() and not (out / "needs_builder.json").exists()
    assert not (out / "evidence" / "02-architecture" / "plan-approval" / "approval.json").exists()
    assert stage_status(out) == {"requirements": "passed", "architecture": "failed"}
    assert "| architecture | ai-solution-architect | all | FAIL |" in (out / "evidence" / "EVIDENCE.md").read_text()


def test_plan_dir_supplies_the_refined_plan_end_to_end(tmp_path):
    out = tmp_path / "plan-dir"
    r = deliver(out, "--builder", "manual", "--plan", str(PLAN_DIR), "--patch", str(PATCH), "--approve-all", brief=None)
    assert r.returncode == 0, r.stdout + r.stderr
    assert stage_status(out) == {s: "passed" for s in STAGES}
    ev = out / "evidence"
    for f in ("plan.md", "tasks.csv"):
        assert (out / "build" / "plan" / f).read_text() == (PLAN_DIR / f).read_text()
        assert (ev / "02-architecture" / "plan-refine" / f).read_text() == (PLAN_DIR / f).read_text()
    assert "TO BE BASELINED" in (ev / "02-architecture" / "plan" / "tasks.csv").read_text()          # the scaffold stays as evidence of what the skill wrote
    steps = {t["id"]: t for t in next(s for s in run_json(out)["stages"] if s["id"] == "architecture")["steps"]}
    assert steps["plan-refine"]["plan_source"] == "architect" and steps["plan-refine"]["skipped"] is False
    fj = json.loads((ev / "03-build" / "files" / "files.json").read_text())
    assert fj["derived"] is True and fj["modify"] == ["lib/orders.js"] and fj["create"] == ["app/api/orders/export/route.js"]
    assert "build/plan/tasks.csv" in run_json(out)["files"]
    r = deliver(tmp_path / "half", "--builder", "manual", "--plan", str(tmp_path), "--patch", str(PATCH), brief=None)
    assert r.returncode == 2 and "lacks plan.md, tasks.csv" in r.stderr


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
    assert "## Order CSV export" in spec and "; files: lib/orders.js,app/api/orders/export/route.js)" in spec
    assert "tasks from brief.tasks" in spec and "(accept: GET /api/orders/export answers 200" in spec   # the brief's tasks carry accept/test/rollback/files
    assert json.loads((ev / "02-architecture" / "spec" / "spec.json").read_text())["section"] == "Order CSV export"
    tasks = (ev / "02-architecture" / "plan" / "tasks.csv").read_text()
    assert "T1,CSV export of the current order list" in tasks and "TO BE BASELINED" not in tasks
    feature = (ev / "03-build" / "feature" / "feature.md").read_text()
    assert feature.startswith("# Order CSV export\n") and feature.count("\n- ") == 3
    assert "- GET /api/orders/export answers 200 with text/csv" in feature                              # criteria are the acceptance cells, not the task titles
    fj = json.loads((ev / "03-build" / "feature" / "feature.json").read_text())
    assert fj == {"title": "Order CSV export", "files": "lib/orders.js,app/api/orders/export/route.js", "criteria": 3, "files_source": "tasks.csv"}
    report = json.loads((ev / "03-build" / "tests" / "scaffold-report.json").read_text())
    assert "tests/unit/lib-orders.test.js" in report["written"]


def test_manual_builder_records_the_diff_and_files_changed(happy):
    out, _ = happy
    fc = json.loads((out / "evidence" / "03-build" / "code" / "files-changed.json").read_text())
    assert fc["files"] == ["app/api/orders/export/route.js", "lib/orders.js", "tests/unit/lib/orders.test.js"]
    assert fc["plan_files"] == ["lib/orders.js", "app/api/orders/export/route.js"] and fc["outside_plan"] == []
    assert fc["plan_files_source"] == "files.txt"                                           # the code step is constrained by files.txt
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
    assert need["plan"].endswith("02-architecture/plan-refine/plan.md") and need["tests"].endswith("03-build/tests/test-plan.md")
    assert need["files"].endswith("03-build/files/files.txt") and need["allowed_files"] == ["lib/orders.js", "app/api/orders/export/route.js"]
    assert any(c.endswith("shared/stack-conventions.md") for c in need["constraints"])
    assert stage_status(out)["build"] == "awaiting_builder"
    steps = {s["id"]: s["status"] for s in run_json(out)["stages"][-1]["steps"]}
    assert steps == {"feature": "ok", "files": "ok", "tests": "ok", "code": "awaiting_builder"}   # files.txt derived: no stop there


def files_step_without_tasks(tmp_path: Path) -> Path:
    """The template with the files step's `tasks` input removed — what a composed `fix` pipeline looks like (no tasks.csv):
    files.txt cannot be derived, so the builder is asked. The refined plan still comes from --plan (the gate needs it)."""
    spec = json.loads((REPO_ROOT / "pipelines" / "feature-delivery.json").read_text())
    build = next(s for s in spec["stages"] if s["id"] == "build")
    del next(t for t in build["steps"] if t["id"] == "files")["inputs"]["tasks"]
    spec["name"] = "notasks"
    (tmp_path / "notasks.json").write_text(json.dumps(spec))
    return tmp_path / "notasks.json"


def test_builder_none_stops_at_the_files_step_when_files_txt_cannot_be_derived(tmp_path):
    """A pipeline whose files step has no tasks.csv (a composed fix): the files step asks the builder (exit 4) — before tests."""
    out = tmp_path / "nofiles"
    r = deliver(out, "--builder", "none", "--approve-all", "--plan", str(PLAN_DIR), pipeline=str(files_step_without_tasks(tmp_path)), brief=None)
    assert r.returncode == 4, r.stdout + r.stderr
    need = json.loads((out / "needs_builder.json").read_text())
    assert need["stage"] == "build" and need["step"] == "files" and need["produce"] == "files.txt"
    assert need["expected"] == str(out / "evidence" / "03-build" / "files" / "files.txt")
    assert need["alternative"] == str(out / "build" / "files.txt")
    assert need["why"] == "files.txt could not be derived: no tasks.csv to derive from"
    assert need["plan"].endswith("02-architecture/plan-refine/plan.md") and need["tasks"] is None
    assert "one repo-relative path per line" in need["format"] and "--resume" in need["how"]
    steps = {s["id"]: s["status"] for s in run_json(out)["stages"][-1]["steps"]}
    assert steps == {"feature": "ok", "files": "awaiting_builder"}
    assert not list((out / "evidence" / "03-build" / "tests").glob("*"))      # tests did not run: nothing to scaffold for yet
    assert "stopped at stage 'build' (awaiting_builder): needs the builder (files)" in r.stdout


def test_resume_picks_up_at_the_files_step_after_the_builder_drops_files_txt(tmp_path):
    out = tmp_path / "resume-files"
    pipeline = str(files_step_without_tasks(tmp_path))
    assert deliver(out, "--builder", "none", "--approve-all", "--plan", str(PLAN_DIR), pipeline=pipeline, brief=None).returncode == 4
    shutil.copy(FILES, out / "evidence" / "03-build" / "files" / "files.txt")      # the builder writes it in place
    r = deliver(out, "--builder", "none", "--approve-all", "--resume", pipeline=pipeline, brief=None)
    assert r.returncode == 4, r.stdout + r.stderr                                  # tests ran; now the code step waits
    need = json.loads((out / "needs_builder.json").read_text())
    assert need["step"] == "code" and need["allowed_files"] == ["lib/orders.js", "app/api/orders/export/route.js"]
    build = next(s for s in run_json(out)["stages"] if s["id"] == "build")
    steps = {t["id"]: t for t in build["steps"]}
    assert [(k, v["status"]) for k, v in steps.items()] == [("feature", "ok"), ("files", "ok"), ("tests", "ok"), ("code", "awaiting_builder")]
    assert steps["feature"].get("resumed") is True and "resumed" not in steps["files"]
    assert steps["files"]["files_source"] == "builder"
    fj = json.loads((out / "evidence" / "03-build" / "files" / "files.json").read_text())
    assert fj["derived"] is False and fj["files"] == ["lib/orders.js", "app/api/orders/export/route.js"]
    assert steps["tests"]["inputs"]["files"] == "lib/orders.js,app/api/orders/export/route.js"
    report = json.loads((out / "evidence" / "03-build" / "tests" / "scaffold-report.json").read_text())
    assert "tests/unit/lib-orders.test.js" in report["written"]
    (out / "build").mkdir(exist_ok=True)
    shutil.copy(PATCH, out / "build" / "diff.patch")
    r = deliver(out, "--builder", "none", "--approve-all", "--resume", pipeline=pipeline, brief=None)
    assert r.returncode == 0, r.stdout + r.stderr
    assert stage_status(out) == {s: "passed" for s in STAGES}


def test_manual_builder_with_a_files_txt_fixture_passes_end_to_end_without_a_brief(tmp_path):
    """--files wins over the derivation: a builder-supplied list is recorded as such even when tasks.csv could derive one."""
    out = tmp_path / "files-fixture"
    r = deliver(out, "--builder", "manual", "--plan", str(PLAN_DIR), "--files", str(FILES), "--patch", str(PATCH), "--approve-all", brief=None)
    assert r.returncode == 0, r.stdout + r.stderr
    assert stage_status(out) == {s: "passed" for s in STAGES}
    assert (out / "build" / "files.txt").read_text() == FILES.read_text()
    assert (out / "evidence" / "03-build" / "files" / "files.txt").read_text() == FILES.read_text()
    fj = json.loads((out / "evidence" / "03-build" / "files" / "files.json").read_text())
    assert fj["source"] == "builder" and fj["derived"] is False
    fc = json.loads((out / "evidence" / "03-build" / "code" / "files-changed.json").read_text())
    assert fc["plan_files_source"] == "files.txt" and fc["outside_plan"] == []
    assert "build/files.txt" in run_json(out)["files"]
    r = deliver(tmp_path / "nofile", "--builder", "manual", "--plan", str(PLAN_DIR), "--files", str(tmp_path / "missing.txt"), "--patch", str(PATCH), brief=None)
    assert r.returncode == 2 and "files.txt not found" in r.stderr


def test_a_missing_wire_is_a_pipeline_error_with_exit_2_not_a_gate_failure(tmp_path):
    """The first real run's failure: tests wired from a json key that is empty without a brief (spec.json#files here —
    the refined plan makes feature.json#files whole). That is a wiring error, never a gate verdict."""
    spec = json.loads((REPO_ROOT / "pipelines" / "feature-delivery.json").read_text())
    build = next(s for s in spec["stages"] if s["id"] == "build")
    build["steps"] = [t for t in build["steps"] if t["id"] != "files"]
    next(t for t in build["steps"] if t["id"] == "tests")["inputs"]["files"] = "$steps.spec:spec.json#files"
    del next(t for t in build["steps"] if t["id"] == "code")["inputs"]["files"]
    build["evidence"] = [e for e in build["evidence"] if ":files.txt" not in e]
    spec["name"] = "miswired"
    (tmp_path / "miswired.json").write_text(json.dumps(spec))
    out = tmp_path / "wire"
    r = deliver(out, "--builder", "none", "--approve-all", "--plan", str(PLAN_DIR), pipeline=str(tmp_path / "miswired.json"), brief=None)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "stopped at stage 'build' (wiring_error)" in r.stdout
    assert r.stderr.strip().endswith("pipeline wiring error: step 'tests' input 'files' resolved to nothing from "
                                     "'$steps.spec:spec.json#files': no earlier step produced it (skill build/test-strategy-tdd requires it)")
    we = json.loads((out / "wiring_error.json").read_text())
    assert we["step"] == "tests" and we["input"] == "files" and we["skill"] == "build/test-strategy-tdd" and we["stage"] == "build"
    assert we["reference"] == "$steps.spec:spec.json#files" and "not a gate failure" in we["how"]
    assert not (out / "needs_input.json").exists() and not (out / "needs_builder.json").exists()
    assert stage_status(out) == {"requirements": "passed", "architecture": "passed", "build": "wiring_error"}
    gate = json.loads((out / "evidence" / "03-build" / "gate.json").read_text())
    assert gate["verdict"] == "fail" and gate["detail"].startswith("pipeline wiring error")
    assert run_json(out)["exit_code"] == 2


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
    assert reused == {"feature": True, "files": True, "tests": True, "code": False, "conventions": False}
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


def test_request_only_run_without_a_brief_asks_the_architect_for_the_plan_never_fails_a_gate(tmp_path):
    out = tmp_path / "nobrief"
    r = deliver(out, "--builder", "manual", "--patch", str(PATCH), "--approve-all", brief=None)
    assert r.returncode == 4, r.stdout + r.stderr                     # manual builder, no refined plan yet: same stop as --builder none
    brief = json.loads((out / "evidence" / "01-requirements" / "brief" / "brief.json").read_text())
    assert brief["feature"] == REQUEST and brief["problem"] == REQUEST and "_composed" in brief
    need = json.loads((out / "needs_builder.json").read_text())
    assert need["step"] == "plan-refine" and need["builder"] == "manual"
    assert stage_status(out)["architecture"] == "awaiting_builder"     # never a gate failure, never a needs_input
    assert not (out / "evidence" / "03-build").exists()                 # the build stage never started on an unfilled plan
    assert not (out / "wiring_error.json").exists() and not (out / "needs_input.json").exists()


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


# ---------------------------------------------------------------- portal callback (--run / --portal)

import os
import socket
import stat
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

_REAL_SOCKET = socket.socket   # conftest's no_network fixture blocks sockets in-process; the stub portal is loopback only

RUN_UUID = "0f1e2d3c-4b5a-4968-8777-66554433aa11"


class StubPortal:
    """A minimal portal: records every stage POST (body + auth), serves GET run with the approvals it holds.
    `approve_after_wait` adds an approval for a stage as soon as that stage has posted awaiting_approval, which is
    what a person clicking Approve in the portal looks like to the executor."""

    def __init__(self, approve_after_wait: bool = False, fail_posts: bool = False, pipeline_spec: dict | None = None):
        self.pipeline_spec = pipeline_spec      # a composed pipeline stored on the run (0024): served on GET run
        self.posts: list[dict] = []
        self.auth: list[str] = []
        self.gets = 0
        self.approvals: list[dict] = []
        self.approve_after_wait = approve_after_wait
        self.fail_posts = fail_posts
        stub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code: int, body: dict):
                data = json.dumps(body).encode()
                self.send_response(code); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                stub.auth.append(self.headers.get("Authorization", ""))
                if stub.fail_posts:
                    return self._send(500, {"error": "boom"})
                if self.path != f"/api/delivery-runs/{RUN_UUID}/stage":
                    return self._send(404, {"error": "not_found"})
                stub.posts.append(body)
                if stub.approve_after_wait and body.get("status") == "awaiting_approval":
                    stub.approvals.append({"id": "a1", "run_id": RUN_UUID, "stage_id": body["id"], "role": "ai-solution-architect",
                                           "approved_by": "giri@example.com", "note": "plan ok", "created_at": "2026-01-01T00:00:00Z"})
                self._send(200, {"run_id": RUN_UUID, "status": "running", "stage": body["id"]})

            def do_GET(self):
                stub.gets += 1
                stub.auth.append(self.headers.get("Authorization", ""))
                self._send(200, {"id": RUN_UUID, "status": "running", "approvals": stub.approvals,
                                 **({"pipeline_spec": stub.pipeline_spec} if stub.pipeline_spec else {})})

        socket.socket = _REAL_SOCKET   # loopback stub only; conftest's monkeypatch restores the block at teardown
        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown(); self.server.server_close()


@pytest.fixture
def portal():
    p = StubPortal()
    yield p
    p.close()


def portal_env(monkeypatch):
    monkeypatch.setenv("SF_API_KEY", "sf_live_test_key")
    monkeypatch.setenv("SF_CALLBACK_BACKOFF", "0")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/giri-skills")
    monkeypatch.setenv("GITHUB_RUN_ID", "4242")
    monkeypatch.delenv("GITHUB_RUN_URL", raising=False)


def test_pipeline_flag_is_an_alias_of_the_positional(tmp_path):
    out = tmp_path / "alias"
    r = run_script(SCRIPT, "--pipeline", "feature-delivery", "--repo", str(REPO), "--request", REQUEST, "--brief", str(BRIEF),
                   "--out", str(out), "--provider", "dry", "--dry", "--builder", "manual", "--patch", str(PATCH), "--approve-all")
    assert r.returncode == 0, r.stdout + r.stderr
    r = run_script(SCRIPT, "--repo", str(REPO), "--request", REQUEST, "--out", str(tmp_path / "none"), "--dry")
    assert r.returncode == 2 and "pipeline is required" in r.stderr
    r = run_script(SCRIPT, "feature-delivery", "--pipeline", "greenfield-app", "--repo", str(REPO), "--request", REQUEST, "--out", str(tmp_path / "two"), "--dry")
    assert r.returncode == 2 and "given twice" in r.stderr


def test_run_and_portal_need_each_other_and_the_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("SF_API_KEY", raising=False)
    r = run_script(SCRIPT, "feature-delivery", "--repo", str(REPO), "--request", REQUEST, "--out", str(tmp_path / "o"), "--dry", "--run", RUN_UUID)
    assert r.returncode == 2 and "--run and --portal go together" in r.stderr
    r = run_script(SCRIPT, "feature-delivery", "--repo", str(REPO), "--request", REQUEST, "--out", str(tmp_path / "o"), "--dry", "--run", RUN_UUID, "--portal", "http://127.0.0.1:1")
    assert r.returncode == 2 and "SF_API_KEY" in r.stderr


def test_portal_receives_the_profile_then_one_record_per_stage(tmp_path, monkeypatch, portal):
    portal_env(monkeypatch)
    out = tmp_path / "cb"
    r = deliver(out, "--builder", "manual", "--patch", str(PATCH), "--approve-all", "--run", RUN_UUID, "--portal", portal.url + "/")
    assert r.returncode == 0, r.stdout + r.stderr
    seq = [(p["id"], p["status"]) for p in portal.posts]
    assert seq == [("requirements", "running")] + [(s, "succeeded") for s in STAGES]
    first = portal.posts[0]
    assert first["stack_profile"]["framework"] == "nextjs" and "stack_profile" not in portal.posts[1]
    assert all(p["executor_ref"] == "https://github.com/acme/giri-skills/actions/runs/4242" for p in portal.posts)
    assert set(portal.auth) == {"Bearer sf_live_test_key"}
    arch = portal.posts[2]
    assert arch["id"] == "architecture" and arch["gate"]["kind"] == "all" and arch["gate"]["verdict"] == "pass"
    assert arch["gate"]["detail"].startswith("[pass] tasks.csv: csv_rows:files!empty") and arch["gate"]["detail"].endswith("[pass] approved by --approve-all")
    assert arch["role"] == "ai-solution-architect" and arch["adlc_stage"] == "architecture"
    paths = [e["path"] for e in arch["evidence"]]
    assert "02-architecture/plan/plan.md" in paths and "02-architecture/plan-refine/tasks.csv" in paths and "02-architecture/gate.json" in paths
    for e in arch["evidence"]:
        assert len(e["sha256"]) == 64 and e["bytes"] > 0
        assert e["sha256"] == run_json(out)["files"]["evidence/" + e["path"]]
    deploy = portal.posts[5]
    assert deploy["gate"]["verdict"] == "pass" and "pr" not in deploy       # dry: no PR to report
    for p in portal.posts:
        assert p["started_at"].endswith("Z") and p.get("finished_at", "Z").endswith("Z")
    log = (out / "callback.log").read_text()
    assert log.count("-> 200") == 7 and "failed" not in log
    assert "warning" not in r.stderr


def test_gate_failure_posts_blocked_with_the_verdict(tmp_path, monkeypatch, portal):
    portal_env(monkeypatch)
    out = tmp_path / "cbfail"
    r = deliver(out, "--builder", "manual", "--patch", str(RISKY_PATCH), "--approve-all", "--run", RUN_UUID, "--portal", portal.url)
    assert r.returncode == 1
    seq = [(p["id"], p["status"]) for p in portal.posts]
    assert seq == [("requirements", "running"), ("requirements", "succeeded"), ("architecture", "succeeded"), ("build", "succeeded"), ("evaluate", "blocked")]
    ev = portal.posts[-1]
    assert ev["gate"]["kind"] == "all" and ev["gate"]["verdict"] == "fail" and "[fail]" in ev["gate"]["detail"]
    assert "error" not in ev          # a gate verdict, not a crash


def test_builder_wait_posts_blocked_with_a_pending_gate(tmp_path, monkeypatch, portal):
    portal_env(monkeypatch)
    r = deliver(tmp_path / "cbb", "--builder", "none", "--approve-all", "--run", RUN_UUID, "--portal", portal.url)
    assert r.returncode == 4
    last = portal.posts[-1]
    assert (last["id"], last["status"], last["gate"]["verdict"]) == ("build", "blocked", "pending")
    assert "waiting for the builder" in last["gate"]["detail"]


def test_portal_approval_resumes_the_run(tmp_path, monkeypatch):
    portal_env(monkeypatch)
    p = StubPortal(approve_after_wait=True)
    try:
        out = tmp_path / "poll"
        r = deliver(out, "--builder", "manual", "--patch", str(PATCH), "--run", RUN_UUID, "--portal", p.url,
                    "--poll-interval", "0.05", "--approval-timeout", "20")
        assert r.returncode == 0, r.stdout + r.stderr
        seq = [(x["id"], x["status"]) for x in p.posts]
        assert seq == [("requirements", "running"), ("requirements", "succeeded"), ("architecture", "awaiting_approval"),
                       ("architecture", "succeeded"), ("build", "succeeded"), ("evaluate", "succeeded"), ("deploy", "succeeded"), ("operate", "succeeded")]
        assert p.posts[2]["gate"] == {"kind": "approval", "verdict": "pending", "detail": "waiting for approval of step 'plan-approval' (ai-solution-architect)"}
        assert p.gets >= 1 and "waiting for approval of 'plan-approval' in the portal" in r.stdout
        ap = json.loads((out / "evidence" / "02-architecture" / "plan-approval" / "approval.json").read_text())
        assert ap["by"] == "giri@example.com" and ap["note"] == "plan ok"
        assert p.posts[3]["gate"]["detail"].endswith("| [pass] approved by giri@example.com")
        assert not (out / "needs_approval.json").exists()
    finally:
        p.close()


def test_approval_timeout_falls_back_to_exit_3(tmp_path, monkeypatch, portal):
    portal_env(monkeypatch)
    out = tmp_path / "pollto"
    r = deliver(out, "--builder", "none", "--run", RUN_UUID, "--portal", portal.url, "--poll-interval", "0.05", "--approval-timeout", "0.3")
    assert r.returncode == 3 and (out / "needs_approval.json").is_file()
    assert portal.gets >= 2
    assert [(x["id"], x["status"]) for x in portal.posts][-1] == ("architecture", "awaiting_approval")
    assert "timed out" in (out / "callback.log").read_text()


def test_approvals_file_skips_the_portal_poll(tmp_path, monkeypatch, portal):
    portal_env(monkeypatch)
    approvals = tmp_path / "approvals.json"
    approvals.write_text(json.dumps({"approvals": [{"step": "plan-approval", "by": "cli"}]}))
    r = deliver(tmp_path / "noPoll", "--builder", "manual", "--patch", str(PATCH), "--approvals", str(approvals), "--run", RUN_UUID, "--portal", portal.url)
    assert r.returncode == 0, r.stdout + r.stderr
    assert portal.gets == 0 and ("architecture", "awaiting_approval") not in [(x["id"], x["status"]) for x in portal.posts]


def test_dead_portal_never_aborts_the_run(tmp_path, monkeypatch):
    portal_env(monkeypatch)
    out = tmp_path / "dead"
    r = deliver(out, "--builder", "manual", "--patch", str(PATCH), "--approve-all", "--run", RUN_UUID, "--portal", "http://127.0.0.1:9")
    assert r.returncode == 0, r.stdout + r.stderr
    assert stage_status(out) == {s: "passed" for s in STAGES}
    assert r.stderr.count("warning: portal callback failed") == 7
    log = (out / "callback.log").read_text()
    assert log.count("attempt 3/3 failed") == 7 and "-> 200" not in log


def test_portal_5xx_is_retried_three_times(tmp_path, monkeypatch):
    portal_env(monkeypatch)
    p = StubPortal(fail_posts=True)
    try:
        r = deliver(tmp_path / "p5", "--builder", "manual", "--patch", str(PATCH), "--approve-all", "--run", RUN_UUID, "--portal", p.url)
        assert r.returncode == 0
        assert len(p.auth) == 7 * 3
    finally:
        p.close()


# ---------------------------------------------------------------- pr step (non-dry) with a fake gh on PATH

FAKE_GH = """#!/bin/sh
printf '%s\\n' "$*" >> "$GH_LOG"
printf 'cwd=%s\\n' "$(pwd -P)" >> "$GH_LOG"
case "$1 $2" in
  "api repos/acme/app") echo "${GH_PUSH:-true}" ;;
  "pr create") echo "https://github.com/acme/app/pull/7" ;;
  "pr view") grep -q '^pr create' "$GH_LOG" || { echo 'no pull requests found for branch' >&2; exit 1; }
             echo '{"number": 7, "url": "https://github.com/acme/app/pull/7", "headRefOid": "deadbeef"}' ;;
esac
exit 0
"""


def test_pr_step_commits_as_the_bot_pushes_and_opens_the_pr(tmp_path, monkeypatch):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    work = tmp_path / "checkout"
    shutil.copytree(REPO, work)
    env = {**os.environ, "GIT_AUTHOR_NAME": "dev", "GIT_AUTHOR_EMAIL": "dev@x", "GIT_COMMITTER_NAME": "dev", "GIT_COMMITTER_EMAIL": "dev@x",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "base"],
                ["git", "remote", "add", "origin", str(bare)], ["git", "push", "-q", "-u", "origin", "main"]):
        subprocess.run(cmd, cwd=work, env=env, check=True)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "gh").write_text(FAKE_GH)
    (bindir / "gh").chmod((bindir / "gh").stat().st_mode | stat.S_IEXEC)
    gh_log = tmp_path / "gh.log"
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("GH_LOG", str(gh_log))
    monkeypatch.setenv("GH_TOKEN", "ghp_fake")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    out = tmp_path / "real"
    r = run_script(SCRIPT, "feature-delivery", "--repo", str(work), "--request", REQUEST, "--brief", str(BRIEF), "--out", str(out),
                   "--provider", "dry", "--builder", "manual", "--patch", str(PATCH), "--approve-all", "--run-id", "r-pr-1")
    assert r.returncode == 0, r.stdout + r.stderr
    pr = json.loads((out / "evidence" / "05-deploy" / "pr" / "pr.json").read_text())
    assert pr == {"dry": False, "branch": "deliver/r-pr-1", "title": REQUEST, "number": 7, "url": "https://github.com/acme/app/pull/7",
                  "head_sha": "deadbeef", "committed_as": "skills-factory[bot]"}
    calls = gh_log.read_text().splitlines()
    assert calls[0].startswith("pr view deliver/r-pr-1")      # no PR yet → create; the push authenticates through `gh auth git-credential` only
    create = next(c for c in calls if c.startswith("pr create"))
    assert create == f"pr create --title {REQUEST} --body-file {out / 'evidence' / 'EVIDENCE.md'} --head deliver/r-pr-1"
    assert "pr view deliver/r-pr-1 --json number,url,headRefOid" in calls
    assert all(c == f"cwd={work.resolve()}" for c in calls if c.startswith("cwd="))      # gh runs in the target checkout
    # the branch reached the bare remote with the bot identity and the checkout's changes
    log = subprocess.run(["git", "log", "-1", "--format=%an <%ae>%n%s", "deliver/r-pr-1"], cwd=bare, capture_output=True, text=True, check=True).stdout
    assert log.splitlines() == ["skills-factory[bot] <skills-factory[bot]@users.noreply.github.com>", REQUEST]
    files = subprocess.run(["git", "ls-tree", "-r", "--name-only", "deliver/r-pr-1"], cwd=bare, capture_output=True, text=True, check=True).stdout
    assert ".github/ci-additions.yml" in files            # what the ci step wrote on the checkout travelled with the commit
    assert "app/api/orders/export/route.js" in files      # the manual diff was applied to the checkout and is in the PR
    applied = json.loads((out / "evidence" / "03-build" / "code" / "applied.json").read_text())
    assert applied["status"] == "applied" and applied["files"] == ["app/api/orders/export/route.js", "lib/orders.js", "tests/unit/lib/orders.test.js"]
    assert "3 files changed" in applied["diff_stat"]
    assert "PR opened" in run_json(out)["stages"][-1]["steps"][0]["inputs"]["state"]


def test_out_defaults_to_runs_run_id_in_portal_mode_matching_the_portal_command(tmp_path, monkeypatch):
    """studio deliverCommand() prints `--pipeline … --repo … --request … --run … --portal …` with no --out."""
    monkeypatch.setenv("SF_API_KEY", "sf_live_x")
    r = run_script(SCRIPT, "feature-delivery", "--repo", str(REPO), "--request", REQUEST, "--dry")
    assert r.returncode == 2 and "--out is required" in r.stderr
    runs = REPO_ROOT / "runs" / RUN_UUID
    shutil.rmtree(runs, ignore_errors=True)
    try:
        r = run_script(SCRIPT, "--pipeline", "feature-delivery", "--repo", str(REPO), "--request", REQUEST, "--brief", str(BRIEF),
                       "--run", RUN_UUID, "--portal", "http://127.0.0.1:9", "--dry", "--builder", "none",
                       "--approval-timeout", "0.2", "--poll-interval", "0.05")
        assert r.returncode == 3, r.stdout + r.stderr           # an IDE run with the portal unreachable: stops at the plan approval
        assert (runs / "needs_approval.json").is_file() and (runs / "callback.log").is_file()
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_repo_key_is_cloned_with_gh_and_a_clear_error_without_access(tmp_path, monkeypatch):
    """The portal names repositories owner/name; the executor clones them itself (via gh) instead of refusing."""
    import importlib.util, sys as _sys
    spec = importlib.util.spec_from_file_location("deliver_mod", REPO_ROOT / "scripts" / "deliver.py")
    mod = importlib.util.module_from_spec(spec)
    _sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        spec.loader.exec_module(mod)
    finally:
        _sys.path.pop(0)
    assert mod.REPO_KEY.match("giritharanchockalingam/vg-advantage-portal")
    assert not mod.REPO_KEY.match("./app") and not mod.REPO_KEY.match("/tmp/x/y")
    # a fake gh that refuses like GitHub does without access
    bindir = tmp_path / "bin"; bindir.mkdir()
    (bindir / "gh").write_text("#!/bin/sh\necho 'remote: Write access to repository not granted.' >&2; exit 1\n")
    (bindir / "gh").chmod(0o755)
    import os
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    import pytest
    with pytest.raises(SystemExit) as e:
        mod.clone_repo("owner/name", tmp_path / "repo")
    assert "GH_TOKEN" in str(e.value) and "not granted" in str(e.value)
    # a fake gh that clones: an existing checkout is reused untouched
    (tmp_path / "repo").mkdir(); (tmp_path / "repo" / ".git").mkdir()
    assert mod.clone_repo("owner/name", tmp_path / "repo") == tmp_path / "repo"


# ---- brownfield baselines: the gate rule is "no NEW high findings from this change", not "the repo is clean"

LEGACY = ('import { sql } from "@/lib/db";\n\nexport default async function Page() {\n'
          '  const rows = await sql`select id from orders`;\n  return <pre>{JSON.stringify(rows)}</pre>;\n}\n')
NEW_VIOLATION_PATCH = FIX / "delivery-build" / "diff-new-violation.patch"


def brownfield_repo(tmp_path: Path) -> Path:
    """The fixture repo plus one pre-existing high finding (NX5 in app/legacy/page.js) the change never touches."""
    repo = tmp_path / "brown"
    shutil.copytree(REPO, repo)
    (repo / "app" / "legacy").mkdir(parents=True)
    (repo / "app" / "legacy" / "page.js").write_text(LEGACY, encoding="utf-8")
    return repo


def findings(out: Path, stage_step: str) -> list[dict]:
    import csv
    return list(csv.DictReader((out / "evidence" / stage_step / "findings.csv").open(encoding="utf-8")))


def test_pre_existing_violation_is_baselined_and_a_clean_patch_passes(tmp_path):
    out = tmp_path / "out"
    r = deliver(out, "--builder", "manual", "--patch", str(PATCH), "--approve-all", repo=brownfield_repo(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert stage_status(out)["build"] == "passed" and stage_status(out)["evaluate"] == "passed"
    base = run_json(out)["baseline"]
    assert base["status"] == "captured" and sorted(base["checks"]) == ["nextjs", "perf", "ui"]
    assert base["checks"]["nextjs"] == {**base["checks"]["nextjs"], "source": "captured", "findings": 1, "high": 1,
                                        "path": "evidence/00-baseline/nextjs-enterprise-conventions/findings.csv"}
    ev = out / "evidence" / "00-baseline"
    for skill in ("nextjs-enterprise-conventions", "perf-review-runner", "ui-component-quality"):
        assert (ev / skill / "findings.csv").is_file() and (ev / skill / "report.md").is_file()
    assert (ev / "baseline.json").is_file()
    rows = findings(out, "03-build/conventions")
    assert [(f["rule"], f["file"], f["status"]) for f in rows] == [("NX5", "app/legacy/page.js", "known")]
    steps = {s["id"]: s for st in run_json(out)["stages"] for s in st["steps"]}
    assert steps["conventions"]["inputs"]["baseline"] == str(out / "evidence/00-baseline/nextjs-enterprise-conventions/findings.csv")
    assert steps["perf"]["inputs"]["baseline"].endswith("00-baseline/perf-review-runner/findings.csv")
    assert steps["ui"]["inputs"]["baseline"].endswith("00-baseline/ui-component-quality/findings.csv")
    assert steps["code"]["baseline"] == "captured" and steps["conventions"]["known"] == 1 and steps["conventions"]["new_high"] == []
    md = (out / "evidence" / "EVIDENCE.md").read_text()
    assert "Baseline (before the change" in md and "nextjs: 1 finding(s), 1 high — [findings.csv](evidence/00-baseline/nextjs-enterprise-conventions/findings.csv)" in md
    assert "perf: 0 finding(s), 0 high" in md and str(out) not in md
    files = run_json(out)["files"]
    assert "evidence/00-baseline/baseline.json" in files and "evidence/00-baseline/nextjs-enterprise-conventions/findings.csv" in files


def test_patch_adding_a_new_violation_fails_naming_only_the_new_finding(tmp_path):
    out = tmp_path / "out"
    r = deliver(out, "--builder", "manual", "--patch", str(NEW_VIOLATION_PATCH), "--approve-all", repo=brownfield_repo(tmp_path))
    assert r.returncode == 1 and "stopped at stage 'build'" in r.stdout
    gate = json.loads((out / "evidence" / "03-build" / "gate.json").read_text())
    assert gate["verdict"] == "fail"
    assert gate["detail"].endswith("1 new high finding(s) against the baseline: NX5 app/api/orders/export/route.js:5")
    assert "app/legacy/page.js" not in gate["detail"]
    rows = {(f["rule"], f["file"]): f["status"] for f in findings(out, "03-build/conventions")}
    assert rows == {("NX5", "app/api/orders/export/route.js"): "new", ("NX5", "app/legacy/page.js"): "known"}
    steps = {s["id"]: s for st in run_json(out)["stages"] for s in st["steps"]}
    assert steps["conventions"]["new_high"] == ["NX5 app/api/orders/export/route.js:5"]


def test_stack_profile_baselines_override_the_captured_ones(tmp_path):
    """docs/baselines/nextjs-findings.csv in the repo: the profile records it, the executor counts it and does not
    re-capture that check; the other checks are still captured."""
    repo = brownfield_repo(tmp_path)
    recorded = repo / "docs" / "baselines" / "nextjs-findings.csv"
    recorded.parent.mkdir(parents=True)
    recorded.write_text("rule,file,line,snippet,severity,status\n"
                        "NX5,app/legacy/page.js,4,const rows = await sql`select id from orders`;,high,new\n", encoding="utf-8")
    out = tmp_path / "out"
    r = deliver(out, "--builder", "manual", "--patch", str(PATCH), "--approve-all", repo=repo)
    assert r.returncode == 0, r.stdout + r.stderr
    base = run_json(out)["baseline"]
    assert base["checks"]["nextjs"]["source"] == "profile" and base["checks"]["nextjs"]["path"].endswith("docs/baselines/nextjs-findings.csv")
    assert base["checks"]["nextjs"]["findings"] == 1 and base["checks"]["perf"]["source"] == "captured"
    assert not (out / "evidence" / "00-baseline" / "nextjs-enterprise-conventions").exists()
    assert (out / "evidence" / "00-baseline" / "perf-review-runner" / "findings.csv").is_file()
    steps = {s["id"]: s for st in run_json(out)["stages"] for s in st["steps"]}
    assert steps["conventions"]["inputs"]["baseline"] == str(out / "repo" / "docs" / "baselines" / "nextjs-findings.csv")
    assert "nextjs: 1 finding(s), 1 high — repo-recorded (docs/baselines)" in (out / "evidence" / "EVIDENCE.md").read_text()


def test_no_baseline_flag_makes_pre_existing_debt_fail_the_gate(tmp_path):
    out = tmp_path / "out"
    r = deliver(out, "--builder", "manual", "--patch", str(PATCH), "--approve-all", "--no-baseline", repo=brownfield_repo(tmp_path))
    assert r.returncode == 1 and stage_status(out)["build"] == "failed"
    base = run_json(out)["baseline"]
    assert base["status"] == "skipped" and "--no-baseline" in base["reason"]
    assert not (out / "evidence" / "00-baseline" / "nextjs-enterprise-conventions").exists()
    assert [f["status"] for f in findings(out, "03-build/conventions")] == ["new"]
    assert "Baseline (before the change): skipped — --no-baseline" in (out / "evidence" / "EVIDENCE.md").read_text()


def test_resume_keeps_the_captured_baseline(tmp_path):
    """The code step stops for the builder (exit 4) after the baseline is taken; the resume reads baseline.json back
    instead of re-running the skills on a checkout that now carries the change."""
    out = tmp_path / "out"
    r = deliver(out, "--approve-all", repo=brownfield_repo(tmp_path))
    assert r.returncode == 4 and (out / "evidence" / "00-baseline" / "baseline.json").is_file()
    at = run_json(out)["baseline"]["at"]
    r = deliver(out, "--resume", "--builder", "manual", "--patch", str(PATCH), "--approve-all", repo=brownfield_repo(tmp_path / "again"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert run_json(out)["baseline"]["at"] == at
    assert [f["status"] for f in findings(out, "03-build/conventions")] == ["known"]


# ---- --builder manual on a real checkout (no --dry): the diff is applied, the gates see it, resume is idempotent

DEV_ENV = {"GIT_AUTHOR_NAME": "dev", "GIT_AUTHOR_EMAIL": "dev@x", "GIT_COMMITTER_NAME": "dev", "GIT_COMMITTER_EMAIL": "dev@x",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def checkout(tmp_path: Path, src: Path = REPO, name: str = "checkout") -> Path:
    """A git checkout of the fixture repo (one commit on main), as the IDE path hands it to deliver.py."""
    work = tmp_path / name
    shutil.copytree(src, work)
    env = {**os.environ, **DEV_ENV}
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "base"]):
        subprocess.run(cmd, cwd=work, env=env, check=True)
    return work


def real(out: Path, work: Path, *extra: str):
    return run_script(SCRIPT, "feature-delivery", "--repo", str(work), "--request", REQUEST, "--brief", str(BRIEF), "--out", str(out),
                      "--provider", "dry", "--approve-all", *extra)


def git_out(work: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=work, env={**os.environ, **DEV_ENV}, capture_output=True, text=True, check=True).stdout


def test_manual_builder_applies_the_patch_to_the_checkout_and_conventions_sees_it(tmp_path):
    """Defect: the manual builder recorded diff.patch but never applied it, so conventions/perf/ui and the pr step saw
    unchanged code. Now `git apply --index` lands it: a diff adding a NEW violation fails the conventions gate."""
    work = checkout(tmp_path, brownfield_repo(tmp_path))
    out = tmp_path / "out"
    r = real(out, work, "--builder", "manual", "--patch", str(NEW_VIOLATION_PATCH))
    assert r.returncode == 1 and "stopped at stage 'build'" in r.stdout, r.stdout + r.stderr
    route = work / "app" / "api" / "orders" / "export" / "route.js"
    assert route.is_file() and "select * from orders" in route.read_text()                 # the checkout carries the change
    assert "app/api/orders/export/route.js" in git_out(work, "diff", "--cached", "--name-only")   # staged (--index)
    applied = json.loads((out / "evidence" / "03-build" / "code" / "applied.json").read_text())
    assert applied["status"] == "applied" and applied["files"] == ["app/api/orders/export/route.js"]
    assert "route.js" in applied["diff_stat"] and "1 file changed" in applied["diff_stat"]
    steps = {s["id"]: s for st in run_json(out)["stages"] for s in st["steps"]}
    assert steps["code"]["applied"] == "applied" and steps["code"]["applied_files"] == ["app/api/orders/export/route.js"]
    assert "applied to the checkout with `git apply --index`" in (out / "evidence" / "03-build" / "code" / "agent-summary.md").read_text()
    gate = json.loads((out / "evidence" / "03-build" / "gate.json").read_text())
    assert gate["detail"].endswith("1 new high finding(s) against the baseline: NX5 app/api/orders/export/route.js:5")
    rows = {(f["rule"], f["file"]): f["status"] for f in findings(out, "03-build/conventions")}
    assert rows == {("NX5", "app/api/orders/export/route.js"): "new", ("NX5", "app/legacy/page.js"): "known"}
    base = run_json(out)["baseline"]
    assert base["status"] == "captured" and base["target_source"].startswith("git archive HEAD")
    assert run_json(out)["base_sha"] == git_out(work, "rev-parse", "HEAD").strip()


def test_manual_patch_that_does_not_apply_fails_the_code_step_with_exit_1(tmp_path):
    work = checkout(tmp_path)
    (work / "lib" / "orders.js").write_text("export function listOrders() { return []; }\n", encoding="utf-8")   # context gone
    subprocess.run(["git", "commit", "-q", "-am", "drift"], cwd=work, env={**os.environ, **DEV_ENV}, check=True)
    out = tmp_path / "out"
    r = real(out, work, "--builder", "manual", "--patch", str(PATCH))
    assert r.returncode == 1 and "stopped at stage 'build'" in r.stdout, r.stdout + r.stderr
    gate = json.loads((out / "evidence" / "03-build" / "gate.json").read_text())
    assert gate["verdict"] == "fail" and "code: build/diff.patch does not apply cleanly to the checkout" in gate["detail"]
    steps = {s["id"]: s for s in run_json(out)["stages"][-1]["steps"]}
    assert steps["code"]["status"] == "failed" and steps["conventions"]["status"] == "skipped"
    assert not (work / "app" / "api" / "orders").exists() and git_out(work, "status", "--porcelain", "app", "lib") == ""
    assert not (out / "evidence" / "03-build" / "code" / "applied.json").exists()


def test_manual_patch_outside_files_txt_is_refused_before_anything_is_applied(tmp_path):
    work = checkout(tmp_path)
    bad = tmp_path / "bad.patch"
    bad.write_text(PATCH.read_text() + "diff --git a/next.config.js b/next.config.js\n--- a/next.config.js\n+++ b/next.config.js\n"
                   "@@ -1,1 +1,2 @@\n+// touched\n module.exports = {};\n", encoding="utf-8")
    out = tmp_path / "out"
    r = real(out, work, "--builder", "manual", "--patch", str(bad))
    assert r.returncode == 1
    gate = json.loads((out / "evidence" / "03-build" / "gate.json").read_text())
    assert "touches 1 file(s) outside files.txt + test paths: next.config.js" in gate["detail"]
    assert not (work / "app" / "api" / "orders").exists()                                  # nothing landed


def test_resume_at_the_code_step_takes_the_missing_baseline_from_the_pre_change_tree(tmp_path):
    """IDE path: run 1 (--builder none) stops at the code step; the IDE agent writes the code on the checkout and saves
    the diff. A resume with no baseline on disk (a run started before baselines existed) must still take it — from
    `git archive HEAD`, never from the checkout that now carries the change — and the already-applied diff is not
    applied twice."""
    work = checkout(tmp_path, brownfield_repo(tmp_path))
    out = tmp_path / "out"
    r = real(out, work, "--builder", "none")
    assert r.returncode == 4 and (out / "evidence" / "00-baseline" / "baseline.json").is_file(), r.stdout + r.stderr
    shutil.rmtree(out / "evidence" / "00-baseline")                                       # as if no baseline had been taken
    rj = run_json(out); rj.pop("baseline", None); (out / "run.json").write_text(json.dumps(rj))
    body = "\n".join(ln for ln in NEW_VIOLATION_PATCH.read_text().splitlines() if not ln.startswith("# ")) + "\n"
    (tmp_path / "ide.patch").write_text(body, encoding="utf-8")
    subprocess.run(["git", "apply", str(tmp_path / "ide.patch")], cwd=work, env={**os.environ, **DEV_ENV}, check=True)
    assert (work / "app" / "api" / "orders" / "export" / "route.js").is_file()
    r = real(out, work, "--resume", "--builder", "manual", "--patch", str(NEW_VIOLATION_PATCH))
    assert r.returncode == 1 and "stopped at stage 'build'" in r.stdout, r.stdout + r.stderr
    base = run_json(out)["baseline"]
    assert base["status"] == "captured" and base["target_source"].startswith("git archive HEAD")
    assert base["checks"]["nextjs"]["findings"] == 1                                        # legacy only: route.js is not in HEAD
    assert (out / "evidence" / "00-baseline" / "nextjs-enterprise-conventions" / "findings.csv").is_file()
    applied = json.loads((out / "evidence" / "03-build" / "code" / "applied.json").read_text())
    assert applied["status"] == "already-applied"
    rows = {(f["rule"], f["file"]): f["status"] for f in findings(out, "03-build/conventions")}
    assert rows == {("NX5", "app/api/orders/export/route.js"): "new", ("NX5", "app/legacy/page.js"): "known"}
    gate = json.loads((out / "evidence" / "03-build" / "gate.json").read_text())
    assert gate["detail"].endswith("1 new high finding(s) against the baseline: NX5 app/api/orders/export/route.js:5")


def test_baseline_is_taken_on_a_resume_at_a_later_stage_when_it_is_missing(tmp_path):
    """A run resumed at the evaluate stage (build already passed, the dry copy carries the change) with no baseline on
    disk: the perf/ui gates still get one, taken from the pre-change tree (git archive HEAD), never the working copy."""
    out = tmp_path / "out"
    r = deliver(out, "--builder", "manual", "--patch", str(PATCH), "--approve-all", repo=brownfield_repo(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    rj = run_json(out)
    rj["stages"] = [st for st in rj["stages"] if st["id"] in ("requirements", "architecture", "build")]   # evaluate and later: not run
    rj.pop("baseline", None)
    (out / "run.json").write_text(json.dumps(rj))
    shutil.rmtree(out / "evidence" / "00-baseline")
    for st in ("04-evaluate", "05-deploy", "06-operate"):
        shutil.rmtree(out / "evidence" / st, ignore_errors=True)
    assert (out / "repo" / "app" / "api" / "orders" / "export" / "route.js").is_file()     # the copy carries the change
    r = deliver(out, "--resume", "--builder", "manual", "--patch", str(PATCH), "--approve-all", repo=brownfield_repo(tmp_path / "x"))
    assert r.returncode == 0, r.stdout + r.stderr
    base = run_json(out)["baseline"]
    assert base["status"] == "captured" and sorted(base["checks"]) == ["nextjs", "perf", "ui"] and "git archive HEAD" in base["target_source"]
    assert base["checks"]["nextjs"]["findings"] == 1                                       # legacy only — route.js is not in HEAD
    assert (out / "evidence" / "00-baseline" / "perf-review-runner" / "findings.csv").is_file()
    steps = {s["id"]: s for st in run_json(out)["stages"] for s in st["steps"]}
    assert steps["perf"]["inputs"]["baseline"].endswith("00-baseline/perf-review-runner/findings.csv")
    assert steps["ui"]["inputs"]["baseline"].endswith("00-baseline/ui-component-quality/findings.csv")
    assert stage_status(out) == {s: "passed" for s in STAGES}                               # build kept, evaluate onwards re-run


def test_gate_detail_names_the_full_count_the_first_ten_and_how_many_more():
    import importlib.util, sys as _sys
    spec = importlib.util.spec_from_file_location("deliver_mod2", REPO_ROOT / "scripts" / "deliver.py")
    mod = importlib.util.module_from_spec(spec)
    _sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        spec.loader.exec_module(mod)
    finally:
        _sys.path.pop(0)
    items = [f"NX5 app/f{i}.js:{i}" for i in range(1, 15)]
    d = mod.new_high_detail(14, items[:10])
    assert d.startswith("14 new high finding(s) against the baseline: NX5 app/f1.js:1; ") and d.endswith("NX5 app/f10.js:10 … and 4 more")
    assert "f11" not in d
    assert mod.new_high_detail(3, items[:3]) == "3 new high finding(s) against the baseline: NX5 app/f1.js:1; NX5 app/f2.js:2; NX5 app/f3.js:3"


# ---- resume after a failed gate, and a build/diff.patch replaced after the build stage passed (first real run, P-8)

def test_resume_after_a_failed_gate_runs_the_stage_steps_again(tmp_path):
    """Defect: a stage whose gate failed kept its step records as 'done' on resume, so the fixed reviewer/security
    skills never ran again — the resume re-judged the stale review.md / findings.csv and failed the same way."""
    out = tmp_path / "out"
    r = deliver(out, "--builder", "manual", "--patch", str(RISKY_PATCH), "--approve-all")
    assert r.returncode == 1 and "stopped at stage 'evaluate' (failed)" in r.stdout
    first = (out / "evidence" / "04-evaluate" / "review" / "run.json").stat().st_mtime_ns
    r = deliver(out, "--resume", "--builder", "manual", "--approve-all")
    assert r.returncode == 1 and "stopped at stage 'evaluate' (failed)" in r.stdout, r.stdout + r.stderr
    steps = {s["id"]: s for s in run_json(out)["stages"][-1]["steps"]}
    assert steps["review"]["skill"] == "build/code-review-runner" and not steps["review"].get("resumed")
    assert (out / "evidence" / "04-evaluate" / "review" / "run.json").stat().st_mtime_ns > first   # the reviewer ran again
    assert stage_status(out)["build"] == "passed"   # the stage that stopped for nothing is not re-run


def test_a_changed_patch_after_the_build_stage_passed_supersedes_build_and_later_stages(tmp_path):
    """Defect: the builder fixed diff.patch after the review failed; the resume kept the passed build stage and the
    evaluate steps judged the OLD evidence copy. Now the build stage and everything after run again on the new diff,
    the old diff is taken off the checkout first, and the evidence carries the new one."""
    out = tmp_path / "out"
    r = deliver(out, "--builder", "manual", "--patch", str(RISKY_PATCH), "--approve-all")
    assert r.returncode == 1 and stage_status(out) == {"requirements": "passed", "architecture": "passed", "build": "passed", "evaluate": "failed"}
    old_sha = hashlib.sha256(RISKY_PATCH.read_bytes()).hexdigest()
    steps = {s["id"]: s for s in run_json(out)["stages"][2]["steps"]}
    assert steps["code"]["patch_sha256"] == old_sha
    r = deliver(out, "--resume", "--builder", "manual", "--patch", str(PATCH), "--approve-all")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "build/diff.patch changed since stage 'build' passed — re-running build, evaluate" in r.stdout
    assert stage_status(out) == {s: "passed" for s in STAGES}
    build = run_json(out)["stages"][2]
    steps = {s["id"]: s for s in build["steps"]}
    assert steps["code"]["patch_sha256"] == hashlib.sha256(PATCH.read_bytes()).hexdigest() and not steps["code"].get("resumed")
    assert steps["code"]["superseded_patch"]["previous_sha256"] == old_sha
    assert (out / "evidence" / "03-build" / "code" / "diff.patch").read_bytes() == PATCH.read_bytes()
    review = (out / "evidence" / "04-evaluate" / "review" / "review.md").read_text()
    assert "Verdict: **PASS**" in review and "app/reports/export.py" not in review


def test_the_earlier_diff_is_taken_off_a_real_checkout_before_the_new_one_lands(tmp_path):
    """The real checkout carries the diff the build stage applied; a replaced diff.patch is applied on the pre-change
    tree (git apply --reverse --index of the earlier one first), not on top of it."""
    work = checkout(tmp_path, brownfield_repo(tmp_path))
    out = tmp_path / "out"
    r = real(out, work, "--builder", "manual", "--patch", str(NEW_VIOLATION_PATCH))
    assert r.returncode == 1 and "stopped at stage 'build'" in r.stdout, r.stdout + r.stderr
    assert "select * from orders" in (work / "app" / "api" / "orders" / "export" / "route.js").read_text()
    r = real(out, work, "--resume", "--builder", "manual", "--patch", str(PATCH))
    assert "stopped at stage 'build'" not in r.stdout, r.stdout + r.stderr
    route = (work / "app" / "api" / "orders" / "export" / "route.js").read_text()
    assert "select * from orders" not in route and "listOrders" in route           # the new diff, not both
    changed = git_out(work, "diff", "--name-only", run_json(out)["base_sha"], "--", "app", "lib").split()
    assert sorted(changed) == ["app/api/orders/export/route.js", "lib/orders.js"]   # the new diff's files; nothing of the old one survives
    steps = {s["id"]: s for s in run_json(out)["stages"][2]["steps"]}
    assert steps["code"]["superseded_patch"]["reverted"] is True and steps["code"]["applied"] == "applied"
    assert stage_status(out)["build"] == "passed"
    assert [f["status"] for f in findings(out, "03-build/conventions")] == ["known"]


def test_dotfile_paths_keep_their_dot_in_files_txt_and_tasks_csv(tmp_path):
    """Defect (first real run): `.env.example` in tasks.csv became `env.example` in files.txt (str.lstrip("./")), so the
    code step refused the diff that touched it as 'outside files.txt'."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import deliver as d
    assert [d.repo_path(x) for x in (".env.example", "./lib/a.js", "`app/x.ts`", "lib\\b.js", "././.github/workflows/ci.yml")] == \
        [".env.example", "lib/a.js", "app/x.ts", "lib/b.js", ".github/workflows/ci.yml"]
    ft = tmp_path / "files.txt"
    ft.write_text("# files\n.env.example\n./lib/a.js\n`lib/a.js`\n", encoding="utf-8")
    assert d.read_files_txt(ft) == [".env.example", "lib/a.js"]


def _pr_fixture(tmp_path, monkeypatch, origin: str | None = None):
    """A checkout with a bare remote and the fake gh on PATH (as test_pr_step…); returns (work, bare, out, gh_log)."""
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    work = tmp_path / "checkout"
    shutil.copytree(REPO, work)
    env = {**os.environ, **DEV_ENV}
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "base"],
                ["git", "remote", "add", "origin", str(bare)], ["git", "push", "-q", "-u", "origin", "main"]):
        subprocess.run(cmd, cwd=work, env=env, check=True)
    if origin:
        subprocess.run(["git", "remote", "set-url", "origin", origin], cwd=work, env=env, check=True)
    bindir = tmp_path / "bin"; bindir.mkdir()
    (bindir / "gh").write_text(FAKE_GH); (bindir / "gh").chmod(0o755)
    gh_log = tmp_path / "gh.log"
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("GH_LOG", str(gh_log)); monkeypatch.setenv("GH_TOKEN", "ghp_fake"); monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    return work, bare, tmp_path / "real", gh_log


def test_a_token_that_cannot_push_stops_the_run_before_any_stage(tmp_path, monkeypatch):
    """First real run: the token cloned the repo but could not push; every gate passed and the run died at the pr step.
    Now the push permission is asked of GitHub up front and the run stops with needs_input.json before stage 1."""
    import http.server, socket, threading
    real_socket = next(c for c in socket.SocketType.__subclasses__() if c.__module__ == "socket")   # the class conftest replaced
    monkeypatch.setattr(socket, "socket", real_socket)   # a loopback stub of GitHub; conftest blocks sockets by default

    class Forbidden(http.server.BaseHTTPRequestHandler):   # GitHub's answer to receive-pack for a token without Contents: write
        def do_GET(self):
            self.send_response(403); self.end_headers(); self.wfile.write(b"Write access to repository not granted.")
        do_POST = do_GET
        def log_message(self, *a): pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), Forbidden)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        work, _, out, gh_log = _pr_fixture(tmp_path, monkeypatch, origin=f"http://127.0.0.1:{srv.server_port}/acme/app.git")
        r = run_script(SCRIPT, "feature-delivery", "--repo", str(work), "--request", REQUEST, "--brief", str(BRIEF), "--out", str(out),
                       "--provider", "dry", "--builder", "manual", "--patch", str(PATCH), "--approve-all", "--run-id", "r-pr-2")
    finally:
        srv.shutdown()
    assert r.returncode != 0 and "no push access to acme/app" in r.stderr and "Contents: read and write" in r.stderr, r.stdout + r.stderr
    need = json.loads((out / "needs_input.json").read_text())
    assert need["missing"][0]["name"] == "push access" and "acme/app" in need["missing"][0]["from"] and "403" in need["missing"][0]["from"]
    assert not (out / "evidence" / "01-requirements").exists()
    assert not gh_log.exists()   # permissions.push describes the user, not a fine-grained token: the API is not consulted


def test_resume_after_a_failed_push_pushes_the_existing_commit_and_opens_one_pr(tmp_path, monkeypatch):
    """The pr step is idempotent: the delivery commit made before a push failure is pushed as it is on resume (no empty
    commit stacked on it), and an already-open PR is reused rather than created twice."""
    work, bare, out, gh_log = _pr_fixture(tmp_path, monkeypatch)
    hook = bare / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'remote: Write access to repository not granted.' >&2\nexit 1\n"); hook.chmod(0o755)
    args = ["feature-delivery", "--repo", str(work), "--request", REQUEST, "--brief", str(BRIEF), "--out", str(out),
            "--provider", "dry", "--builder", "manual", "--approve-all", "--run-id", "r-pr-3"]
    r = run_script(SCRIPT, *args, "--patch", str(PATCH))
    assert r.returncode == 1 and "stopped at stage 'deploy'" in r.stdout, r.stdout + r.stderr
    gate = json.loads((out / "evidence" / "05-deploy" / "gate.json").read_text())
    assert "git push -u origin deliver/r-pr-3" in gate["detail"] and "not granted" in gate["detail"] and "cannot push" in gate["detail"]
    hook.unlink()
    r = run_script(SCRIPT, *args, "--resume")
    assert r.returncode == 0, r.stdout + r.stderr
    log = subprocess.run(["git", "log", "--format=%s", "main..deliver/r-pr-3"], cwd=bare, capture_output=True, text=True, check=True).stdout
    assert log.splitlines() == [REQUEST]                                  # one delivery commit, no empty commit on top
    assert sum(1 for c in gh_log.read_text().splitlines() if c.startswith("pr create")) == 1
    pr = json.loads((out / "evidence" / "05-deploy" / "pr" / "pr.json").read_text())
    assert pr["number"] == 7 and pr["branch"] == "deliver/r-pr-3"

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
    assert arch["id"] == "architecture" and arch["gate"] == {"kind": "approval", "verdict": "pass", "detail": "approved by --approve-all"}
    assert arch["role"] == "ai-solution-architect" and arch["adlc_stage"] == "architecture"
    paths = [e["path"] for e in arch["evidence"]]
    assert "02-architecture/plan/plan.md" in paths and "02-architecture/gate.json" in paths
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
        assert p.posts[3]["gate"]["detail"] == "approved by giri@example.com"
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
  "pr create") echo "https://github.com/acme/app/pull/7" ;;
  "pr view") echo '{"number": 7, "url": "https://github.com/acme/app/pull/7", "headRefOid": "deadbeef"}' ;;
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
    assert calls[0] == "auth setup-git"
    create = next(c for c in calls if c.startswith("pr create"))
    assert create == f"pr create --title {REQUEST} --body-file {out / 'evidence' / 'EVIDENCE.md'} --head deliver/r-pr-1"
    assert "pr view deliver/r-pr-1 --json number,url,headRefOid" in calls
    assert all(c == f"cwd={work.resolve()}" for c in calls if c.startswith("cwd="))      # gh runs in the target checkout
    # the branch reached the bare remote with the bot identity and the checkout's changes
    log = subprocess.run(["git", "log", "-1", "--format=%an <%ae>%n%s", "deliver/r-pr-1"], cwd=bare, capture_output=True, text=True, check=True).stdout
    assert log.splitlines() == ["skills-factory[bot] <skills-factory[bot]@users.noreply.github.com>", REQUEST]
    files = subprocess.run(["git", "ls-tree", "-r", "--name-only", "deliver/r-pr-1"], cwd=bare, capture_output=True, text=True, check=True).stdout
    assert ".github/ci-additions.yml" in files            # what the ci step wrote on the checkout travelled with the commit
    assert "PR opened" in run_json(out)["stages"][-1]["steps"][0]["inputs"]["state"]


def test_out_defaults_to_runs_run_id_in_portal_mode_matching_the_portal_command(tmp_path, monkeypatch):
    """studio deliverCommand() prints `--pipeline … --repo … --request … --run … --portal …` with no --out."""
    monkeypatch.setenv("SF_API_KEY", "sf_live_x")
    r = run_script(SCRIPT, "feature-delivery", "--repo", str(REPO), "--request", REQUEST, "--dry")
    assert r.returncode == 2 and "--out is required" in r.stderr
    runs = REPO_ROOT / "runs" / RUN_UUID
    shutil.rmtree(runs, ignore_errors=True)
    try:
        r = run_script(SCRIPT, "--pipeline", "feature-delivery", "--repo", str(REPO), "--request", REQUEST,
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

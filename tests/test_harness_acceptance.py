"""Harness layer 1: the requirements verification gate (docs/HARNESS.md).

A stand-in `claude` reads the prompt the pipeline gives the reviewer, writes the acceptance JSON at the path the
prompt names, and records its argv — so the gate's rules (what fails, what is downgraded, what is never the builder's
fault) and the reviewer's tool limits are tested on the real code path."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deliver_acc", REPO / "scripts" / "deliver.py")
d = importlib.util.module_from_spec(spec)
sys.modules["deliver_acc"] = d
spec.loader.exec_module(d)


def fake_reviewer(bin_dir: Path, review: dict | None) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe = bin_dir / "claude"
    exe.write_text(
        f"#!{sys.executable}\nimport sys, json, re\n"
        f"open({str(bin_dir / 'argv.json')!r}, 'w').write(json.dumps(sys.argv))\n"
        "prompt = sys.argv[sys.argv.index('-p') + 1]\n"
        "path = re.search(r'Write (\\S+acceptance\\.json) as JSON', prompt).group(1)\n"
        f"review = {review!r}\n"
        "if review is not None:\n    open(path, 'w').write(json.dumps(review))\n"
        "print(json.dumps({'subtype': 'success', 'result': 'reviewed', 'total_cost_usd': 0.4, 'usage': {}}))\n",
        encoding="utf-8")
    exe.chmod(0o755)


class Args:
    builder, model, dry, provider, acceptance, review_model, goal, sandbox = "claude-code", "m", True, "none", "auto", None, None, "none"
    budget_usd = None


def setup(tmp: Path, monkeypatch, review):
    fake_reviewer(tmp / "bin", review)
    monkeypatch.setenv("PATH", f"{tmp / 'bin'}:{__import__('os').environ['PATH']}")
    target = tmp / "app"
    (target / "docs").mkdir(parents=True)
    (target / "docs" / "CAPE-2.0-GOAL.md").write_text("# Goal\nPS wins, always.\n", encoding="utf-8")
    (target / "server.ts").write_text("export const x = 1;\n", encoding="utf-8")
    run = d.Run({"name": "t", "stages": []}, Args(), tmp / "out")
    run.run_id = "r1"
    sdir = tmp / "out" / "evidence" / "04-build" / "code"
    sdir.mkdir(parents=True)
    return run, target, sdir


GOOD = {"criteria": [{"id": "C1", "text": "PS wins", "must": True, "verdict": "MET", "evidence": "ran tests/x: pass"}], "defects": [], "summary": "ok"}


def test_a_met_review_passes_and_is_written_up(tmp_path, monkeypatch):
    run, target, sdir = setup(tmp_path, monkeypatch, GOOD)
    rec = {}
    run.run_acceptance(target, sdir, rec)
    assert rec["acceptance"]["verdict"] == "pass" and rec["acceptance"]["counts"]["MET"] == 1
    assert "round 1: PASS" in (sdir / "acceptance.md").read_text()


def test_not_met_fails_with_the_findings_for_the_builder(tmp_path, monkeypatch):
    review = {"criteria": [{"id": "C1", "text": "a PS change revalidates the draft", "must": True, "verdict": "NOT_MET",
                            "evidence": "E1: commit accepted on superseded data"}], "defects": [], "summary": "stale"}
    run, target, sdir = setup(tmp_path, monkeypatch, review)
    with pytest.raises(d.StepError, match="acceptance review failed: C1 NOT_MET: a PS change revalidates the draft"):
        run.run_acceptance(target, sdir, {})


def test_a_high_defect_fails_even_when_every_criterion_is_met(tmp_path, monkeypatch):
    review = {**GOOD, "defects": [{"severity": "high", "title": "no auth on commit route", "location": "app/api/commit/route.ts:3",
                                    "confirmed_by": "grep: no session check"}]}
    run, target, sdir = setup(tmp_path, monkeypatch, review)
    with pytest.raises(d.StepError, match="high defect: no auth on commit route"):
        run.run_acceptance(target, sdir, {})


def test_met_without_evidence_is_downgraded_to_unverified_not_counted_as_met(tmp_path, monkeypatch):
    review = {"criteria": [{"id": "C1", "text": "x", "must": True, "verdict": "MET", "evidence": ""}], "defects": [], "summary": ""}
    run, target, sdir = setup(tmp_path, monkeypatch, review)
    rec = {}
    run.run_acceptance(target, sdir, rec)
    assert rec["acceptance"]["counts"] == {"MET": 0, "PARTLY": 0, "NOT_MET": 0, "UNVERIFIED": 1}


def test_a_reviewer_that_writes_nothing_is_a_reviewer_error_never_the_builders(tmp_path, monkeypatch):
    run, target, sdir = setup(tmp_path, monkeypatch, None)
    with pytest.raises(d.ReviewerError, match="no valid round-1-acceptance.json"):
        run.run_acceptance(target, sdir, {})


def test_the_reviewer_reviews_a_copy_and_may_run_commands_only_through_the_sandbox(tmp_path, monkeypatch):
    run, target, sdir = setup(tmp_path, monkeypatch, GOOD)
    run.run_acceptance(target, sdir, {})
    argv = json.loads((tmp_path / "bin" / "argv.json").read_text())
    allowed = argv[argv.index("--allowedTools") + 1: argv.index("--append-system-prompt")]
    bash = [t for t in allowed if t.startswith("Bash")]
    assert bash == [f"Bash(python3 {REPO / 'scripts' / 'sandbox.py'} exec --dir {sdir / 'acceptance' / 'review-copy-1'}:*)"]
    assert (sdir / "acceptance" / "review-copy-1" / "server.ts").is_file()          # a disposable copy, not the checkout
    prompt = argv[argv.index("-p") + 1]
    assert "CAPE-2.0-GOAL.md" in prompt and "never edit the application to make it pass" in prompt


def test_manual_builders_are_not_reviewed_by_default_and_say_so(tmp_path, monkeypatch):
    run, target, sdir = setup(tmp_path, monkeypatch, GOOD)
    run.args.builder = "manual"
    rec = {}
    run.run_acceptance(target, sdir, rec)
    assert rec["acceptance"]["verdict"] == "not_run" and "manual builder's diff was not reviewed" in rec["acceptance"]["detail"]

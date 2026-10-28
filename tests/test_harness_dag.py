"""Harness layers 2 and 7: goal -> slice DAG -> durable, resumable runs, with people approving (docs/HARNESS.md).

The planner model and deliver.py are replaced by small executables with the same contract (the planner writes the
slices file its prompt names; deliver writes run.json and exits 0/1/3), so the harness's own logic — validation,
ordering, checkpointing, resume, approvals, budget — runs for real."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("harness_t", REPO / "scripts" / "harness.py")
h = importlib.util.module_from_spec(spec)
sys.modules["harness_t"] = h
spec.loader.exec_module(h)


def brief(f):
    return {"feature": f, "problem": "p", "goals": ["g"]}


PLAN = {"slices": [{"id": "S1", "title": "contracts", "depends_on": [], "brief": brief("contracts")},
                   {"id": "S2", "title": "engine", "depends_on": ["S1"], "brief": brief("engine")},
                   {"id": "S3", "title": "commit", "depends_on": ["S2"], "brief": brief("commit")}],
        "out_of_scope": [{"what": "real PeopleSoft", "why": "no sandbox"}]}


def test_plan_validation_catches_what_would_break_a_run():
    assert h.validate_plan(PLAN, 8) == []
    bad = {"slices": [{"id": "A", "title": "a", "depends_on": ["B"], "brief": brief("a")},
                      {"id": "B", "title": "b", "depends_on": ["A"], "brief": brief("b")}]}
    assert any("cycle" in p or "no root" in p for p in h.validate_plan(bad, 8))
    assert any("unknown slice X" in p for p in h.validate_plan({"slices": [{"id": "A", "title": "a", "depends_on": ["X"], "brief": brief("a")}]}, 8))
    assert any("brief lacks goals" in p for p in h.validate_plan({"slices": [{"id": "A", "title": "a", "brief": {"feature": "f", "problem": "p"}}]}, 8))
    assert any("max 2" in p for p in h.validate_plan(PLAN, 2))


def test_topological_order_follows_dependencies_not_listing_order():
    s = [{"id": "C", "depends_on": ["A", "B"]}, {"id": "A", "depends_on": []}, {"id": "B", "depends_on": ["A"]}]
    assert h.topo_order(s) == ["A", "B", "C"]


def fake_planner(bin_dir: Path, plans: list[dict]) -> None:
    """Writes plans[n] on its n-th call (a refused first plan is repaired by the second)."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "plans.json").write_text(json.dumps(plans), encoding="utf-8")
    exe = bin_dir / "claude"
    exe.write_text(f"#!{sys.executable}\nimport sys, json, re, os\nb = {str(bin_dir)!r}\n"
                   "n = len([f for f in os.listdir(b) if f.startswith('call')]); open(os.path.join(b, f'call{n}'), 'w').write(sys.argv[sys.argv.index('-p') + 1])\n"
                   "plans = json.load(open(os.path.join(b, 'plans.json')))\n"
                   "path = re.search(r'Write (\\S+slices\\.proposed\\.json) as JSON', sys.argv[sys.argv.index('-p') + 1]).group(1)\n"
                   "open(path, 'w').write(json.dumps(plans[min(n, len(plans) - 1)]))\n"
                   "print(json.dumps({'subtype': 'success', 'result': 'planned', 'total_cost_usd': 0.5}))\n", encoding="utf-8")
    exe.chmod(0o755)


def fake_deliver(tmp: Path, behaviour: dict[str, list[int]]) -> Path:
    """deliver.py stand-in: per slice brief id, the exit codes of successive calls; records argv; costs $1 per call."""
    log = tmp / "deliver-calls.jsonl"
    exe = tmp / "fake_deliver.py"
    exe.write_text(
        "import sys, json, os\nfrom pathlib import Path\n"
        f"log = {str(log)!r}; behaviour = {behaviour!r}\n"
        "a = sys.argv[1:]\n"
        "if a[0] == 'approve':\n"
        "    out = Path(a[1]); (out / 'approvals.json').write_text(json.dumps({'approvals': [{'step': a[a.index('--step') + 1], 'by': a[a.index('--by') + 1]}]})); sys.exit(0)\n"
        "out = Path(a[a.index('--out') + 1]); out.mkdir(parents=True, exist_ok=True)\n"
        "sid = Path(a[a.index('--brief') + 1]).stem\n"
        "calls = [json.loads(l) for l in open(log)] if os.path.exists(log) else []\n"
        "n = sum(1 for c in calls if c['sid'] == sid)\n"
        "open(log, 'a').write(json.dumps({'sid': sid, 'argv': a}) + '\\n')\n"
        "code = behaviour.get(sid, [0])[min(n, len(behaviour.get(sid, [0])) - 1)]\n"
        "prev = json.loads((out / 'run.json').read_text()) if (out / 'run.json').exists() else {}\n"
        "cost = float((prev.get('llm') or {}).get('cost_usd') or 0) + 1.0\n"
        "(out / 'run.json').write_text(json.dumps({'run_id': sid, 'llm': {'cost_usd': cost}, 'stages': []}))\n"
        "if code == 3: (out / 'needs_approval.json').write_text(json.dumps({'step': 'plan-approval'}))\n"
        "print(f'{sid} exit {code}'); sys.exit(code)\n", encoding="utf-8")
    return log


@pytest.fixture
def planned(tmp_path, monkeypatch):
    fake_planner(tmp_path / "bin", [{"slices": [{"id": "S1", "title": "x", "depends_on": ["S9"], "brief": brief("x")}]}, PLAN])
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:{__import__('os').environ['PATH']}")
    goal = tmp_path / "GOAL.md"
    goal.write_text("# Goal\nPS wins, always.\n", encoding="utf-8")
    d = tmp_path / "h"
    assert h.main(["plan", "--goal", str(goal), "--dir", str(d)]) == 0
    return d


def test_plan_repairs_a_refused_proposal_and_writes_briefs_and_state(planned, tmp_path):
    second_prompt = (tmp_path / "bin" / "call1").read_text()
    assert "refused by the harness: S1: depends on unknown slice S9" in second_prompt      # the refusal went back to the model
    plan, state = h.load(planned)
    assert plan["order"] == ["S1", "S2", "S3"] and state["plan_approval"] is None and state["cost_usd"] == 1.0
    assert json.loads((planned / "briefs" / "S2.json").read_text())["feature"] == "engine"


def test_run_refuses_an_unapproved_plan_and_an_approval_names_the_person(planned):
    assert h.main(["run", "--dir", str(planned), "--dry"]) == h.EXIT_APPROVAL
    h.main(["approve", "--dir", str(planned), "--by", "Giri", "--note", "reviewed"])
    assert h.load(planned)[1]["plan_approval"]["by"] == "Giri"


def test_slices_run_in_order_on_the_previous_slices_result_with_the_goal_and_harness_flags(planned, tmp_path, monkeypatch):
    log = fake_deliver(tmp_path, {})
    monkeypatch.setattr(h, "DELIVER", tmp_path / "fake_deliver.py")
    h.main(["approve", "--dir", str(planned), "--by", "Giri"])
    monkeypatch.setattr(h, "git", lambda *a: __import__("subprocess").CompletedProcess(a, 0, "", ""))
    assert h.main(["run", "--dir", str(planned), "--dry", "--budget-usd", "10"]) == 0
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert [c["sid"] for c in calls] == ["S1", "S2", "S3"]
    s1, s2 = calls[0]["argv"], calls[1]["argv"]
    assert s1[0] == "greenfield-app" and s2[0] == "feature-delivery" and s2[s2.index("--repo") + 1].endswith("runs/S1/repo")
    for flag in ("--goal", "--sandbox", "--acceptance", "--budget-usd"):
        assert flag in s2
    assert s2[s2.index("--budget-usd") + 1] == "8.0000"            # $10 goal budget - $1 planner - $1 slice S1
    assert "--approve-all" not in s2                               # plan approvals stay with people unless asked
    assert (planned / "HARNESS-REPORT.md").is_file() and "approved by: **Giri**" in (planned / "HARNESS-REPORT.md").read_text()


def test_a_crash_mid_slice_resumes_that_slice_with_resume(planned, tmp_path, monkeypatch):
    log = fake_deliver(tmp_path, {})
    monkeypatch.setattr(h, "DELIVER", tmp_path / "fake_deliver.py")
    monkeypatch.setattr(h, "git", lambda *a: __import__("subprocess").CompletedProcess(a, 0, "", ""))
    h.main(["approve", "--dir", str(planned), "--by", "Giri"])
    plan, state = h.load(planned)                                   # simulate: S1 passed, S2 was running when the box died
    out1, out2 = planned / "runs" / "S1", planned / "runs" / "S2"
    for o in (out1, out2):
        o.mkdir(parents=True)
        (o / "run.json").write_text(json.dumps({"llm": {"cost_usd": 1.0}, "stages": []}))
    state["slices"]["S1"].update(status="passed", out=str(out1))
    state["slices"]["S2"].update(status="running", out=str(out2))
    h.write_json(planned / "state.json", state)
    assert h.main(["run", "--dir", str(planned), "--dry"]) == 0
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert [c["sid"] for c in calls] == ["S2", "S3"] and "--resume" in calls[0]["argv"] and "--resume" not in calls[1]["argv"]


def test_a_slice_waiting_for_a_person_stops_the_harness_and_continues_after_approval(planned, tmp_path, monkeypatch):
    log = fake_deliver(tmp_path, {"S2": [3, 0]})
    monkeypatch.setattr(h, "DELIVER", tmp_path / "fake_deliver.py")
    monkeypatch.setattr(h, "git", lambda *a: __import__("subprocess").CompletedProcess(a, 0, "", ""))
    h.main(["approve", "--dir", str(planned), "--by", "Giri"])
    assert h.main(["run", "--dir", str(planned), "--dry"]) == h.EXIT_APPROVAL
    assert h.load(planned)[1]["slices"]["S2"]["status"] == "awaiting_approval"
    assert h.main(["approve", "--dir", str(planned), "--slice", "S2", "--by", "Asha"]) == 0
    assert json.loads((planned / "runs" / "S2" / "approvals.json").read_text())["approvals"][0]["by"] == "Asha"
    assert h.main(["run", "--dir", str(planned), "--dry"]) == 0
    assert [json.loads(x)["sid"] for x in log.read_text().splitlines()] == ["S1", "S2", "S2", "S3"]


def test_the_goal_budget_stops_the_harness_before_the_next_slice(planned, tmp_path, monkeypatch):
    fake_deliver(tmp_path, {})
    monkeypatch.setattr(h, "DELIVER", tmp_path / "fake_deliver.py")
    monkeypatch.setattr(h, "git", lambda *a: __import__("subprocess").CompletedProcess(a, 0, "", ""))
    h.main(["approve", "--dir", str(planned), "--by", "Giri"])
    assert h.main(["run", "--dir", str(planned), "--dry", "--budget-usd", "2"]) == h.EXIT_FAIL     # $1 plan + $1 S1 = $2
    st = h.load(planned)[1]["slices"]
    assert st["S1"]["status"] == "passed" and st["S2"]["status"] == "failed" and "budget exhausted" in st["S2"]["detail"]


def test_approve_all_is_recorded_as_auto_not_as_a_person(planned, tmp_path, monkeypatch):
    fake_deliver(tmp_path, {})
    monkeypatch.setattr(h, "DELIVER", tmp_path / "fake_deliver.py")
    monkeypatch.setattr(h, "git", lambda *a: __import__("subprocess").CompletedProcess(a, 0, "", ""))
    assert h.main(["run", "--dir", str(planned), "--dry", "--approve-all"]) == 0
    assert "AUTO-APPROVED" in (planned / "HARNESS-REPORT.md").read_text()

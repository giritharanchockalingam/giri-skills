"""Composed agents: skills chained by configuration (scripts/run_agent.py)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT

RUNNER = REPO_ROOT / "scripts" / "run_agent.py"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import run_agent  # noqa: E402


def agent(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(RUNNER), *args], capture_output=True, text=True, cwd=str(cwd or REPO_ROOT))


AGENT_DIRS = sorted(p.parent for p in (REPO_ROOT / "agents").glob("*/agent.json"))


@pytest.mark.parametrize("d", AGENT_DIRS, ids=lambda d: d.name)
def test_every_shipped_agent_validates(d: Path):
    assert run_agent.validate(run_agent.load_spec(d)) == []


def test_validator_catches_wiring_mistakes():
    spec = {
        "name": "bad", "description": "x", "inputs": [{"name": "client", "required": True}],
        "steps": [
            {"id": "est", "skill": "presales/effort-estimator", "inputs": {"client": "$in.client", "nope": "1"}},
            {"id": "prop", "skill": "presales/proposal-writer",
             "inputs": {"win_themes": "$in.themes", "estimate": "$steps.est:not-written.md", "discovery": "$steps.later:x.md"}},
            {"id": "gate", "approval": {"role": " "}},
            {"id": "est", "compose": {"out": "f.csv", "format": "xml", "rows": {}}},
        ],
    }
    problems = "\n".join(run_agent.validate(spec))
    for expected in ("has no input 'nope'", "required input 'wbs'", "$in.themes is not a declared agent input",
                     "does not declare 'not-written.md'", "refers to a step that does not run before it",
                     "approval needs a role", "duplicate id", "compose needs out, format"):
        assert expected in problems, expected


def test_presales_agent_pauses_for_approval_then_completes(tmp_path: Path):
    out = tmp_path / "run"
    r = agent("--demo", "presales-pursuit", "--provider", "dry", "--out", str(out))
    assert r.returncode == 4, r.stdout + r.stderr
    gate = json.loads((out / "awaiting_approval.json").read_text())
    assert gate["role"] == "Account owner" and gate["step"] == "commercial-review"
    trace = json.loads((out / "agent-run.json").read_text())
    assert [s["status"] for s in trace["steps"]] == ["ok", "ok", "ok", "awaiting_approval"]

    r = agent("--demo", "presales-pursuit", "--provider", "dry", "--out", str(out),
              "--approve", "commercial-review", "--approver", "Account owner (test)")
    assert r.returncode == 0, r.stdout + r.stderr
    trace = json.loads((out / "agent-run.json").read_text())
    assert trace["status"] == "ok" and all(s["status"] in ("ok", "approved") for s in trace["steps"])
    assert all(s["checks_passed"] == s["checks_total"] > 0 for s in trace["steps"] if s["kind"] == "skill")
    # composition is real: the proposal quotes the estimate's P80 and the discovery pain matrix verbatim
    estimate = (out / "steps" / "02-estimate" / "estimate.md").read_text()
    p80 = next(ln for ln in estimate.splitlines() if ln.startswith("| P80 |"))
    proposal = (out / "steps" / "05-proposal" / "proposal.md").read_text()
    assert p80 in proposal and "Evidence from discovery (verbatim pain matrix):" in proposal


def test_missing_agent_input_exits_2(tmp_path: Path):
    r = agent("presales-pursuit", "--input", "client=Acme", "--provider", "dry", "--out", str(tmp_path / "o"))
    assert r.returncode == 2
    missing = json.loads((tmp_path / "o" / "needs_input.json").read_text())["missing"]
    assert "wbs" in missing and "client" not in missing


def test_compose_builds_kv_csv_from_earlier_json_and_fails_on_missing_keys(tmp_path: Path):
    step = tmp_path / "s1"
    step.mkdir()
    (step / "r.json").write_text(json.dumps({"summary": {"pass_rate": 0.97}, "n": 38}))
    out = tmp_path / "s2"
    out.mkdir()
    extra = tmp_path / "extra.csv"
    extra.write_text("# fictional\nkey,value,source,notes\nrollback_time_min,15,owner,\nredteam_pass_rate,0.1,owner,\n")
    path = run_agent.do_compose({"out": "facts.csv", "format": "kv-csv", "include": "$in.extra",
                                 "rows": {"redteam_pass_rate": "$steps.s1:r.json#summary.pass_rate", "risk_tier": "medium"}},
                                {"extra": str(extra)}, {"s1": step}, out)
    rows = {ln.split(",")[0]: ln.split(",")[1] for ln in path.read_text().splitlines()[1:]}
    assert rows == {"redteam_pass_rate": "0.97", "risk_tier": "medium", "rollback_time_min": "15"}  # composed wins over extra
    with pytest.raises(run_agent.RefError, match="not found"):
        run_agent.do_compose({"out": "f.csv", "format": "kv-csv", "rows": {"x": "$steps.s1:r.json#summary.nope"}}, {}, {"s1": step}, out)


def test_inproc_and_subprocess_agents_agree(tmp_path: Path):
    a = agent("--demo", "presales-pursuit", "--provider", "dry", "--out", str(tmp_path / "a"), "--approve", "commercial-review")
    b = agent("--demo", "presales-pursuit", "--provider", "dry", "--out", str(tmp_path / "b"), "--approve", "commercial-review", "--inproc")
    assert a.returncode == b.returncode == 0, a.stdout + b.stdout
    ta = json.loads((tmp_path / "a" / "agent-run.json").read_text())
    tb = json.loads((tmp_path / "b" / "agent-run.json").read_text())
    pick = lambda t: [(s["id"], s["status"], s.get("checks_passed"), s.get("checks_total")) for s in t["steps"]]  # noqa: E731
    assert pick(ta) == pick(tb)


def test_list_shows_agents():
    r = agent("--list")
    assert r.returncode == 0 and "presales-pursuit:" in r.stdout


def test_adlc_spine_composes_real_results_and_blocks_on_the_release_gate(tmp_path: Path):
    out = tmp_path / "adlc"
    r = agent("--demo", "ai-use-case-to-release", "--provider", "dry", "--out", str(out))
    assert r.returncode == 4, r.stdout + r.stderr                       # stops for the AI risk lead first
    r = agent("--demo", "ai-use-case-to-release", "--provider", "dry", "--out", str(out),
              "--approve", "risk-signoff", "--approver", "AI risk lead (test)")
    assert r.returncode == 5, r.stdout + r.stderr                       # verdict, not malfunction
    trace = json.loads((out / "agent-run.json").read_text())
    assert trace["status"] == "blocked" and trace["steps"][-1]["status"] == "blocked"
    assert "redteam_pass_rate" in trace["steps"][-1]["error"]
    assert all(s["checks_passed"] == s["checks_total"] for s in trace["steps"][:-1] if s["kind"] == "skill")
    # the facts the release plan judged were composed from the earlier steps' own outputs
    steps = {p.name.split("-", 1)[1]: p for p in (out / "steps").iterdir()}
    red = json.loads((steps["redteam"] / "redteam-scorecard.json").read_text())["overall"]["pass_rate"]
    ev = json.loads((steps["evaluate"] / "scorecard.json").read_text())["overall_pass_rate"]
    facts = dict(ln.split(",")[:2] for ln in (steps["facts"] / "facts.csv").read_text().splitlines()[1:])
    assert facts["redteam_pass_rate"] == str(red) and facts["eval_pass_rate"] == str(ev)
    assert facts["system_name"] == "Northwind Billing Assistant"
    assert "NOT READY" in (steps["release"] / "release-plan.md").read_text()

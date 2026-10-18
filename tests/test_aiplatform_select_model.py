"""Tests for ai-platform/model-selection/scripts/select_model.py (hand-checked numbers)."""
from __future__ import annotations

import json
import re

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/model-selection/scripts/select_model.py"
FX = REPO_ROOT / "skills/ai-platform/model-selection/evals/fixtures"
HEAD = "model,provider,hosting,region,context_tokens,price_in_per_1m,price_out_per_1m,p95_latency_ms,acc,source,as_of\n"


def _run(tmp_path, cands, crit, workload=None):
    c = tmp_path / "c.csv"
    k = tmp_path / "k.csv"
    c.write_text(cands, encoding="utf-8")
    k.write_text(crit, encoding="utf-8")
    args = ["--candidates", str(c), "--criteria", str(k), "--out-dir", str(tmp_path / "out")]
    if workload:
        w = tmp_path / "w.csv"
        w.write_text(workload, encoding="utf-8")
        args += ["--workload", str(w)]
    r = run_script(SCRIPT, *args)
    data = None
    if (tmp_path / "out" / "ranking.json").exists():
        data = json.loads((tmp_path / "out" / "ranking.json").read_text(encoding="utf-8"))
    return r, data


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_fixture_happy_path_hand_checked(tmp_path):
    out = tmp_path / "out"
    r = run_script(SCRIPT, "--candidates", str(FX / "candidates.csv"), "--criteria", str(FX / "criteria.csv"),
                   "--workload", str(FX / "workload.csv"), "--out-dir", str(out))
    assert r.returncode == 0, r.stderr
    d = json.loads((out / "ranking.json").read_text(encoding="utf-8"))
    # eliminations: Cedar-8 (accuracy 0.69 < 0.75, context 32000 < 64000), Delta-Pro (latency 3000 > 2500)
    elim = {e["model"]: e["reasons"] for e in d["eliminated"]}
    assert set(elim) == {"Cedar-8 (fictional)", "Delta-Pro (fictional)"}
    assert len(elim["Cedar-8 (fictional)"]) == 2
    # monthly cost = 400000 * (1800*pin + 350*pout) / 1e6
    by = {x["model"]: x for x in d["ranking"]}
    assert by["Atlas-L (fictional)"]["monthly_cost_usd"] == 4260.0
    assert by["Atlas-S (fictional)"]["monthly_cost_usd"] == 1136.0
    assert by["Birch-70 (fictional)"]["monthly_cost_usd"] == 516.0
    # cost normalised (lower better): (4260-1136)/(4260-516) = 0.8344
    assert by["Atlas-S (fictional)"]["normalised"]["monthly_cost_usd"] == 0.8344
    assert by["Birch-70 (fictional)"]["normalised"]["task_accuracy"] == 0.375
    # scores: L = .4+.2 = 0.6; B = .4*.375 + .25 + .15*.6 = 0.49; S = .2*.5 + .25*.8344 + .15 = 0.4586
    assert [x["model"] for x in d["ranking"]] == ["Atlas-L (fictional)", "Birch-70 (fictional)", "Atlas-S (fictional)"]
    assert [x["score"] for x in d["ranking"]] == [0.6, 0.49, 0.4586]
    assert d["recommendation"]["margin"] == 0.11
    assert d["sensitivity"]["winner_changes"] is False and len(d["sensitivity"]["runs"]) == 8
    acc_down = next(x for x in d["sensitivity"]["runs"] if x["criterion"] == "task_accuracy" and x["factor"] == 0.8)
    assert acc_down["winner_score"] == 0.5652  # 0.52 / 0.92
    md = (out / "decision.md").read_text(encoding="utf-8")
    for h in ("## Recommendation", "## Eliminated", "## Scores", "## Sensitivity", "## Sources"):
        assert h in md
    assert "$4,260.00" in md
    # every number in decision.md traces to ranking.json; --verify recomputes
    chk = run_script("scripts/check_output.py", str(out / "decision.md"), f"numbers_trace_to:{out / 'ranking.json'}",
                     "no_unowned_tbd")
    assert chk.returncode == 0, chk.stdout
    assert run_script(SCRIPT, "--verify", str(out / "ranking.json")).returncode == 0


def test_no_survivor_exits_1_and_says_so(tmp_path):
    out = tmp_path / "out"
    r = run_script(SCRIPT, "--candidates", str(FX / "candidates.csv"), "--criteria",
                   str(FX / "criteria-self-host-strict.csv"), "--out-dir", str(out))
    assert r.returncode == 1
    d = json.loads((out / "ranking.json").read_text(encoding="utf-8"))
    assert d["ranking"] == [] and d["recommendation"] is None and len(d["eliminated"]) == 5
    api = next(e for e in d["eliminated"] if e["model"] == "Atlas-L (fictional)")
    assert any("hosting = api not in allowed {self-host}" in x for x in api["reasons"])
    birch = next(e for e in d["eliminated"] if e["model"] == "Birch-70 (fictional)")
    assert birch["reasons"] == ["task_accuracy = 0.81 below hard_min 0.85"]
    md = (out / "decision.md").read_text(encoding="utf-8")
    assert "None of the 5 candidates survives" in md and "owner: Solution architect" in md


def test_sensitivity_detects_winner_flip(tmp_path):
    cands = HEAD + ("A,p,api,us,1000,1,1,200,1.0,s,2026-01-01\n"
                    "B,p,api,us,1000,1,1,100,0.9,s,2026-01-01\n")
    crit = "criterion,weight,direction\nacc,0.55,higher\np95_latency_ms,0.45,lower\n"
    r, d = _run(tmp_path, cands, crit)
    assert r.returncode == 0, r.stderr
    assert d["recommendation"]["model"] == "A" and d["recommendation"]["score"] == 0.55
    # acc weight x0.8: A = .44/.89 = 0.4944, B = .45/.89 = 0.5056 -> B wins
    run = next(x for x in d["sensitivity"]["runs"] if x["criterion"] == "acc" and x["factor"] == 0.8)
    assert run["winner"] == "B" and run["winner_score"] == 0.5056
    assert d["sensitivity"]["winner_changes"] is True and d["sensitivity"]["challengers"] == ["B"]
    assert d["recommendation"]["robust_to_weight_changes"] is False
    md = (tmp_path / "out" / "decision.md").read_text(encoding="utf-8")
    assert "winner changes" in md and "[TO BE BASELINED — owner: Solution architect]" in md


def test_missing_weighted_value_scores_zero_with_owned_gap(tmp_path):
    cands = HEAD + ("A,p,api,us,1000,1,1,200,,s,2026-01-01\n"
                    "B,p,api,us,1000,1,1,100,0.9,,\n")
    crit = "criterion,weight,direction\nacc,1,higher\n"
    r, d = _run(tmp_path, cands, crit)
    assert r.returncode == 0, r.stderr
    by = {x["model"]: x for x in d["ranking"]}
    assert by["A"]["normalised"]["acc"] is None and by["A"]["score"] == 0.0
    assert by["B"]["normalised"]["acc"] == 1.0  # single value -> all equal -> 1.0
    issues = {(g["model"], g["criterion"]) for g in d["gaps"]}
    assert ("A", "acc") in issues and ("B", "source/as_of") in issues
    md = (tmp_path / "out" / "decision.md").read_text(encoding="utf-8")
    assert "[TO BE BASELINED — owner: Model evaluation lead]" in md
    assert "owner: ]" not in md and "owner: ___" not in md


def test_missing_value_on_hard_constraint_eliminates(tmp_path):
    cands = HEAD + ("A,p,api,,1000,1,1,200,0.8,s,2026-01-01\n"
                    "B,p,api,EU,1000,1,1,100,0.9,s,2026-01-01\n")
    crit = "criterion,weight,direction,hard_min,hard_max,hard_in\nacc,1,higher,,,\nregion,0,,,,eu;uk\n"
    r, d = _run(tmp_path, cands, crit)
    assert r.returncode == 0, r.stderr
    assert [e["model"] for e in d["eliminated"]] == ["A"]
    assert "cannot be verified" in d["eliminated"][0]["reasons"][0]
    assert d["recommendation"]["model"] == "B"  # 'EU' matches 'eu' case-insensitively


def test_cost_criterion_needs_workload_exit_2(tmp_path):
    r = run_script(SCRIPT, "--candidates", str(FX / "candidates.csv"), "--criteria", str(FX / "criteria.csv"),
                   "--out-dir", str(tmp_path / "out"))
    assert r.returncode == 2 and "needs --workload" in r.stderr


def test_input_errors_exit_2(tmp_path):
    r, _ = _run(tmp_path, "model,provider\nA,p\n", "criterion,weight,direction\nacc,1,higher\n")
    assert r.returncode == 2 and "missing required columns" in r.stderr
    r, _ = _run(tmp_path, HEAD + "A,p,cloud,us,1,1,1,1,1,s,d\n", "criterion,weight,direction\nacc,1,higher\n")
    assert r.returncode == 2 and "hosting must be" in r.stderr
    r, _ = _run(tmp_path, HEAD + "A,p,api,us,1,1,1,1,1,s,d\n", "criterion,weight,direction\nnot_a_col,1,higher\n")
    assert r.returncode == 2 and "not a candidates column" in r.stderr
    r, _ = _run(tmp_path, HEAD + "A,p,api,us,1,1,1,1,1,s,d\n", "criterion,weight,direction\nacc,1,\n")
    assert r.returncode == 2 and "direction must be" in r.stderr
    assert run_script(SCRIPT, "--candidates", str(tmp_path / "nope.csv")).returncode == 2


def test_verify_catches_tampered_score(tmp_path):
    out = tmp_path / "out"
    run_script(SCRIPT, "--candidates", str(FX / "candidates.csv"), "--criteria", str(FX / "criteria.csv"),
               "--workload", str(FX / "workload.csv"), "--out-dir", str(out))
    p = out / "ranking.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["ranking"][1]["score"] = 0.99
    p.write_text(json.dumps(d), encoding="utf-8")
    r = run_script(SCRIPT, "--verify", str(p))
    assert r.returncode == 1 and "recomputed" in r.stderr


def test_deterministic(tmp_path):
    outs = []
    for i in range(2):
        o = tmp_path / f"o{i}"
        run_script(SCRIPT, "--candidates", str(FX / "candidates.csv"), "--criteria", str(FX / "criteria.csv"),
                   "--workload", str(FX / "workload.csv"), "--out-dir", str(o))
        outs.append((o / "ranking.json").read_bytes() + (o / "decision.md").read_bytes())
    assert outs[0] == outs[1]


def test_offline_stdlib_only():
    src = (REPO_ROOT / SCRIPT).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(socket|urllib|requests|httpx|http\.client|subprocess)\b", src, re.M)

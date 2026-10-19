"""Tests for ai-platform/rag-pipeline-design/scripts/eval_retrieval.py."""
from __future__ import annotations

import json
from pathlib import Path

from conftest import copy_asset, run_script

SCRIPT = "skills/ai-platform/rag-pipeline-design/scripts/eval_retrieval.py"
CSV = "skills/ai-platform/rag-pipeline-design/assets/retrieval-eval-set.csv"


def test_help_exits_zero():
    r = run_script(SCRIPT, "--help")
    assert r.returncode == 0


def test_happy_path_reports_metrics(tmp_path):
    csvp = copy_asset(CSV, tmp_path)
    r = run_script(SCRIPT, "--csv", str(csvp))
    assert r.returncode == 0, r.stderr
    assert "recall@" in r.stdout
    assert "mrr" in r.stdout


def test_json_output(tmp_path):
    csvp = copy_asset(CSV, tmp_path)
    out = tmp_path / "results.json"
    r = run_script(SCRIPT, "--csv", str(csvp), "--json", str(out))
    assert r.returncode == 0, r.stderr
    assert out.exists()
    assert "overall" in json.loads(out.read_text(encoding="utf-8"))


def test_min_recall_gate_fails(tmp_path):
    # Example data has recall@1 = 0.5, so a 0.99 gate must fail.
    csvp = copy_asset(CSV, tmp_path)
    r = run_script(SCRIPT, "--csv", str(csvp), "--min-recall", "0.99", "--at", "1")
    assert r.returncode == 1
    assert "GATE FAILED" in r.stdout


def test_missing_columns(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("query_id,query\n1,hello\n", encoding="utf-8")
    r = run_script(SCRIPT, "--csv", str(bad))
    assert r.returncode == 1
    assert "CSV missing columns" in (r.stdout + r.stderr)


# --- brownfield: compare with an earlier run's metrics (--baseline / --max-drop) ---

from conftest import REPO_ROOT  # noqa: E402

FX = REPO_ROOT / "skills/ai-platform/rag-pipeline-design/evals/fixtures"


def _live(tmp_path, *extra):
    out = tmp_path / "m.json"
    r = run_script(SCRIPT, "--csv", str(FX / "eval-set-live.csv"), "--json", str(out),
                   "--baseline", str(FX / "metrics-baseline.json"), *extra)
    return r, (json.loads(out.read_text()) if out.exists() else None)


def test_baseline_deltas_and_query_movement(tmp_path):
    r, res = _live(tmp_path)
    assert r.returncode == 0, r.stderr
    vb = res["vs_baseline"]
    assert vb["overall"]["recall@5"] == 0.0333 and vb["overall"]["mrr"] == 0.0833
    assert (vb["newly_missed"], vb["newly_found"], vb["new_queries"], vb["dropped_queries"]) == (
        ["Q005"], ["Q006"], ["Q007"], [])
    assert vb["by_type"]["fact"]["recall@5"] == 0.05
    assert "newly_missed=Q005" in r.stdout


def test_max_drop_gate_fails_on_regression(tmp_path):
    worse = tmp_path / "worse.csv"
    worse.write_text("query_id,expected_doc_ids,retrieved_doc_ids\nQ001,d1,x\nQ002,d2,d2\n", encoding="utf-8")
    base = tmp_path / "base.json"
    run_script(SCRIPT, "--csv", str(worse), "--json", str(base))
    data = json.loads(base.read_text())
    data["overall"]["recall@5"] = 1.0  # the earlier release retrieved everything at 5
    base.write_text(json.dumps(data))
    r = run_script(SCRIPT, "--csv", str(worse), "--baseline", str(base), "--max-drop", "0.1")
    assert r.returncode == 1 and "REGRESSION GATE FAILED: recall@5 changed -0.5000" in r.stdout


def test_old_baseline_without_query_ids(tmp_path):
    base = json.loads((FX / "metrics-baseline.json").read_text())
    base.pop("in_scope_query_ids")
    p = tmp_path / "old.json"
    p.write_text(json.dumps(base))
    out = tmp_path / "m.json"
    r = run_script(SCRIPT, "--csv", str(FX / "eval-set-live.csv"), "--json", str(out), "--baseline", str(p))
    vb = json.loads(out.read_text())["vs_baseline"]
    assert r.returncode == 0 and vb["new_queries"] == [] and "lacks query ids" in vb["per_query_basis"]


def test_max_drop_without_baseline_and_bad_baseline(tmp_path):
    r = run_script(SCRIPT, "--csv", str(FX / "eval-set-live.csv"), "--max-drop", "0.1")
    assert r.returncode != 0 and "needs --baseline" in r.stderr
    bad = tmp_path / "bad.json"
    bad.write_text("[]")
    r = run_script(SCRIPT, "--csv", str(FX / "eval-set-live.csv"), "--baseline", str(bad))
    assert r.returncode != 0 and "metrics JSON" in r.stderr

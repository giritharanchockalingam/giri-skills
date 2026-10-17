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

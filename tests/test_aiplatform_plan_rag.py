"""Tests for ai-platform/langchain-rag-runner/scripts/plan_rag.py (hand-checked numbers)."""
from __future__ import annotations

import ast
import json
import re

from conftest import REPO_ROOT, run_script

SKILL = "skills/ai-platform/langchain-rag-runner"
SCRIPT = f"{SKILL}/scripts/plan_rag.py"

BASE_CFG = {"chunk_size_chars": 1000, "chunk_overlap_chars": 200, "embedding_price_per_1m_tokens": 0.02,
            "top_k": 5, "reranker": "no", "vector_store": "chroma", "context_budget_tokens": 6000,
            "embedding_model": "m", "embedding_provider": "openai", "price_date": "2026-10-01"}
CORPUS = "source,doc_count,avg_chars,update_frequency,change_fraction\n" \
         "policies,1200,3000,monthly,\n" \
         "faq,400,800,weekly,\n" \
         "contracts,250,24000,quarterly,0.25\n"


def _run(tmp_path, cfg=None, corpus=CORPUS):
    c = tmp_path / "cfg.json"
    c.write_text(json.dumps(BASE_CFG if cfg is None else cfg), encoding="utf-8")
    k = tmp_path / "corpus.csv"
    k.write_text(corpus, encoding="utf-8")
    out = tmp_path / "out"
    r = run_script(SCRIPT, "--corpus", str(k), "--config", str(c), "--out-dir", str(out))
    plan = json.loads((out / "rag-plan.json").read_text(encoding="utf-8")) if (out / "rag-plan.json").exists() else None
    return r, plan, out


def _src(plan, name):
    return next(s for s in plan["sizing"]["sources"] if s["source"] == name)


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_chunk_math_hand_checked(tmp_path):
    r, plan, _ = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    p = _src(plan, "policies")   # L=3000, C=1000, O=200: 1 + ceil(2000/800) = 4; E = 3000 + 3*200 = 3600
    assert (p["chunks_per_doc"], p["chunks"], p["embedded_chars_per_doc"]) == (4, 4800, 3600)
    assert p["embedding_tokens"] == 1_080_000           # 1200 * 3600 / 4
    f = _src(plan, "faq")        # L <= C: one chunk, no overlap duplication
    assert (f["chunks_per_doc"], f["chunks"], f["embedding_tokens"]) == (1, 400, 80_000)
    c = _src(plan, "contracts")  # 1 + ceil(23000/800) = 1 + 29 = 30; E = 24000 + 29*200 = 29800
    assert (c["chunks_per_doc"], c["chunks"], c["embedding_tokens"]) == (30, 7500, 1_862_500)
    assert plan["sizing"]["total_chunks"] == 12_700
    assert plan["sizing"]["total_embedding_tokens"] == 3_022_500


def test_cost_hand_checked(tmp_path):
    _, plan, _ = _run(tmp_path)
    assert _src(plan, "policies")["one_time_cost"] == 0.0216      # 1.08M tokens * 0.02 / 1M
    assert _src(plan, "policies")["monthly_cost"] == 0.0216       # monthly, full re-embed
    assert _src(plan, "faq")["monthly_reembed_tokens"] == 346_667  # 80000 * 52/12
    assert _src(plan, "contracts")["monthly_reembed_tokens"] == 155_209  # 1862500 * 1/3 * 0.25
    assert plan["sizing"]["one_time_cost"] == 0.0605              # 3.0225M * 0.02 / 1M = 0.06045
    assert plan["config"]["embedding_price_per_1m_tokens"] == 0.02


def test_retrieval_budget(tmp_path):
    _, plan, _ = _run(tmp_path)
    rb = plan["retrieval_budget"]
    assert rb["per_query_context_tokens"] == 1250                 # 5 * 1000 / 4
    assert rb["utilization_pct"] == 20.8 and rb["headroom_tokens"] == 4750 and rb["fits"] is True


def test_boundary_one_char_over_chunk(tmp_path):
    corpus = "source,doc_count,avg_chars,update_frequency\nx,1,1000,static\ny,1,1001,daily\n"
    _, plan, _ = _run(tmp_path, corpus=corpus)
    assert _src(plan, "x")["chunks_per_doc"] == 1 and _src(plan, "x")["monthly_cost"] == 0.0
    assert _src(plan, "y")["chunks_per_doc"] == 2                 # 1 + ceil(1/800)
    assert _src(plan, "y")["updates_per_month"] == 30.4167        # 365/12


def test_outputs_and_scaffold(tmp_path):
    _, plan, out = _run(tmp_path)
    md = (out / "rag-plan.md").read_text(encoding="utf-8")
    for h in ("## Sizing", "## Cost", "## Retrieval budget", "## Warnings", "## Scaffold"):
        assert h in md
    src = (out / "rag_pipeline.py").read_text(encoding="utf-8")
    defs = {n.name for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)}
    assert {"make_embeddings", "make_vector_store", "ingest", "retrieve"} <= defs
    assert "CHUNK_SIZE = 1000" in src and "TOP_K = 5" in src and "from langchain_chroma import Chroma" in src
    assert plan["scaffold"]["executed"] is False


def test_missing_price_blocks_and_is_not_assumed(tmp_path):
    cfg = {k: v for k, v in BASE_CFG.items() if k != "embedding_price_per_1m_tokens"}
    r, plan, out = _run(tmp_path, cfg)
    assert r.returncode == 1
    assert "config.embedding_price_per_1m_tokens is missing (no default is assumed)" in plan["blocking_errors"]
    assert plan["sizing"] is None and not (out / "rag_pipeline.py").exists()


def test_overlap_not_less_than_chunk_blocks(tmp_path):
    r, plan, _ = _run(tmp_path, {**BASE_CFG, "chunk_overlap_chars": 1000})
    assert r.returncode == 1
    assert any("the splitter cannot advance" in e for e in plan["blocking_errors"])


def test_context_overflow_blocks(tmp_path):
    r, plan, out = _run(tmp_path, {**BASE_CFG, "top_k": 30})      # 30 * 1000 / 4 = 7500 > 6000
    assert r.returncode == 1
    assert plan["retrieval_budget"]["per_query_context_tokens"] == 7500
    assert any("exceeds the context budget" in e for e in plan["blocking_errors"])
    assert not (out / "rag_pipeline.py").exists()


def test_reranker_fetch_k_rules(tmp_path):
    r, plan, _ = _run(tmp_path, {**BASE_CFG, "reranker": "yes", "rerank_fetch_k": 3})
    assert r.returncode == 1 and any("rerank_fetch_k (3) < top_k (5)" in e for e in plan["blocking_errors"])
    r, plan, out = _run(tmp_path, {**BASE_CFG, "reranker": "yes"})
    assert r.returncode == 0
    assert any("rerank_fetch_k is not set" in w for w in plan["warnings"])
    assert "[TO BE BASELINED — owner: Search/retrieval engineer]" in (out / "rag-plan.md").read_text(encoding="utf-8")


def test_store_and_overlap_warnings(tmp_path):
    _, plan, out = _run(tmp_path, {**BASE_CFG, "vector_store": "inmemory", "chunk_overlap_chars": 0})
    w = "\n".join(plan["warnings"])
    assert "in-memory" in w and "chunk_overlap_chars is 0" in w
    _, plan, out = _run(tmp_path, {**BASE_CFG, "vector_store": "faiss"})
    assert any("pickle" in x for x in plan["warnings"])
    assert "FAISS.from_documents" in (out / "rag_pipeline.py").read_text(encoding="utf-8")


def test_missing_model_and_date_become_owned_tbd(tmp_path):
    cfg = {k: v for k, v in BASE_CFG.items() if k not in ("embedding_model", "price_date")}
    _, _, out = _run(tmp_path, cfg)
    md = (out / "rag-plan.md").read_text(encoding="utf-8")
    assert md.count("[TO BE BASELINED — owner: ML platform lead]") >= 2
    assert "[TO BE BASELINED]" not in md


def test_bad_corpus_rows_block(tmp_path):
    corpus = "source,doc_count,avg_chars,update_frequency\nx,ten,1000,monthly\ny,1,500,fortnightly\n"
    r, plan, _ = _run(tmp_path, corpus=corpus)
    errs = "\n".join(plan["blocking_errors"])
    assert r.returncode == 1 and "doc_count must be a number" in errs and "update_frequency" in errs


def test_missing_files_exit_2(tmp_path):
    k = tmp_path / "c.csv"
    k.write_text(CORPUS, encoding="utf-8")
    assert run_script(SCRIPT, "--corpus", str(k), "--config", str(tmp_path / "no.json"), "--out-dir", str(tmp_path / "o")).returncode == 2
    c = tmp_path / "cfg.json"
    c.write_text(json.dumps(BASE_CFG), encoding="utf-8")
    assert run_script(SCRIPT, "--corpus", str(tmp_path / "no.csv"), "--config", str(c), "--out-dir", str(tmp_path / "o")).returncode == 2


def test_fixtures_are_labelled_fictional():
    fx = REPO_ROOT / SKILL / "evals" / "fixtures"
    for f in fx.glob("*.json"):
        assert "fictional" in json.loads(f.read_text(encoding="utf-8"))["_note"]
    for line in (fx / "corpus.csv").read_text(encoding="utf-8").splitlines()[1:]:
        assert line.endswith("fictional fixture")


def test_scripts_have_no_network_or_subprocess():
    for f in (REPO_ROOT / SKILL / "scripts").glob("*.py"):
        src = f.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+(socket|urllib|requests|http|subprocess)\b", src, re.M), f

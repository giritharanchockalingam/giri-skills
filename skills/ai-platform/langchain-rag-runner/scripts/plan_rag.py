#!/usr/bin/env python3
"""RAG sizing, embedding cost, retrieval budget and a LangChain pipeline scaffold.

Turns a corpus profile and a RAG config into numbers, applying the splitter/vector-store
guidance of the upstream `langchain-rag` skill (langchain-ai/langchain-skills, pinned in
vendor/pins.json). No price, model or threshold is built in: every figure comes from the inputs.

Corpus CSV columns: source, doc_count, avg_chars, update_frequency [, change_fraction, notes]
  update_frequency: static|yearly|quarterly|monthly|weekly|daily, or a number of updates per month
  change_fraction: share of the source re-embedded per update (0-1); default 1 (full re-embed)
Config JSON keys:
  required  chunk_size_chars, chunk_overlap_chars, embedding_price_per_1m_tokens, top_k,
            reranker (yes/no), vector_store, context_budget_tokens
  optional  embedding_model, embedding_provider, rerank_fetch_k, chars_per_token (default 4),
            currency, price_date

Method (per source; L = avg_chars, C = chunk size, O = overlap, S = C - O):
  chunks per doc        n = 1 if L <= C else 1 + ceil((L - C) / S)
  embedded chars / doc  L + (n - 1) * O          (overlap is embedded twice)
  embedding tokens      ceil(doc_count * embedded chars / chars_per_token)   -- an estimate
  one-time cost         tokens / 1M * price
  monthly re-embedding  tokens * updates_per_month * change_fraction / 1M * price
  per-query context     ceil(top_k * C / chars_per_token) vs context_budget_tokens

Blocking errors (exit 1; no rag_pipeline.py): missing/invalid config keys; overlap >= chunk size;
rerank_fetch_k < top_k; top_k x chunk tokens > context budget; invalid corpus rows.

Usage: python3 -I plan_rag.py --corpus corpus.csv --config rag-config.json --out-dir OUT
Writes OUT/rag-plan.json and OUT/rag-plan.md always; OUT/rag_pipeline.py only without blocking
errors. The scaffold is generated as text and syntax-checked, never executed.
Exit: 0 ok · 1 blocking config/corpus errors · 2 an input file missing or unreadable. Stdlib only.
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import sys
from pathlib import Path

FREQ_PER_MONTH = {"static": 0.0, "never": 0.0, "yearly": 1 / 12, "annual": 1 / 12, "quarterly": 1 / 3,
                  "monthly": 1.0, "weekly": 52 / 12, "daily": 365 / 12}
REQUIRED = ("chunk_size_chars", "chunk_overlap_chars", "embedding_price_per_1m_tokens", "top_k",
            "reranker", "vector_store", "context_budget_tokens")
STORES = {"chroma": "chroma", "faiss": "faiss", "inmemory": "inmemory", "in-memory": "inmemory",
          "in_memory": "inmemory", "pinecone": "pinecone", "pgvector": "pgvector", "postgres": "pgvector"}
TBD_MODEL = "[TO BE BASELINED — owner: ML platform lead]"
TBD_DATE = "[TO BE BASELINED — owner: ML platform lead]"
TBD_FETCH = "[TO BE BASELINED — owner: Search/retrieval engineer]"
TBD_PATH = "[TO BE BASELINED — owner: Data owner]"


# ------------------------------------------------------------------ inputs

def _num(v, name: str, errors: list[str], *, integer=False, minimum=None, strict=False):
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        errors.append(f"{name} must be a number, got {v!r}")
        return None
    if integer and x != int(x):
        errors.append(f"{name} must be a whole number, got {v!r}")
        return None
    if minimum is not None and (x <= minimum if strict else x < minimum):
        errors.append(f"{name} must be {'>' if strict else '>='} {minimum}, got {v!r}")
        return None
    return int(x) if integer or x.is_integer() else x


def _yes(v) -> bool | None:
    s = str(v).strip().lower()
    if v is True or s in ("yes", "y", "true", "1"):
        return True
    if v is False or s in ("no", "n", "false", "0"):
        return False
    return None


def read_config(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"error: config not found: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"error: config is not valid JSON: {e}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(data, dict):
        print("error: config must be a JSON object", file=sys.stderr)
        sys.exit(2)
    return data


def read_corpus(path: Path) -> list[dict]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
            header = rows[0].keys() if rows else []
    except FileNotFoundError:
        print(f"error: corpus profile not found: {path}", file=sys.stderr)
        sys.exit(2)
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in rows] if header else []


def parse_config(cfg: dict, errors: list[str]) -> dict:
    c: dict = {}
    for k in REQUIRED:
        if cfg.get(k) in (None, ""):
            errors.append(f"config.{k} is missing (no default is assumed)")
    if errors:
        return c
    c["chunk_size_chars"] = _num(cfg["chunk_size_chars"], "chunk_size_chars", errors, integer=True, minimum=0, strict=True)
    c["chunk_overlap_chars"] = _num(cfg["chunk_overlap_chars"], "chunk_overlap_chars", errors, integer=True, minimum=0)
    c["embedding_price_per_1m_tokens"] = _num(cfg["embedding_price_per_1m_tokens"], "embedding_price_per_1m_tokens", errors, minimum=0)
    c["top_k"] = _num(cfg["top_k"], "top_k", errors, integer=True, minimum=1)
    c["context_budget_tokens"] = _num(cfg["context_budget_tokens"], "context_budget_tokens", errors, integer=True, minimum=0, strict=True)
    c["chars_per_token"] = _num(cfg.get("chars_per_token", 4), "chars_per_token", errors, minimum=0, strict=True)
    c["reranker"] = _yes(cfg["reranker"])
    if c["reranker"] is None:
        errors.append(f"config.reranker must be yes or no, got {cfg['reranker']!r}")
    c["vector_store"] = str(cfg["vector_store"]).strip()
    c["store_kind"] = STORES.get(c["vector_store"].lower().replace(" ", ""), "other")
    c["embedding_model"] = str(cfg.get("embedding_model") or "").strip()
    c["embedding_provider"] = str(cfg.get("embedding_provider") or "").strip().lower()
    c["currency"] = str(cfg.get("currency") or "").strip()
    c["price_date"] = str(cfg.get("price_date") or "").strip()
    fk = cfg.get("rerank_fetch_k")
    c["rerank_fetch_k"] = _num(fk, "rerank_fetch_k", errors, integer=True, minimum=1) if fk not in (None, "") else None
    if c.get("chunk_size_chars") and c.get("chunk_overlap_chars") is not None and c["chunk_overlap_chars"] >= c["chunk_size_chars"]:
        errors.append(f"chunk_overlap_chars ({c['chunk_overlap_chars']}) >= chunk_size_chars ({c['chunk_size_chars']}): "
                      "the splitter cannot advance")
    if c.get("reranker") and c.get("rerank_fetch_k") is not None and c.get("top_k") and c["rerank_fetch_k"] < c["top_k"]:
        errors.append(f"rerank_fetch_k ({c['rerank_fetch_k']}) < top_k ({c['top_k']}): the reranker cannot return top_k results")
    return c


def parse_corpus(rows: list[dict], errors: list[str]) -> list[dict]:
    if not rows:
        errors.append("corpus profile has no rows")
        return []
    need = {"source", "doc_count", "avg_chars", "update_frequency"}
    missing = need - set(rows[0])
    if missing:
        errors.append(f"corpus profile lacks columns {sorted(missing)}")
        return []
    out = []
    for i, r in enumerate(rows, start=2):
        tag = f"corpus line {i} ({r.get('source') or '?'})"
        e0 = len(errors)
        if not r["source"]:
            errors.append(f"{tag}: source is empty")
        dc = _num(r["doc_count"], f"{tag}: doc_count", errors, integer=True, minimum=0)
        ac = _num(r["avg_chars"], f"{tag}: avg_chars", errors, minimum=0, strict=True)
        fq = r["update_frequency"].lower()
        if fq in FREQ_PER_MONTH:
            upm = FREQ_PER_MONTH[fq]
        else:
            upm = _num(fq, f"{tag}: update_frequency (not in {sorted(FREQ_PER_MONTH)} or a per-month number)", errors, minimum=0)
        cf = r.get("change_fraction", "")
        chf = _num(cf, f"{tag}: change_fraction", errors, minimum=0) if cf else 1.0
        if chf is not None and chf > 1:
            errors.append(f"{tag}: change_fraction must be <= 1, got {cf!r}")
        if len(errors) == e0:
            out.append({"source": r["source"], "doc_count": dc, "avg_chars": ac, "update_frequency": r["update_frequency"],
                        "updates_per_month": upm, "change_fraction": chf, "change_fraction_supplied": bool(cf)})
    return out


# ------------------------------------------------------------------ math

def chunks_per_doc(avg_chars: float, size: int, overlap: int) -> int:
    """Sliding-window chunk count for one document of avg_chars characters."""
    if avg_chars <= size:
        return 1
    return 1 + math.ceil((avg_chars - size) / (size - overlap))


def size_corpus(sources: list[dict], c: dict) -> dict:
    C, O, cpt, price = c["chunk_size_chars"], c["chunk_overlap_chars"], c["chars_per_token"], c["embedding_price_per_1m_tokens"]
    rows, t_chunks, t_tokens, t_month_tokens = [], 0, 0, 0.0
    for s in sources:
        n = chunks_per_doc(s["avg_chars"], C, O)
        emb_chars = s["avg_chars"] + (n - 1) * O
        chunks = s["doc_count"] * n
        tokens = math.ceil(s["doc_count"] * emb_chars / cpt)
        month_tokens = tokens * s["updates_per_month"] * s["change_fraction"]
        rows.append({"source": s["source"], "doc_count": s["doc_count"], "avg_chars": s["avg_chars"],
                     "chunks_per_doc": n, "chunks": chunks, "embedded_chars_per_doc": emb_chars,
                     "embedding_tokens": tokens, "update_frequency": s["update_frequency"],
                     "updates_per_month": round(s["updates_per_month"], 4), "change_fraction": s["change_fraction"],
                     "monthly_reembed_tokens": math.ceil(month_tokens),
                     "one_time_cost": round(tokens / 1e6 * price, 4),
                     "monthly_cost": round(month_tokens / 1e6 * price, 4)})
        t_chunks += chunks
        t_tokens += tokens
        t_month_tokens += month_tokens
    return {"sources": rows, "total_chunks": t_chunks, "total_embedding_tokens": t_tokens,
            "total_monthly_reembed_tokens": math.ceil(t_month_tokens),
            "one_time_cost": round(t_tokens / 1e6 * price, 4),
            "monthly_cost": round(t_month_tokens / 1e6 * price, 4),
            "annual_cost_first_year": round(t_tokens / 1e6 * price + 12 * t_month_tokens / 1e6 * price, 4)}


def retrieval_budget(c: dict) -> dict:
    per_query = math.ceil(c["top_k"] * c["chunk_size_chars"] / c["chars_per_token"])
    return {"top_k": c["top_k"], "chunk_size_chars": c["chunk_size_chars"], "per_query_context_tokens": per_query,
            "context_budget_tokens": c["context_budget_tokens"],
            "utilization_pct": round(100 * per_query / c["context_budget_tokens"], 1),
            "headroom_tokens": c["context_budget_tokens"] - per_query,
            "fits": per_query <= c["context_budget_tokens"],
            "reranker": c["reranker"], "rerank_fetch_k": c["rerank_fetch_k"]}


def warnings_for(c: dict, sizing: dict | None) -> list[str]:
    w = []
    if c.get("chunk_overlap_chars") == 0:
        w.append("chunk_overlap_chars is 0: text that spans a chunk boundary is split with no shared context")
    if c.get("store_kind") == "inmemory":
        w.append(f"vector store '{c['vector_store']}' is in-memory: the index is lost on restart; use a persistent store beyond tests")
    if c.get("store_kind") == "faiss":
        w.append("FAISS indexes load with pickle-backed metadata: only load indexes this pipeline created and controls")
    if c.get("store_kind") == "other":
        w.append(f"vector store '{c.get('vector_store')}' has no scaffold template: make_vector_store() raises until you implement it")
    if c.get("reranker") and c.get("rerank_fetch_k") is None:
        w.append(f"reranker is on but rerank_fetch_k is not set: candidate count {TBD_FETCH}")
    if not c.get("embedding_model"):
        w.append(f"embedding_model not set: {TBD_MODEL}; index and query must use the same model")
    if c.get("embedding_price_per_1m_tokens") == 0:
        w.append("embedding price is 0: confirm (self-hosted embeddings still carry compute cost)")
    if not c.get("price_date"):
        w.append(f"price_date not set: embedding price date {TBD_DATE}")
    if sizing:
        for s in sizing["sources"]:
            if s["avg_chars"] <= c["chunk_size_chars"]:
                w.append(f"source '{s['source']}': average document ({s['avg_chars']} chars) fits in one chunk; chunking has no effect")
    return w


# ------------------------------------------------------------------ scaffold

def gen_python(c: dict, sources: list[dict], cfg_name: str) -> str:
    model = c["embedding_model"] or None
    L = [f'"""RAG ingestion + retrieval scaffold generated by langchain-rag-runner from {cfg_name}.',
         "",
         "Generated as text and syntax-checked (compile/ast.parse) by langchain-rag-runner; it was NOT",
         "executed. Follows the langchain-rag guidance (vendor/pins.json): one embeddings object for",
         "indexing and querying, RecursiveCharacterTextSplitter with overlap, a persistent store.",
         '"""',
         "from __future__ import annotations", "",
         "import os",
         "from typing import Any", "",
         "from langchain_community.document_loaders import DirectoryLoader, TextLoader",
         "from langchain_text_splitters import RecursiveCharacterTextSplitter", "",
         f"CHUNK_SIZE = {c['chunk_size_chars']}",
         f"CHUNK_OVERLAP = {c['chunk_overlap_chars']}",
         f"TOP_K = {c['top_k']}",
         f"USE_RERANKER = {bool(c['reranker'])}",
         f"RERANK_FETCH_K = {c['rerank_fetch_k']!r}" + (f"  # {TBD_FETCH}" if c["reranker"] and c["rerank_fetch_k"] is None else ""),
         f"EMBEDDING_MODEL = {model!r}" + (f"  # {TBD_MODEL}" if not model else ""),
         f"EMBEDDING_PROVIDER = {c['embedding_provider'] or None!r}",
         f"VECTOR_STORE = {c['vector_store']!r}",
         "COLLECTION = os.environ.get(\"RAG_COLLECTION\", \"rag\")",
         "PERSIST_DIR = os.environ.get(\"RAG_PERSIST_DIR\", \"./vector_index\")",
         "LOADER_GLOB = \"**/*.txt\"  # assumption: plain-text files; swap the loader for PDF/HTML sources", "",
         "# One entry per corpus-profile source. Point each at the real location.",
         "SOURCES: dict[str, str] = {"]
    for s in sources:
        L.append(f"    {s['source']!r}: os.environ.get({('RAG_SRC_' + ''.join(ch if ch.isalnum() else '_' for ch in s['source']).upper())!r}, ''),  # {TBD_PATH}")
    L += ["}", "", "",
          "def make_embeddings() -> Any:",
          '    """The ONE embeddings object used for both indexing and querying (same model, same dimensions)."""',
          "    if not EMBEDDING_MODEL:",
          "        raise NotImplementedError(\"choose EMBEDDING_MODEL before ingesting\")",
          "    if EMBEDDING_PROVIDER == \"openai\":",
          "        from langchain_openai import OpenAIEmbeddings",
          "        return OpenAIEmbeddings(model=EMBEDDING_MODEL)",
          "    raise NotImplementedError(f\"embeddings provider {EMBEDDING_PROVIDER!r}: construct its LangChain Embeddings here\")",
          "", "",
          "def make_vector_store(embeddings: Any, splits: list | None = None) -> Any:",
          f'    """Open (or build from `splits`) the {c["vector_store"]} store."""']
    k = c["store_kind"]
    if k == "chroma":
        L += ["    from langchain_chroma import Chroma",
              "    store = Chroma(collection_name=COLLECTION, embedding_function=embeddings, persist_directory=PERSIST_DIR)",
              "    if splits:",
              "        store.add_documents(splits)",
              "    return store"]
    elif k == "faiss":
        L += ["    from langchain_community.vectorstores import FAISS",
              "    if splits:",
              "        store = FAISS.from_documents(splits, embeddings)",
              "        store.save_local(PERSIST_DIR)",
              "        return store",
              "    # Only load an index this pipeline created and controls (pickle-backed metadata).",
              "    return FAISS.load_local(PERSIST_DIR, embeddings, allow_dangerous_deserialization=True)"]
    elif k == "inmemory":
        L += ["    from langchain_core.vectorstores import InMemoryVectorStore",
              "    store = InMemoryVectorStore(embeddings)  # lost on restart: tests only",
              "    if splits:",
              "        store.add_documents(splits)",
              "    return store"]
    elif k == "pinecone":
        L += ["    from langchain_pinecone import PineconeVectorStore",
              "    store = PineconeVectorStore(index_name=os.environ[\"PINECONE_INDEX\"], embedding=embeddings)",
              "    if splits:",
              "        store.add_documents(splits)",
              "    return store"]
    elif k == "pgvector":
        L += ["    from langchain_postgres import PGVector",
              "    store = PGVector(embeddings=embeddings, collection_name=COLLECTION, connection=os.environ[\"PGVECTOR_DSN\"])",
              "    if splits:",
              "        store.add_documents(splits)",
              "    return store"]
    else:
        L += [f"    raise NotImplementedError({('vector store ' + repr(c['vector_store']) + ': no template; construct it here')!r})"]
    L += ["", "",
          "def ingest() -> Any:",
          '    """Load every source, split with the configured size/overlap, embed and index."""',
          "    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)",
          "    splits = []",
          "    for group, path in SOURCES.items():",
          "        if not path:",
          "            raise ValueError(f\"source {group!r} has no location configured\")",
          "        docs = DirectoryLoader(path, glob=LOADER_GLOB, loader_cls=TextLoader).load()",
          "        for d in docs:",
          "            d.metadata[\"source_group\"] = group",
          "        splits.extend(splitter.split_documents(docs))",
          "    return make_vector_store(make_embeddings(), splits)", "", "",
          "def rerank(query: str, docs: list) -> list:",
          '    """Plug in the chosen reranker; return docs best-first."""',
          "    raise NotImplementedError(\"reranker not implemented\")", "", "",
          "def retrieve(store: Any, query: str) -> list:",
          '    """Top-k retrieval; with a reranker, fetch RERANK_FETCH_K candidates and keep the best TOP_K."""',
          "    if USE_RERANKER:",
          "        if not RERANK_FETCH_K:",
          "            raise NotImplementedError(\"set RERANK_FETCH_K before enabling the reranker\")",
          "        docs = store.as_retriever(search_kwargs={\"k\": RERANK_FETCH_K}).invoke(query)",
          "        return rerank(query, docs)[:TOP_K]",
          "    return store.as_retriever(search_kwargs={\"k\": TOP_K}).invoke(query)", "", "",
          "if __name__ == \"__main__\":",
          "    vector_store = ingest()",
          "    for doc in retrieve(vector_store, input(\"query> \")):",
          "        print(doc.metadata.get(\"source_group\"), doc.page_content[:200])", ""]
    return "\n".join(L)


def syntax_check(src: str) -> tuple[bool, str]:
    try:
        compile(src, "rag_pipeline.py", "exec")
        ast.parse(src)
        return True, "compile() and ast.parse() succeeded"
    except SyntaxError as e:
        return False, f"SyntaxError line {e.lineno}: {e.msg}"


# ------------------------------------------------------------------ report

def _n(x) -> str:
    """Integers with thousands separators; floats exactly as stored in rag-plan.json."""
    if isinstance(x, bool) or x is None:
        return str(x)
    if isinstance(x, int) or (isinstance(x, float) and x.is_integer() and abs(x) >= 1000):
        return f"{int(x):,}"
    return repr(x)


def gen_markdown(plan: dict, corpus_name: str, cfg_name: str) -> str:
    c, sz, rb = plan["config"], plan.get("sizing"), plan.get("retrieval_budget")
    cur = c.get("currency") or "price units"
    L = [f"# RAG plan — {cfg_name}", "",
         f"Verdict: **{'READY' if plan['ok'] else 'BLOCKED'}** — {len(plan['blocking_errors'])} blocking error(s), "
         f"{len(plan['warnings'])} warning(s). Inputs: `{corpus_name}`, `{cfg_name}`. "
         "Wraps langchain-rag from langchain-ai/langchain-skills (pinned in vendor/pins.json).", ""]
    if plan["blocking_errors"]:
        L += ["Blocking errors (fix the inputs and re-run):", ""] + [f"- {e}" for e in plan["blocking_errors"]] + [""]
    L += ["## Sizing", ""]
    if sz:
        L += [f"Chunk size {_n(c['chunk_size_chars'])} chars, overlap {_n(c['chunk_overlap_chars'])} chars; "
              f"tokens estimated as characters / {_n(c['chars_per_token'])} (an estimate, not a tokenizer count). "
              "Chunks per document use the average length, so real counts vary with separators and length spread.", "",
              "| Source | Docs | Avg chars | Chunks/doc | Chunks | Embedding tokens (est.) | Update frequency |",
              "|---|---|---|---|---|---|---|"]
        for s in sz["sources"]:
            L.append(f"| {s['source']} | {_n(s['doc_count'])} | {_n(s['avg_chars'])} | {_n(s['chunks_per_doc'])} | "
                     f"{_n(s['chunks'])} | {_n(s['embedding_tokens'])} | {s['update_frequency']} |")
        L += [f"| **Total** | | | | **{_n(sz['total_chunks'])}** | **{_n(sz['total_embedding_tokens'])}** | |", ""]
    else:
        L += ["Not computed: blocking errors in the inputs.", ""]
    L += ["## Cost", ""]
    if sz:
        date = c.get("price_date") or TBD_DATE
        L += [f"Embedding price: {_n(c['embedding_price_per_1m_tokens'])} {cur} per 1M tokens (user-supplied; price date: {date}). "
              "Monthly re-embedding = tokens × updates per month × change fraction (1 = full re-embed unless supplied).", "",
              f"| Source | One-time ({cur}) | Updates/month | Change fraction | Re-embed tokens/month | Monthly ({cur}) |",
              "|---|---|---|---|---|---|"]
        for s in sz["sources"]:
            L.append(f"| {s['source']} | {_n(s['one_time_cost'])} | {_n(s['updates_per_month'])} | {_n(s['change_fraction'])} | "
                     f"{_n(s['monthly_reembed_tokens'])} | {_n(s['monthly_cost'])} |")
        L += [f"| **Total** | **{_n(sz['one_time_cost'])}** | | | **{_n(sz['total_monthly_reembed_tokens'])}** | **{_n(sz['monthly_cost'])}** |", "",
              f"First-year embedding spend (one-time + 12 × monthly): {_n(sz['annual_cost_first_year'])} {cur}. "
              "Excludes vector-store hosting, query-time embedding, reranker and generation costs.", ""]
    else:
        L += ["Not computed: blocking errors in the inputs.", ""]
    L += ["## Retrieval budget", ""]
    if rb:
        L += ["| Item | Value |", "|---|---|",
              f"| top_k | {_n(rb['top_k'])} |",
              f"| Retrieved context per query (top_k × chunk size, est. tokens) | {_n(rb['per_query_context_tokens'])} |",
              f"| Context budget for retrieved text (input) | {_n(rb['context_budget_tokens'])} |",
              f"| Utilization | {_n(rb['utilization_pct'])}% |",
              f"| Headroom (tokens) | {_n(rb['headroom_tokens'])} |",
              f"| Fits | {'yes' if rb['fits'] else 'NO — blocking'} |",
              f"| Reranker | {'yes' if rb['reranker'] else 'no'}"
              + (f"; candidates fetched: {_n(rb['rerank_fetch_k']) if rb['rerank_fetch_k'] is not None else TBD_FETCH}" if rb["reranker"] else "") + " |", ""]
    else:
        L += ["Not computed: blocking errors in the inputs.", ""]
    L += ["## Warnings", ""]
    L += [f"- {w}" for w in plan["warnings"]] or ["None."]
    L += ["", "## Scaffold", "", f"`rag_pipeline.py`: {plan['scaffold']['status']}."]
    if plan["scaffold"]["generated"]:
        L += ["", "| Step | Function | Config |", "|---|---|---|",
              f"| Load + split | `ingest()` | RecursiveCharacterTextSplitter(chunk_size={c['chunk_size_chars']}, chunk_overlap={c['chunk_overlap_chars']}) |",
              f"| Embed | `make_embeddings()` | model: {c.get('embedding_model') or TBD_MODEL} |",
              f"| Index | `make_vector_store()` | {c['vector_store']} |",
              f"| Retrieve | `retrieve()` | top_k {_n(c['top_k'])}{', reranker' if c['reranker'] else ''} |",
              "", "Set each source location (`RAG_SRC_*` environment variables), install the LangChain packages for the chosen store and embeddings, then run it; it has not been executed here."]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RAG sizing, cost, retrieval budget and LangChain scaffold")
    ap.add_argument("--corpus", required=True, help="corpus profile CSV (layout: assets/corpus-profile.example.csv)")
    ap.add_argument("--config", required=True, help="RAG config JSON (layout: assets/rag-config.example.json)")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    cfg_path, corpus_path = Path(a.config), Path(a.corpus)
    cfg_raw = read_config(cfg_path)
    rows = read_corpus(corpus_path)
    errors: list[str] = []
    c = parse_config(cfg_raw, errors)
    sources = parse_corpus(rows, errors)
    sizing = rb = None
    if not errors:
        sizing = size_corpus(sources, c)
        rb = retrieval_budget(c)
        if not rb["fits"]:
            errors.append(f"top_k × chunk size = {rb['per_query_context_tokens']} est. tokens exceeds the context budget "
                          f"of {rb['context_budget_tokens']}: lower top_k or chunk size, or raise the budget")
    warns = warnings_for(c, sizing) if c else []
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    scaffold = {"generated": False, "syntax_checked": False, "executed": False, "status": "not generated (blocking errors)"}
    if not errors:
        src = gen_python(c, sources, cfg_path.name)
        ok, detail = syntax_check(src)
        scaffold = {"generated": ok, "syntax_checked": ok, "executed": False, "detail": detail,
                    "status": f"generated and syntax-checked ({detail}); not executed"}
        if ok:
            (out / "rag_pipeline.py").write_text(src, encoding="utf-8")
        else:
            errors.append(f"generated scaffold failed the syntax check: {detail}")
    plan = {"ok": not errors, "inputs": {"corpus": corpus_path.name, "config": cfg_path.name},
            "config": {k: v for k, v in c.items()}, "blocking_errors": errors, "warnings": warns,
            "method": {"chunks_per_doc": "1 if L <= C else 1 + ceil((L - C) / (C - O))",
                       "embedded_chars_per_doc": "L + (n - 1) * O",
                       "tokens": "ceil(doc_count * embedded_chars / chars_per_token) (estimate)",
                       "monthly_reembed_tokens": "tokens * updates_per_month * change_fraction"},
            "sizing": sizing, "retrieval_budget": rb, "scaffold": scaffold,
            "upstream": "langchain-rag (langchain-ai/langchain-skills, vendor/pins.json)"}
    (out / "rag-plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "rag-plan.md").write_text(gen_markdown(plan, corpus_path.name, cfg_path.name), encoding="utf-8")
    print(f"RAG plan: {'READY' if plan['ok'] else 'BLOCKED'} — {len(errors)} blocking error(s), {len(warns)} warning(s); wrote {out}")
    for e in errors:
        print(f"  error: {e}", file=sys.stderr)
    return 0 if plan["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

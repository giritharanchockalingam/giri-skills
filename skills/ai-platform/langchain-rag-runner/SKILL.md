---
name: langchain-rag-runner
description: Use when the user is building a LangChain RAG pipeline and needs the numbers and starter code — "how many chunks will our corpus make", "what will embedding cost, one-time and monthly", "does top_k fit the context window", "generate the ingestion and retrieval code". Produces rag-plan.json and rag-plan.md (sizing per source, one-time and monthly re-embedding cost from a user-supplied price, retrieval budget vs context, warnings, scaffold summary) and a syntax-checked LangChain ingestion + retrieval scaffold rag_pipeline.py; optional LLM review against the upstream langchain-rag guidance. Not for retrieval-quality evaluation or chunking-strategy trade-offs (rag-pipeline-design) or GPU sizing (infra-gpu-sizing).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: build
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: corpus, type: csv, required: true, from: "corpus profile CSV: source, doc_count, avg_chars, update_frequency (static|yearly|quarterly|monthly|weekly|daily or updates per month), optional change_fraction (layout: assets/corpus-profile.example.csv)"}
      - {name: config, type: json, required: true, from: "RAG config JSON: chunk_size_chars, chunk_overlap_chars, embedding_price_per_1m_tokens (user-supplied, no default), top_k, reranker yes/no, vector_store, context_budget_tokens; optional embedding_model, embedding_provider, rerank_fetch_k, chars_per_token, currency, price_date (layout: assets/rag-config.example.json)"}
      - {name: review, type: flag, required: false, flag: "--review", from: "yes to add an LLM review of the plan against the upstream langchain-rag guidance"}
      - {name: current_config, type: json, required: false, from: "the RAG config JSON the live index was built with; adds the change plan (re-index needed or not, its cost, deltas)"}
    run:
      - {step: plan, kind: script, cmd: "python3 -I scripts/plan_rag.py --corpus {corpus} --config {config} [--current-config {current_config}] --out-dir {out}", stdout: "{out}/plan.log"}
      - {step: upstream-review, kind: llm, template: assets/rag-review-template.md, context: ["../../../vendor/langchain-rag/SKILL.md", "{out}/rag-plan.md", "{out}/rag-plan.json", "{out}/rag_pipeline.py"], out: "{out}/rag-review.md", skip_if_missing: [review]}
    outputs:
      - {path: "{out}/rag-plan.json", checks: [exists, json, contains:"\"ok\": true"]}
      - {path: "{out}/rag-plan.md", checks: [exists, sections:["Sizing","Cost","Retrieval budget","Warnings","Scaffold"], no_unowned_tbd, numbers_trace_to:"{out}/rag-plan.json"]}
      - {path: "{out}/rag_pipeline.py", checks: [exists, contains:"RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)", cmd:"python3 scripts/check_syntax.py {path} --require ingest --require retrieve --require make_embeddings --require make_vector_store"]}
    modes:
      new:      {case: agent-happy-path, bring: "your corpus profile and the RAG settings you plan"}
      existing: {case: agent-mode-existing, bring: "your corpus profile, live index settings and the change"}
---

# LangChain RAG Runner

Wraps langchain-rag from langchain-ai/langchain-skills (pinned in vendor/pins.json). The upstream skill is instructions only; this skill turns its splitter, embedding and vector-store guidance into sizing and cost arithmetic, blocking config checks and a generated scaffold. Upstream text is not copied: the optional review step reads `vendor/langchain-rag/SKILL.md` directly.

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/langchain-rag-runner --input <name>=<value> … --out <dir>` (see `--explain ai-platform/langchain-rag-runner`). Report the `run.json` results; do not hand-write the deliverables the scripts produce (`rag-plan.json`, `rag-plan.md`, `rag_pipeline.py`). A blocked plan (exit 1) is the gate working: fix the config or corpus profile and re-run.

## Starting points
- **New** — size, cost and scaffold a pipeline from a corpus profile and the settings you plan.
- **Existing** — also pass the config the live index was built with as `current_config`: both are sized on the same corpus and the plan adds "Change vs current index" (changed keys, whether a full re-index is needed and its one-off cost, deltas in chunks, monthly cost and context per query).

## When to use
- Before building a LangChain RAG pipeline: how many chunks, how many embedding tokens, what it costs to embed and keep fresh, whether `top_k` chunks fit the context.
- When a chunking, `top_k` or store choice changes and the cost or budget must be re-checked.
- NOT for: measuring retrieval quality or choosing between chunking strategies (`rag-pipeline-design`), serving capacity (`infra-gpu-sizing`), running evals (`llm-eval-harness`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| `corpus` — one row per source: doc count, average characters, update frequency, optional change fraction | yes | data owner; layout `assets/corpus-profile.example.csv` |
| `config` — chunk size and overlap (chars), embedding price per 1M tokens, `top_k`, reranker yes/no, vector store, context budget (tokens available for retrieved text) | yes | ML platform lead; layout `assets/rag-config.example.json` |
| optional config: embedding model and provider, `rerank_fetch_k`, chars per token (default 4), currency, price date | no | ML platform lead |
| `review` — flag for the optional LLM review | no | user |

The embedding price has no default: a missing price blocks the run. A missing model, price date or rerank candidate count becomes `[TO BE BASELINED — owner: <role>]`.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Fill the corpus profile and config from `assets/`. Use measured averages (from a sample) rather than guesses; record the price date.
3. Run the skill. `scripts/plan_rag.py` applies `references/sizing-method.md`: chunks per document from the sliding window, embedded characters including overlap, tokens as characters ÷ chars-per-token (an estimate), one-time and monthly re-embedding cost, per-query context vs budget.
4. Blocking (exit 1): a missing required key, overlap ≥ chunk size, `rerank_fetch_k` < `top_k`, `top_k` × chunk tokens over the context budget, an invalid corpus row. Fix and re-run.
5. Read the Warnings: zero overlap, in-memory store, FAISS deserialization, missing model or price date, documents shorter than one chunk.
6. `rag_pipeline.py` holds the config constants, one `SOURCES` entry per corpus source (locations from environment variables), `make_embeddings()` (one embeddings object for index and query), `make_vector_store()` for chroma, faiss, inmemory, pinecone or pgvector, `ingest()` and `retrieve()` with optional rerank. It was generated and syntax-checked, not executed.
7. Optional: pass `review=yes` for `rag-review.md` on `assets/rag-review-template.md`.
8. Run the self-check.

## Output
| File | Content | Checks |
|---|---|---|
| `rag-plan.json` | ok flag, config, method, per-source sizing and cost, totals, retrieval budget, warnings, scaffold status | json; `"ok": true` |
| `rag-plan.md` | Sizing, Cost, Retrieval budget, Warnings, Scaffold | sections; no unowned TBD; every number traces to `rag-plan.json` |
| `rag_pipeline.py` | LangChain ingestion + retrieval scaffold | syntax check with required functions; splitter wired to config |
| `rag-review.md` (optional) | Upstream conformance, Cost and budget risks, Next changes | eval case `agent-with-review` |

## Self-check
- [ ] Every price is a dated user input; nothing assumed
- [ ] Token counts are labelled estimates (characters ÷ chars-per-token), not tokenizer counts
- [ ] Monthly cost states whether it assumes a full re-embed or a change fraction
- [ ] `top_k` × chunk fits the context budget with headroom for the prompt and answer
- [ ] Index and query use the same embeddings object; the store persists beyond tests
- [ ] `rag_pipeline.py` is described as syntax-checked, not run

## References
- `references/sizing-method.md` — formulas, a hand-checked example, and limits
- `scripts/plan_rag.py` — calculator and generator (argparse; stdlib)
- `scripts/check_syntax.py` — compile/ast check used by the output check
- `assets/corpus-profile.example.csv`, `assets/rag-config.example.json` — input layouts
- `assets/rag-review-template.md` — template for the optional review
- Upstream: `vendor/langchain-rag/SKILL.md` (langchain-ai/langchain-skills, MIT, pinned in vendor/pins.json)

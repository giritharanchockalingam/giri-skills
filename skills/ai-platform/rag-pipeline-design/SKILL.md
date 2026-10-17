---
name: rag-pipeline-design
description: Use when the user has a knowledge, search, or question-answering use case over documents — "design our RAG pipeline", "which chunking/embedding should we use", "our RAG answers are wrong", "size the cost of a knowledge assistant". Produces the retrieval design (ingestion, chunking, embedding, hybrid retrieval, reranking), an evaluation set and metrics (recall@k, MRR, faithfulness, answer relevance), guardrails, and a cost model with labeled inputs; ships a retrieval-eval script. Not for agent orchestration (use agent-architecture) or model-quality evaluation beyond retrieval (use llm-eval-harness).
license: MIT
metadata:
  domain: ai-platform
  version: 0.1.0
  author: giri-skills
---

# RAG Pipeline Design

## When to use
- New knowledge assistant, document Q&A, policy/contract search, support knowledge base, code or ticket search.
- Diagnosing a RAG system that answers wrong, hallucinates, or costs too much.
- NOT for: fine-tuning decisions, agent control flow (`agent-architecture`), full answer-quality harness (`llm-eval-harness`; this skill covers retrieval metrics and hands off).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Corpus description: types, count, size, update rate, languages, access control | yes | user |
| Question types with 10+ real examples | yes | user; if absent, ask — synthetic questions are a last resort and labeled |
| Users, volume (queries/day), latency SLO | yes | user; mark `[TO BE BASELINED — owner: ___]` if unknown |
| Freshness requirement (how stale may an answer be) | yes | user |
| Constraints: residency, PII, allowed vendors, budget | no | user |

If the corpus or example questions are missing, ask once.

## Procedure
1. Read `../../../shared/quality-bar.md` and `../../../shared/stack-conventions.md`.
2. **Decide whether RAG is the right tool.** Small, static corpus that fits the context window → direct context, no retrieval. Structured data → SQL/API tool, not embeddings. Record the decision.
3. **Design ingestion and chunking** with `references/chunking-strategies.md`: parser per document type, chunk strategy per type, metadata schema (source, section, ACL, timestamp, version), dedup, update/delete path.
4. **Select embeddings and index** with `references/embedding-selection.md`: criteria table (domain fit, language, dimension/cost, latency, licensing, hosting), index type, ACL filtering strategy.
5. **Design retrieval** with `references/retrieval-and-reranking.md`: hybrid (BM25 + dense) by default, metadata filters, query rewriting, reranker, k values, context assembly, citation format.
6. **Build the eval set** (`assets/retrieval-eval-set.csv`): ≥ 50 queries with expected doc/chunk ids; run `scripts/eval_retrieval.py` for recall@k and MRR. Define answer-level metrics (faithfulness, answer relevance) with `references/eval-metrics.md`; hand off scoring to `llm-eval-harness`.
7. **Set guardrails** with `references/guardrails.md`: ACL enforcement at retrieval, "no answer" behavior, citation requirement, PII handling, injection in documents.
8. **Model cost** with `references/cost-model.md` and `assets/cost-model-inputs.csv`: ingestion, storage, query (embedding + retrieval + rerank + generation), re-indexing. All unit prices are user inputs; none are hardcoded.
9. **Write the design doc**: decision, architecture, chunking table, retrieval config, eval results table, guardrails, cost table, risks, next steps.
10. Run the self-check.

## Output
- `rag-design-<name>.md` plus filled `retrieval-eval-set.csv` and `cost-model-inputs.csv`.
- Eval scorecard from `scripts/eval_retrieval.py` (recall@1/5/10, MRR) in the doc.

## Self-check
- [ ] "Why RAG and not context/SQL" answered in one line
- [ ] Chunking strategy stated per document type with sizes and overlap as labeled assumptions
- [ ] ACL filtering happens before or during retrieval, never only in the prompt
- [ ] Eval set ≥ 50 real queries or labeled synthetic; recall@k and MRR reported with k stated
- [ ] Faithfulness and answer-relevance measurement defined with a gate threshold
- [ ] Cost model has no hardcoded prices; every unit price is a labeled input
- [ ] No vendor benchmark numbers quoted without a source

## References
- `references/chunking-strategies.md`
- `references/embedding-selection.md`
- `references/retrieval-and-reranking.md`
- `references/eval-metrics.md`
- `references/guardrails.md`
- `references/cost-model.md`
- `scripts/eval_retrieval.py` — `python3 -I scripts/eval_retrieval.py --csv assets/retrieval-eval-set.csv --k 1,5,10`

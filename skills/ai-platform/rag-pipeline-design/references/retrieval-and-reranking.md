# Retrieval, Hybrid Search, and Reranking

## Default pipeline
```
query → [rewrite/expand] → BM25 top-N  ┐
                          dense top-N  ┴→ fuse (RRF) → metadata/ACL filter → rerank top-M → assemble top-k with citations → generate
```
Start here; remove stages only when the eval set shows no loss.

## Stages
| Stage | What | Default (assumption) | When to change |
|---|---|---|---|
| Query rewriting | Normalize, expand acronyms, resolve pronouns from chat history, generate 1–3 paraphrases | On for chat; off for single-shot search | High latency budget pressure |
| Hypothetical answer (HyDE-style) | Embed a model-generated answer instead of the query | Off | Short, keyword-poor queries with low dense recall |
| Lexical (BM25) | Exact terms, ids, codes, names | On | Never off for enterprise corpora (ids and part numbers matter) |
| Dense | Semantic similarity | On | — |
| Fusion | Reciprocal Rank Fusion of the two lists | RRF, k=60 constant | Weighted fusion when one channel dominates on evals |
| Filters | ACL, doc_type, date, tenant | Pre-filter | — |
| Reranker | Cross-encoder scores query–chunk pairs | Top-30 → top-5 | Skip only if p95 latency fails and recall@5 without reranker meets target |
| Context assembly | Order by score or by document order; dedup; include title/section path; cap tokens | 4–8 chunks, ≤ 3–4k tokens | Long-context models allow more; evaluate "lost in the middle" |
| Citations | Each chunk gets `[n]` with source_uri + section; answer must cite | Mandatory | — |

## Choosing k
| Measure | Target |
|---|---|
| Recall@k (pre-rerank candidates) | ≥ 0.9 at N (e.g., N=30) so the reranker has the answer in its pool |
| Recall@k (post-rerank, assembled) | ≥ 0.8 at k (e.g., k=5), set by the eval set |
| Context tokens | Minimum that holds recall; more context raises cost and distraction |

## Query routing
| Query type | Route |
|---|---|
| Structured (counts, filters, "how many tickets…") | SQL/API tool, not retrieval |
| Entity lookup by id/code | Lexical only, filter by field |
| Conceptual / procedural | Hybrid + rerank |
| Multi-hop ("compare policy A and B") | Decompose into sub-queries; retrieve per sub-query; merge |
| Out of scope | Classifier → "not covered" response; log for corpus gaps |

## Conversation handling
- Condense the follow-up question with prior turns into a standalone query before retrieval.
- Do not retrieve for chit-chat or clarification turns.
- Keep retrieved context per turn, not accumulated across turns, unless the question references prior results.

## Failure diagnosis
| Symptom | Likely cause | Check |
|---|---|---|
| Right doc, wrong chunk | Chunking too small or no parent context | Parent-child; section path |
| Wrong doc entirely | Dense-only; ids/jargon not captured | Add BM25; check query rewriting |
| Correct chunk retrieved, answer wrong | Generation/faithfulness issue | Prompt, citations required, smaller context |
| Good offline, bad online | Query distribution drift; chat condensation | Log queries; add to eval set |
| Stale answers | Index update lag | Freshness SLO; incremental ingestion |

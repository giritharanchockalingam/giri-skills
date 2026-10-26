# RAG Evaluation Metrics

Two layers: retrieval (deterministic, cheap, run on every change) and answer quality (judged, costlier, run on release candidates and sampled in production).

## Retrieval metrics (computed by `scripts/eval_retrieval.py`)
| Metric | Definition | Use |
|---|---|---|
| Recall@k | Fraction of queries where at least one expected id is in the top-k (or fraction of expected ids found, when multiple) | Primary tuning metric; report at k = 1, 5, 10 and at the reranker pool size |
| MRR | Mean of 1/rank of the first relevant result (0 if none in list) | Sensitivity to ordering; matters when k is small |
| Precision@k | Relevant in top-k ÷ k | Context cleanliness; distraction risk |
| nDCG@k | Rank-weighted gain | When graded relevance labels exist |
| Coverage | Queries with ≥1 relevant result at any rank in the candidate pool | Corpus gap detection |

Eval set layout: `assets/retrieval-eval-set.csv` — `query_id, query, expected_doc_ids (pipe-separated), retrieved_doc_ids (pipe-separated, ranked), query_type, notes`.

Construction rules:
1. ≥ 50 queries; ≥ 10 per query type; drawn from real logs or SMEs. Synthetic queries are labeled `synthetic` and reported separately.
2. Expected ids are chunk ids when the chunk is the citation unit; doc ids when any chunk of the doc suffices. State which.
3. Include negatives: 10% out-of-scope queries where the expected answer is "not covered".
4. Refresh quarterly; add every production failure.

## Answer-quality metrics (scored via `llm-eval-harness`)
| Metric | Definition | Scoring method | Gate (assumption) |
|---|---|---|---|
| Faithfulness / groundedness | Every claim in the answer is supported by the retrieved context | Claim extraction → per-claim support check (judge model or NLI); or human rubric | ≥ 0.9 |
| Answer relevance | Answer addresses the question asked | Judge rubric 1–5; or embedding similarity question↔answer as a weak proxy | ≥ 4.0 mean |
| Context relevance / precision | Retrieved chunks are useful to the answer | Judge per chunk | Track; no hard gate |
| Correctness (when gold answers exist) | Matches reference answer | Exact/regex for facts; judge for prose | ≥ target per use case |
| Citation accuracy | Cited chunk actually supports the cited sentence | Judge or human sample | ≥ 0.9 |
| Abstention accuracy | "Not covered" returned for out-of-scope queries; not returned for in-scope | Deterministic from labels | ≥ 0.9 both ways |
| Latency p50/p95, cost per query | Operational | Measured | Per SLO |

## Rules
1. Retrieval metrics gate every index/chunking/embedding change in CI.
2. Answer metrics gate prompt/model changes; run on the full set pre-release, sampled (e.g., 2–5%) in production.
3. Report deltas against the previous baseline, not absolute numbers alone.
4. Judge-model scoring follows the pitfalls list in `llm-eval-harness/references/llm-as-judge.md`: separate judge from generator, calibrate against human labels, fix rubrics.
5. No metric target is quoted as a benchmark; targets are set from the use case's risk tier and recorded as assumptions.

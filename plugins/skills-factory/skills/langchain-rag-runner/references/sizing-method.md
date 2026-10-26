# Sizing method

How `scripts/plan_rag.py` computes chunks, tokens, cost and the retrieval budget. Splitter, embedding and store behaviour follow the upstream langchain-rag skill (langchain-ai/langchain-skills, pinned in vendor/pins.json).

## Symbols
| Symbol | Meaning | Source |
|---|---|---|
| L | average characters per document in a source | corpus profile |
| D | documents in the source | corpus profile |
| C | chunk size (characters) | config |
| O | chunk overlap (characters), O < C | config |
| S | stride = C − O | derived |
| r | characters per token (default 4) | config; an estimate, not a tokenizer |
| P | embedding price per 1M tokens | config; no default |
| u | updates per month (static 0, yearly 1/12, quarterly 1/3, monthly 1, weekly 52/12, daily 365/12, or a number) | corpus profile |
| f | change fraction re-embedded per update (default 1 = full re-embed) | corpus profile |

## Formulas
```
chunks per doc         n = 1                       if L <= C
                       n = 1 + ceil((L - C) / S)   otherwise
embedded chars / doc   E = L + (n - 1) * O          (each overlap is embedded twice)
chunks                 D * n
embedding tokens       T = ceil(D * E / r)
one-time cost          T / 1M * P
monthly re-embed       T * u * f tokens; cost T * u * f / 1M * P
first-year spend       one-time + 12 * monthly
per-query context      ceil(top_k * C / r) tokens   vs context_budget_tokens
```
The sliding-window count is the upper envelope of what a recursive splitter produces at the average length; real splitters break on separators, and length spread changes the total. Treat totals as planning estimates.

## Hand-checked example (fictional numbers)
C = 1000, O = 200, S = 800, r = 4, L = 3000, D = 1200:
n = 1 + ceil(2000 / 800) = 4 (windows start at 0, 800, 1600, 2400); E = 3000 + 3 × 200 = 3600; T = ceil(1200 × 3600 / 4) = 1,080,000 tokens. At P = 0.02 per 1M: one-time 0.0216; monthly updates (u = 1, f = 1): 0.0216 per month.

## Blocking errors
| Condition | Why |
|---|---|
| Required config key missing (incl. price) | Nothing is assumed |
| O >= C | The splitter cannot advance |
| `rerank_fetch_k` < `top_k` | The reranker cannot return `top_k` results |
| ceil(top_k × C / r) > context budget | Retrieved text cannot fit the prompt |
| Corpus row invalid (non-numeric, negative, unknown frequency, change fraction > 1) | Garbage in |

## Warnings
Zero overlap (boundary context lost); in-memory store (lost on restart); FAISS (only load self-created indexes: pickle-backed metadata); unknown store (no template); reranker without candidate count; no embedding model; zero price; no price date; documents shorter than one chunk.

## Not modelled
Vector-store hosting and storage, query-time embedding, reranker inference, generation tokens, index rebuild time. Add them in a TCO model (see `infra-gpu-sizing` for serving).

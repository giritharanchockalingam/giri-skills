# RAG Cost Model — inputs and formulas

No prices are hardcoded. Every unit price is an input the user supplies from current vendor pricing or internal cost allocation; label the date of the price. Record inputs in `assets/cost-model-inputs.csv`.

## Inputs
| Input | Symbol | Unit |
|---|---|---|
| Documents | D | count |
| Average tokens per document | T_doc | tokens |
| Chunks per document (after chunking) | C_doc | count |
| Embedding price | P_emb | $ per 1M tokens (API) or $/GPU-hr ÷ tokens/hr (self-host) |
| Re-index frequency | R | full re-indexes per year |
| Incremental update rate | U | % of corpus changed per month |
| Vector storage price | P_store | $ per GB-month |
| Embedding dimension, bytes per dim | dim, b | e.g., 1024, 4 (float32) or 2 (float16) |
| Queries per day | Q | count |
| Query tokens (embedding) | T_q | tokens |
| Rerank price | P_rr | $ per 1k query–doc pairs or per request |
| Rerank pool size | N | candidates per query |
| Generation input tokens per query | T_in | tokens (prompt + assembled context) |
| Generation output tokens per query | T_out | tokens |
| Generation price | P_in, P_out | $ per 1M tokens |
| Search/DB infrastructure | P_infra | $/month fixed |
| Engineering and ops | P_ops | $/month (labeled assumption) |

## Formulas
```
Ingestion tokens          I = D × T_doc  (plus chunk-context overhead ~10–20%, assumption)
Initial embedding cost    E0 = I / 1e6 × P_emb
Annual re-embedding       E_year = E0 × R + E0 × U × 12
Storage GB                S = D × C_doc × dim × b / 1e9  (+ index overhead, e.g., 1.5–2×, assumption)
Storage cost / month      = S × overhead × P_store
Query embedding / month   = Q × 30 × T_q / 1e6 × P_emb
Rerank / month            = Q × 30 × N / 1000 × P_rr        (if priced per pair)
Generation / month        = Q × 30 × (T_in / 1e6 × P_in + T_out / 1e6 × P_out)
Monthly run cost          = storage + query embedding + rerank + generation + P_infra + P_ops
Cost per query            = (monthly run cost − P_ops) / (Q × 30)
```

## Sensitivity to show
| Lever | Effect |
|---|---|
| Context tokens T_in | Usually the largest variable cost; halving assembled context halves generation input cost |
| Dimension / precision | Storage scales linearly; float16 halves it; check recall |
| Reranker | Adds per-query cost; often lets k drop, reducing T_in |
| Model tier for generation | Route simple queries to a cheaper model; measure answer quality per tier |
| Caching | Exact/near-duplicate query cache; measure hit rate before counting savings |

## Reporting
Present three scenarios (low / expected / high volume) with the input table and the formulas visible. Every price cell shows its source and date.

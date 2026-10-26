# Embedding Model and Index Selection

Pick by measured recall on your eval set, under your constraints. Public leaderboards rank on public benchmarks; your corpus is not on them.

## Selection factors
| Factor | Why it matters | How to assess |
|---|---|---|
| Domain fit | Legal, medical, code, and multilingual corpora favor models trained on similar text | recall@k on your eval set; compare 2–3 candidates |
| Language coverage | Monolingual models fail on mixed corpora | Per-language recall |
| Dimension | Storage and query cost scale with dimension; some models support truncation (Matryoshka-style) | Storage = chunks × dim × bytes; test recall at reduced dims |
| Max input length | Chunks longer than the limit are silently truncated | Chunk size ≤ model limit |
| Latency | Query embedding is on the critical path | p95 per query at target concurrency |
| Hosting | API (simplest), self-host (residency, cost at volume), managed (middle) | Residency, PII, throughput |
| Licensing | Open-weights license terms for commercial use | Legal review |
| Versioning | Re-embedding the corpus on model change is a full re-index cost | Pin version; plan re-index |
| Cost | Per-million-token price (API) or GPU-hour (self-host) | Enter in cost model as input |

## Index and store options
| Option | Fit | Notes |
|---|---|---|
| Postgres + pgvector | Default for the house stack (Supabase); corpora up to low millions of chunks; ACL via row-level security | HNSW index; filter-then-search for ACL; hybrid via tsvector |
| Dedicated vector DB (managed) | Tens of millions of chunks; multi-tenant at scale; advanced filtering | Another system to govern; data egress |
| Search engine (OpenSearch/Elasticsearch) with vectors | Strong BM25 + vectors in one engine; existing ops skills | Heavier to run |
| In-memory / file (FAISS, local) | Prototypes, evals, offline batch | No ACL; not for prod multi-user |

Rule: start with the store you already operate. Move only when a measured limit (latency, scale, filtering) is hit.

## ACL strategy
| Approach | Rule |
|---|---|
| Pre-filter | Apply `acl_groups ∩ user_groups` as a filter inside the vector query. Required when access control matters. |
| Post-filter | Retrieve k' > k then drop unauthorized — leaks existence; only acceptable with pre-filter as well |
| Separate indexes per tenant | Strongest isolation; operational overhead; use for strict residency/tenancy |

Never rely on the prompt to hide documents the user is not allowed to see.

## Decision record (fill in)
| Item | Choice | Evidence |
|---|---|---|
| Embedding model + version | | recall@5 on eval set vs 2 alternatives |
| Dimension | | storage and recall trade-off |
| Index/store | | existing ops, scale, ACL |
| Re-index plan on model change | | |

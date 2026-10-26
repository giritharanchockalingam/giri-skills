# Chunking Strategies

Chunking decides what the retriever can find. Choose per document type, not per corpus. All sizes below are starting assumptions; tune with the eval set and label them in the design doc.

## Strategies
| Strategy | How | Best for | Weakness |
|---|---|---|---|
| Fixed-size with overlap | N tokens, M overlap (e.g., 400/60) | Uniform prose, logs, transcripts | Cuts mid-thought; duplicates at boundaries |
| Recursive by separators | Split on headings → paragraphs → sentences until under size | Markdown, HTML, docs with structure | Needs clean structure |
| Structure-aware (section/heading) | One chunk per section; split large sections recursively | Policies, manuals, contracts, wikis | Section sizes vary; add parent context |
| Semantic | Split where embedding similarity between sentences drops | Long unstructured prose | Cost at ingestion; non-deterministic boundaries |
| Element-based (tables, code, lists) | Keep tables/code blocks whole; chunk text around them | Technical docs, specs, spreadsheets exported to text | Large tables exceed size; summarize + link |
| Parent-child (small-to-big) | Index small chunks (100–200 tokens) for recall; return the parent (section/page) for generation | Most enterprise Q&A | Two-level storage; parent size cap needed |
| Proposition / fact-level | LLM extracts atomic statements; index each | FAQ-style precise answers | Ingestion cost; provenance must link to source span |
| Page-level | One chunk per page | Scanned PDFs, slides | Pages mix topics |
| Row/record-level | One chunk per record with field labels | Catalogs, tickets, CRM notes | Many small chunks; use metadata filters |

## Rules
1. **Chunk = unit of citation.** If a user cannot verify the answer from the chunk's source span, the chunk is wrong.
2. **Carry context into every chunk:** document title, section path ("Policy > Travel > Per diem"), and date, either prepended to the text or in metadata used at assembly time.
3. **Never split a table row or code block mid-way.** Summarize oversized elements and store the raw element as a linked resource.
4. **Overlap 10–20%** for fixed/recursive strategies; 0 for structure-aware with parent-child.
5. **Dedup** near-identical chunks (hash of normalized text; optional embedding-similarity dedup above a threshold).
6. **Metadata schema (minimum):** `doc_id, chunk_id, source_uri, title, section_path, page?, created_at, updated_at, version, acl_groups[], doc_type, language, hash`.
7. **Updates and deletes:** re-chunk by document; delete stale chunk ids by `doc_id + version`; never leave orphans.
8. **Multi-language:** chunk per language block; store `language`; use a multilingual embedding or per-language indexes.

## Parser choices (decide per type)
| Type | Parser considerations |
|---|---|
| PDF (text) | Layout-aware extraction; preserve headings and reading order; tables to Markdown |
| PDF (scanned) | OCR with confidence; flag low-confidence pages; page-level chunks |
| DOCX/PPTX | Native structure (headings, slide titles, notes) |
| HTML | Strip nav/boilerplate; keep headings, lists, tables |
| Spreadsheets | Row-level with header labels; or table summaries |
| Code | Function/class-level; include file path and signature |
| Email/tickets | Record-level; strip signatures/quoted threads; thread id in metadata |

## Chunk-size selection heuristic
| Question type | Chunk size (tokens, assumption) | Retrieval unit |
|---|---|---|
| Fact lookup ("what is the per diem for X") | 150–300 | child chunk, return parent section |
| Procedure ("how do I file an expense") | 300–600 | section |
| Comparison / synthesis across docs | 300–500, k higher | section + reranker |
| Code / config | element | function/file |

Validate with recall@k on the eval set; change one variable at a time and record the result.

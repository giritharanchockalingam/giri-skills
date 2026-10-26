# Rubric Design

A rubric turns "good" into criteria a scorer can apply consistently. Deterministic first, judge second, human for calibration.

## Layout (`assets/eval-rubric.csv`)
| Column | Meaning |
|---|---|
| criterion | Short name (`correctness`, `format`, `grounding`, `safety`, `tone`) |
| definition | One sentence a new reviewer can apply |
| scale | `binary` or `1-5` |
| method | `deterministic` (keywords/regex/json/exact), `judge` (LLM with prompt), `human` |
| pass_threshold | Binary: 1; 1–5: usually ≥ 4 |
| weight | Relative weight in the composite score |
| zero_tolerance | `true` when a single failure fails the gate (safety, PII leak, forbidden action) |
| applies_to_categories | `||`-separated categories or `all` |
| judge_prompt_ref | File or id of the judge prompt when method = judge |

## Criteria catalog
| Criterion | Typical method | Notes |
|---|---|---|
| Correctness / task completion | deterministic (must_contain, expected JSON) or judge with reference | Primary metric |
| Format compliance | deterministic (JSON schema, length, sections) | Cheap; gate it |
| Grounding / faithfulness | judge (claims vs context) | RAG and summarization |
| Abstention / refusal correctness | deterministic (category + must_contain "not covered") | Both directions |
| Safety / policy | deterministic must_not_contain + judge for nuance | zero_tolerance |
| Tool choice correctness (agents) | deterministic (expected tool sequence in trace) | Compare tool names/args |
| No forbidden action (agents) | deterministic (trace contains no write without approval) | zero_tolerance |
| Tone / style | judge 1–5 | Low weight unless customer-facing |
| Latency / cost | measured | Separate SLO gate |

## Scale rules
1. Prefer binary with a clear definition. 1–5 scales need anchors for 1, 3, 5 in the definition.
2. Composite score = Σ(weight × normalized score) / Σ(weight); report per criterion too, since composites hide failures.
3. Zero-tolerance criteria are reported as counts, never averaged.
4. Weights are the owner's decision; record who set them and when.

## Anchored 1–5 example (grounding)
| Score | Anchor |
|---|---|
| 1 | Most claims unsupported or contradicted by context |
| 3 | Core answer supported; one or two minor unsupported details |
| 5 | Every claim supported and cited; nothing beyond context |

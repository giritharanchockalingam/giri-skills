# Audit method

How `scripts/audit_evals.py` audits and cleans an eval set. The concerns (leakage, coverage, independent and complete grading, fair case mix) come from the upstream eval-engineering skill (langchain-ai/langchain-skills, pinned in vendor/pins.json); the rules below are ours, applied to a flat dataset rather than a Harbor task.

## Columns
| Canonical | Accepted names | Required |
|---|---|---|
| id | id, case_id | no (assigned `row-<line>` with a low issue) |
| input | input, prompt, question | yes |
| expected | expected, reference, answer, ideal, expected_output | yes (column); per-row emptiness depends on the grader |
| category | category, or tags (`;`, `|`, `,` separated or a JSON list) | yes (one of them) |
| grader | grader, grader_type | no |
| split | split | no (enables leakage detection) |
| label | label | no (enables label distribution) |

## Normalisation
NFKC → lowercase → punctuation to spaces → collapse whitespace. Exact duplicate = same normalised input. Near-duplicate = token-set Jaccard ≥ threshold (default 0.9, a method parameter printed in every report). Above 4,000 kept rows, near-duplicate search is limited to pairs within a category (stated in the report).

## Rules
| Issue | Severity | Effect on `eval-clean.jsonl` |
|---|---|---|
| empty_input | high | dropped |
| empty_reference (grader blank, exact, contains, regex, numeric, json_match, code) | high | dropped |
| conflicting_reference (same input, different reference) | high | later row dropped; resolve with the domain owner |
| split_leakage (same input in two or more splits) | high | first occurrence kept; re-split |
| duplicate (same input, same reference) | medium | later row dropped |
| near_duplicate | medium | kept; review |
| missing_grader | medium | kept; treated as reference-based |
| missing_category | medium | kept as `uncategorised` |
| duplicate_id | medium | renamed `<id>-dup<n>` |
| unknown_grader | low | kept |
| missing_id | low | assigned `row-<line>` |

Reference-free graders: llm_judge, rubric, human, pairwise.

## Coverage and verdict
- Cases are counted per category on the cleaned set; a row with several tags counts once per tag.
- With targets: a category below `min_cases` (including a target category absent from the data) is BELOW; any BELOW → verdict FAIL, exit 1.
- Without targets: verdict NOT GATED; `min_cases` is `[TO BE BASELINED — owner: Eval owner]`.
- Balance: largest and smallest non-empty category and their ratio (reported, not gated).

## Recommendations
Derived only from findings: cases to add per BELOW category (the exact gap), near-duplicates to replace, graders to assign, targets to set, and dataset-wide fixes for leakage, conflicting and empty references.

## Limits
- Token Jaccard catches rewording with shared words, not paraphrase; semantic duplicates need an embedding pass.
- The audit cannot judge whether a reference is correct; that needs a domain owner.

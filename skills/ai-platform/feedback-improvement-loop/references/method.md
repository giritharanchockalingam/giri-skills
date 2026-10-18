# Feedback improvement loop — method

Deterministic: the same inputs always give the same backlog and cases. No model is called.

## 1. Normalise ratings to severity
| Rating | Severity | Counted as |
|---|---|---|
| 1 or thumbs down (`down`, `-1`) | 3 | issue |
| 2 | 2 | issue |
| 3 | 1 | issue |
| 4, 5 or thumbs up (`up`, `+1`) | 0 | positive (not in the backlog) |
| anything else / missing id or feature | — | rejected row (counted) |

## 2. Group issues
For each issue row, in this order, the first match wins:
1. A row tag (`tags`, `;`-separated) equals a bucket's `tag_aliases` entry.
2. A bucket keyword occurs in the lower-cased comment, starting at a word boundary (buckets tried in taxonomy order).
3. Otherwise `other`.

Buckets (`assets/taxonomy.json`): hallucination, wrong-format, too-slow, refusal, missing-info,
tone, other. Each carries the hypothesis, fix type (prompt | retrieval | guardrail | model | data |
UX), accountable owner role and expected behaviours used for eval cases. Groups are
(bucket, feature) pairs so the fix lands on one feature.

Eval failures (`case_id, feature, failure_reason`) are bucketed the same way on `failure_reason`
and linked to the same (bucket, feature) group; a group may exist with eval failures only.

## 3. Rank
`score = frequency × mean severity = sum of severities`. Ties: more eval failures first, then
taxonomy order, then feature name.

## 4. Backlog and new eval cases
Each group becomes one backlog row with owner `[TO BE BASELINED — owner: <role>]` until a person
is named. For the `--cases-per-issue` most severe feedback rows of each group, one new eval case:

```json
{"id": "fil-<bucket>-<feature>-<feedback id>",
 "prompt": "Replay the user input recorded in trace <trace_id> (feature <feature>).",
 "expected": ["<bucket expected behaviours>", "Does not repeat the reported failure: \"<comment>\""],
 "provenance": {"feedback_id": "...", "trace_id": "...", "bucket": "...", "backlog_rank": 1}}
```
The shape (id, prompt, expected) matches this repo's `evals/evals.json` cases. Without a
trace_id the prompt is `[TO BE BASELINED — owner: Eval lead]`: the original input must be
recovered, never reconstructed from the complaint.

## 5. Minimum sample
`--min-rows` is the owner's minimum number of valid feedback rows. Below it the run writes the
outputs marked INSUFFICIENT DATA and exits 1, so a thin sample never drives prioritisation silently.

## Related public practice (by name)
- NIST AI RMF 1.0, *Measure* and *Manage* functions — feedback and continual improvement.
- ISO/IEC 42001 — continual improvement of an AI management system.

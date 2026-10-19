# Method

## Timings (minutes, one decimal)
| Measure | From | To | Notes |
|---|---|---|---|
| Time to detect | incident `started_at` | first `detected` event | |
| Time to acknowledge | first `detected` | first `acknowledged` | |
| Time to mitigate | `started_at` | first `mitigated` | user impact contained |
| Time to resolve | `started_at` | first `resolved` | no `resolved` event = incident OPEN; never inferred |
| Impact duration | `started_at` | first `mitigated` (else first `resolved`) | basis written to `timings.json` |

Rules:
- Timestamps must be ISO 8601 with a timezone. `Z` is accepted.
- A milestone that is absent gives `null` for every measure that needs it, plus a flag. Nothing is estimated.
- Milestones must run `started_at ≤ detected ≤ acknowledged ≤ mitigated ≤ resolved`. Each violation is flagged; a negative interval is reported as `null`.
- Rows listed out of time order in the CSV are flagged and shown sorted. A duplicate milestone is flagged; the first one counts.
- `change` and `note` events may precede `started_at` (a change often causes the incident).

## Factors and coverage
- Factors get ids F1..Fn in row order. `category` must match an id or name in `assets/factor-taxonomy.csv`, or the run stops (exit 2).
- Actions link to factors by id or exact factor text (`;` for several). Coverage = each factor has ≥ 1 linked action.
- Missing owner or due date → `[TO BE BASELINED — owner: Incident commander]`; status becomes `blocked: no owner` / `blocked: no due date`. Otherwise status is the input `status` (open | in-progress | done) or `open`.

## Strict gate (`--strict`)
Exit 1 when any factor has no action, any action has no owner, or no factors were supplied (coverage cannot be shown). All outputs are still written.

## Regression eval cases (`eval-cases.csv`)
- Columns are exactly the `llm-eval-harness` golden-set columns (`id, category, difficulty, input, expected, must_contain, must_not_contain, expected_json_valid, weight, source, notes`), so the file feeds `build_golden.py` unchanged.
- An input is taken only from an `input:"..."` marker in timeline descriptions or factor text/evidence. An `output:"..."` marker is copied into `notes` as the observed bad output.
- An eval-relevant factor (taxonomy `eval_relevant = yes`) without a marker yields a row whose input is `[TO BE BASELINED — owner: Eval lead]`.
- Scoring columns are never invented: `must_contain` / `must_not_contain` stay blank with a TBD note for the Eval lead. `difficulty` is `adversarial` for prompt/guardrail-gap factors, else `medium`; `weight` is 1.

## Blameless language check
Case-insensitive regex scan of title, customer impact, went-well, timeline descriptions and actor roles, factors, evidence and actions against `assets/blame-phrases.csv`. Each hit lists where, the phrase, why it reads as blame and a rewrite hint. It is a word-list scan: it cannot detect personal names or tone, and it does not change the text.

## Limits
- Timings are only as good as the timeline timestamps.
- The skill does not decide root cause; it records the factors the review supplied.
- Not a legal, regulatory or HR determination.

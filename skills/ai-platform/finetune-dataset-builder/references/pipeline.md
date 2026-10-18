# Pipeline rules

## 1. Validate
A record is rejected (and counted by reason) when:
- the JSON line does not parse, is not an object, or has neither `messages` nor `prompt`/`completion`;
- a role is not `system`, `user` or `assistant`, or content is not text;
- there is no user turn, or the last turn is not `assistant`;
- any turn is empty after trimming ("empty prompt or completion");
- `max_chars` is set and the total characters of all turns exceed it.

## 2. Normalise whitespace
CRLF/CR → LF; trailing whitespace per line removed; runs of spaces/tabs → one space; 3+ newlines → one blank line; ends trimmed. Case and punctuation are **not** changed in the output.

## 3. De-duplicate
1. **Exact**: identical raw record (all roles and contents) → later copies removed.
2. **Normalised**: same roles and same contents after casefolding and collapsing all whitespace → later copies removed.
First occurrence wins, so input order matters; sort the source if you need a different winner.

## 4. Split (grouped, seeded)
- Group key = normalised prompt (all non-assistant turns joined).
- Targets: val = round(n × val_ratio), test = round(n × test_ratio), train = n − val − test.
- Group keys are sorted, shuffled with `random.Random(seed)`, and each group goes to the first split (train → val → test) with room; a group that fits nowhere goes to the split furthest below target.
- Same prompt with different completions stays in one split → leakage is 0 by construction.

## 5. Leakage
Count of normalised prompts present in more than one split (pairwise sum). Must be 0; otherwise the run fails (exit 1).

## 6. Length stats (estimate)
Tokens ≈ ceil(total characters ÷ 4) per example. Per split: examples, min, mean (1 dp), nearest-rank P50 and P95, max, total. This is a planning heuristic; real tokenizers differ by language and content (code and non-Latin scripts usually use more tokens per character).

## Defaults
| Parameter | Default | Why it is safe to default |
|---|---|---|
| split | 0.8, 0.1, 0.1 | Conventional starting ratio; changes no example content |
| seed | 42 | Any fixed integer gives reproducibility |
| min_rows | 10 | Floor below which a split is meaningless; raise it for real training |
Defaults are written into the data card with "(default)".

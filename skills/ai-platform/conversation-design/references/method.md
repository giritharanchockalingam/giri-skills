# Method: routing, quality and coverage

All steps are deterministic and stdlib-only (`scripts/conversation_design.py`). Same inputs give byte-identical outputs.

## Tokenising
Lower-case; tokens are `[a-z0-9]+`; tokens shorter than 2 characters and a fixed stopword list (articles, pronouns, auxiliaries, greetings, "please") are dropped; a trailing `s` is removed from tokens longer than 3 characters that do not end in `ss` (light plural folding: `bills` → `bill`). No stemming beyond that, no synonyms.

## Routing (TF-IDF cosine)
- One document per intent: its description plus all examples.
- IDF over the intent documents, smoothed: `idf(t) = ln((1 + N) / (1 + df(t))) + 1`.
- Vectors are raw term counts × IDF, L2-normalised. Utterance terms not in any intent document are ignored.
- Score = cosine(utterance, intent). The best intent wins; ties break by intent name.
- **Confidence threshold 0.25**: a best score below 0.25 routes to `fallback` (uncovered). The value is the skill's default, not a standard; tune it on your own labelled sample. The threshold is printed in every report.

## Accuracy and per-intent quality (labelled rows only)
- `correct` = predicted intent equals `expected_intent` (`fallback` is a valid expected value for out-of-scope messages).
- Accuracy = correct / labelled. Precision(intent) = correct / routed-to-intent. Recall(intent) = correct / labelled-as-intent. A zero denominator prints `n/a`.
- Confusion pairs: (expected, predicted) counts for wrong rows.

## Confusable intents
Cosine between two intents' **example sets** (examples only, same IDF) at or above **0.40** flags the pair. Shared vocabulary in examples is the main cause of lexical mis-routing; the fix is sharper examples or a merge.

## Coverage and gaps
- Coverage = utterances routed to an intent / all utterances.
- Gaps listed: recall or precision below 1.000, intents with fewer than **5 examples** (skill design guideline), intents no utterance reached, confusable pairs, a `handoff` response type without `handoff=yes`, no hand-off intent at all, uncovered utterances, missing persona keys.

## Fallback and hand-off pattern
The spec states the pattern the flowchart draws: below threshold → rephrase prompt → re-route; a second miss → the persona's `escalation_channel`. `handoff=yes` intents go straight to that channel.

## Limits
- Lexical only: paraphrases with no shared words score 0. A production NLU or embedding router will score differently; use this as a design-time check, not a production benchmark.
- Results describe the supplied sample, not all future traffic. Sample size is printed; small samples swing accuracy by several points per utterance.
- Utterances are user text. Outputs echo at most the first 80 characters (`--leak-check` enforces it). Strip personal data from samples before running.

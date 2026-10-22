---
name: conversation-design
description: Use when the user is designing or checking the conversation layer of an AI assistant or chatbot — "design the intents for our assistant", "how well do our intents cover what users actually say", "which intents get confused", "where is the fallback and human hand-off", "check our utterances against the intent list". Produces routing.csv (each utterance's best intent and score), intent-quality.csv (examples, precision, recall, confusable intents) and conversation-spec.md (Summary, Persona, Intents, Fallback and hand-off with a mermaid flowchart, Coverage, Gaps, Method) from an intent catalog and real user utterances, using a deterministic TF-IDF router. Exit 1 when labelled accuracy is below the supplied min_accuracy. Not for prompt wording (use prompt-spec), LLM answer quality (use llm-eval-harness) or agent topology (use agent-architecture).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: requirements
  version: 0.2.0
  author: giri-skills
  agent:
    modes:
      new:      {case: agent-mode-new, bring: "draft intents and sample messages from people you will serve"}
      existing: {case: agent-happy-path, bring: "your assistant's intent catalog and labelled real user messages"}
    inputs:
      - {name: intents, type: csv, required: true, from: "intent catalog intent,description,examples(pipe-separated),response_type answer|action|handoff|clarify,handoff yes/no,owner (layout: assets/intents-template.csv)"}
      - {name: utterances, type: csv, required: true, from: "real or sampled user messages utterance[,expected_intent] (layout: assets/utterances-template.csv); echoed to 80 characters at most"}
      - {name: persona, type: csv, required: false, from: "kv-csv key,value,source,notes: name, tone, reading_level, escalation_channel, disallowed_topics (layout: assets/persona-template.csv); missing keys are TBD for the Conversation designer"}
      - {name: min_accuracy, type: string, required: false, from: "gate 0-1 on labelled routing accuracy; below it the run exits 1"}
    run:
      - {step: design, kind: script, cmd: "python3 -I scripts/conversation_design.py --intents {intents} --utterances {utterances} [--persona {persona}] [--min-accuracy {min_accuracy}] --out-dir {out}"}
    outputs:
      - {path: "{out}/routing.csv", checks: [exists, csv:[utterance,predicted_intent,score,expected_intent,correct], "csv_rows:score~^[01]\\.\\d{3}$", csv_rows:predicted_intent!empty, cmd:"python3 -I scripts/conversation_design.py --verify {path} --intents {intents} --utterances {utterances}", cmd:"python3 -I scripts/conversation_design.py --leak-check {path} --utterances {utterances}"]}
      - {path: "{out}/intent-quality.csv", checks: [exists, csv:[intent,examples,precision,recall,confusable_with], "csv_rows:examples~^\\d+$", "csv_rows:recall~^(n/a|[01]\\.\\d{3})$"]}
      - {path: "{out}/conversation-spec.md", checks: [exists, sections:["Summary","Persona","Intents","Fallback and hand-off","Coverage","Gaps","Method"], mermaid_parses, no_unowned_tbd, cmd:"python3 -I scripts/conversation_design.py --leak-check {path} --utterances {utterances}"]}
---

# Conversation Design (intents, fallback, hand-off, coverage)

## In a conversation: route and report now
The reply **is the coverage report** (or one ask), never only a command. About 1,000 tokens, tables over prose. Line 1: `Run: python3 -I scripts/conversation_design.py --intents <intents.csv> --utterances <utterances.csv> [--persona <persona.csv>] [--min-accuracy <x>] --out-dir out` → `routing.csv`, `intent-quality.csv`, `conversation-spec.md` (use the case's flags). Line 2: the headline — `Coverage a/b · Accuracy c/d = 0.xxx (or "not measured — no labels") · Gate: met (exit 0) | FAILED (exit 1) | none (exit 0)`.

**Never**
- Never pick "sensible" persona values. Each of `name, tone, reading_level, escalation_channel, disallowed_topics` absent from the persona file is `[TO BE BASELINED — owner: Conversation designer]` — list each missing key by name (e.g. reading_level too), and say "not chosen: the Conversation designer's decision".
- Never invent utterances or intents: no utterance file → ask once for the utterance sample (`utterance[,expected_intent]`, `assets/utterances-template.csv`); the run **stops (exit 2)**. Same for a missing intent catalog.
- Never echo more than the first 80 characters of a user message (end with "…").
- Never state accuracy without counting labelled rows from the file.

**Procedure — row by row from the supplied CSVs** (`references/method.md`)
1. Tokenise: lower-case, `[a-z0-9]+`, drop tokens < 2 chars and stopwords (a an the and or but if of to in on at for from by with about as is are was were be been am do does did i me my we our you your it its this that these those there here can could would should will just so please hi hello hey), drop a trailing `s` on tokens > 3 chars not ending `ss`.
2. One document per intent = description + all examples; idf(t) = ln((1+N)/(1+df)) + 1 over the N intent documents; vectors = count × idf, L2-normalised; utterance terms in no intent document are ignored. Score = cosine; best intent wins (tie → intent name). **Best score < 0.25 → `fallback`** (uncovered). Long messages sharing one or two common terms usually fall below 0.25.
3. Coverage = utterances routed to an intent ÷ all utterances (blank-label rows count here).
4. Labelled = rows with a non-blank `expected_intent` (`fallback` is a label). Accuracy = correct ÷ labelled, 3 decimals. Precision = correct ÷ routed-to-intent; recall = correct ÷ labelled-as-intent; zero denominator → `n/a`.
5. Confusable: cosine of two intents' **example sets** ≥ **0.40** (shared example words such as "pay … bill" across two intents).
6. Gate: `--min-accuracy x` and accuracy < x (or no labels) → "**run exits 1; all outputs still written**" (e.g. "0.870 is below 0.900"); accuracy ≥ x → "gate met (exit 0)"; no min_accuracy → "no gate (exit 0)". Unknown label, bad response_type, handoff not yes/no, duplicate intent, an intent named `fallback`, or a missing required file → **stops (exit 2)** with the line.

**Reply layout after the two lines**
1. Working table, every utterance: `| # | utterance (≤80 chars) | predicted | score≈ | expected | ✓ |`, then the counts it gives.
2. Per-intent `| intent | examples | precision | recall | confusable_with | owner |`.
3. **Gaps** (each with the intent's owner): uncovered messages, recall/precision < 1.000, intents with < 5 examples, confusable pairs, missing persona keys.
4. **Fallback and hand-off**: below 0.25 → rephrase prompt → re-route; second miss → the persona's `escalation_channel` (or its TBD); `handoff=yes` intents go straight there. Short mermaid `flowchart`.
5. **Method** line: thresholds 0.25 route / 0.40 confusable; the router is **lexical (TF-IDF) and sample-based**, not a production NLU benchmark; hand-computed scores are approximate — `routing.csv` from the run is authoritative (`--verify` re-derives it).
No files in the conversation: give line 1, describe each metric above with its threshold, and ask once for the intent catalog and utterance sample.

## Starting points
- **New:** first-draft intents and unlabelled sample messages give a coverage figure, the messages nothing catches, thin and confusable intents, and the persona keys still to decide.
- **Existing:** your live intent catalog, persona and labelled real messages give per-intent precision and recall, misroutes and an accuracy gate for edits to the catalog.

## When to use
- ADLC requirements stage: before building an assistant, to agree the intent catalog, response types, fallback and the human hand-off path.
- "How much of what users actually say do our intents cover?" — route a sample of real messages and read coverage and gaps.
- Regression check after editing intents: run with labelled utterances and a `min_accuracy` gate.
- NOT for: prompt wording or system prompts (`prompt-spec`), grading LLM answers (`llm-eval-harness`), single- vs multi-agent design (`agent-architecture`), production NLU benchmarking (this router is lexical).

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `intents` — `intent,description,examples,response_type,handoff,owner` | yes | Conversation designer (copy `assets/intents-template.csv`) | run stops (exit 2), asks once |
| `utterances` — `utterance[,expected_intent]` | yes | chat logs, search logs, call-centre notes, sampled and de-identified | run stops (exit 2), asks once |
| `persona` — kv-csv `name, tone, reading_level, escalation_channel, disallowed_topics` | no | Conversation designer / brand voice guide | each missing key is `[TO BE BASELINED — owner: Conversation designer]` |
| `min_accuracy` — 0–1 | no | product owner | no gate; accuracy reported only |

`expected_intent` may be an intent name, `fallback` (out of scope on purpose) or blank (unlabelled; counts toward coverage only). An unknown label, a bad `response_type`, a `handoff` other than yes/no, a duplicate intent or an intent named `fallback` stops the run (exit 2) with the line number.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Strip personal data from the utterance sample. Outputs echo at most 80 characters of each utterance, but the run reads all of it.
3. Run the agent. `scripts/conversation_design.py` routes each utterance by TF-IDF cosine (`references/method.md`); below 0.25 it goes to `fallback`.
4. With labels it computes accuracy, per-intent precision/recall and confusion pairs; it flags intent pairs whose example sets reach cosine 0.40.
5. With `min_accuracy`, accuracy below it (or no labels to measure it) exits 1.
6. Work the Gaps list with each intent's owner: add missed phrasings, split or merge confusable intents, confirm out-of-scope messages.
7. Run the self-check.

## Output
- `routing.csv` — `utterance` (≤ 80 chars), `predicted_intent`, `score`, `expected_intent`, `correct`, `nearest_intent`.
- `intent-quality.csv` — `intent, examples, precision, recall, confusable_with, response_type, handoff, routed, labelled, owner`.
- `conversation-spec.md` — **Summary**, **Persona**, **Intents**, **Fallback and hand-off** (mermaid flowchart), **Coverage** (uncovered utterances, confusion pairs), **Gaps** (each with an owner), **Method**.

## Self-check
- [ ] `routing.csv` re-derives exactly (`--verify`) and no output echoes more than 80 characters of an utterance (`--leak-check`)
- [ ] Every gap names an owner; missing persona keys are TBD for the Conversation designer
- [ ] The flowchart shows fallback and a path to a person
- [ ] Threshold values (0.25 route, 0.40 confusable) are stated in the report
- [ ] Limits stated: lexical router, sample-based, not a production NLU benchmark

## References
- `references/method.md` — tokenising, TF-IDF formula, thresholds, metrics, limits
- `assets/intents-template.csv`, `assets/utterances-template.csv`, `assets/persona-template.csv` — input layouts
- `scripts/conversation_design.py` — router, metrics, spec writer, `--verify` and `--leak-check` (argparse; stdlib)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/conversation-design --input <name>=<value> … --out <dir>` (see `--explain ai-platform/conversation-design`). Report the `run.json` results; do not hand-write the deliverables the script produces (`routing.csv`, `intent-quality.csv`, `conversation-spec.md`). Accuracy below a supplied `min_accuracy` fails the run (exit 1) on purpose; the outputs are still written so the misses are visible.

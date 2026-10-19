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

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/conversation-design --input <name>=<value> … --out <dir>` (see `--explain ai-platform/conversation-design`). Report the `run.json` results; do not hand-write the deliverables the script produces (`routing.csv`, `intent-quality.csv`, `conversation-spec.md`). Accuracy below a supplied `min_accuracy` fails the run (exit 1) on purpose; the outputs are still written so the misses are visible.

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

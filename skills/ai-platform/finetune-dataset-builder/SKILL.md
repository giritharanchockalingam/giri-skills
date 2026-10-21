---
name: finetune-dataset-builder
description: Use when the user has raw prompt/response examples and needs a training-ready fine-tune dataset — "build a fine-tune set from these examples", "clean and split my SFT data", "make train/val/test JSONL in chat format", "dedupe my training examples", "check for train/test leakage". Produces train.jsonl, val.jsonl and test.jsonl in chat-messages format after validation, whitespace normalisation, exact and normalised de-duplication and a seeded, prompt-grouped split with zero cross-split leakage, plus a data card (source checksum, cleaning counts, split sizes, estimated token-length stats, known limits). Not for PII scanning (pii-data-inventory), data-quality gating of tabular sources (data-readiness-assessment), running the fine-tune, or generating synthetic examples.
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: build
  version: 0.2.0
  author: giri-skills
  agent:
    modes:
      new:      {case: agent-happy-path, bring: "a spreadsheet of example questions and good answers"}
      existing: {case: agent-mode-existing, bring: "your current training set plus newly collected examples"}
    inputs:
      - {name: examples, type: file, required: true, from: "raw examples: .csv with prompt,completion[,system] or .jsonl with messages or prompt+completion (layout: assets/examples-template.csv)"}
      - {name: split, type: string, required: false, from: "train,val,test ratios summing to 1; default 0.8,0.1,0.1 (stated as default in the data card)"}
      - {name: seed, type: string, required: false, from: "integer shuffle seed; default 42 (stated as default in the data card)"}
      - {name: min_rows, type: string, required: false, from: "minimum usable examples; default 10; fewer fails the run (exit 1)"}
      - {name: max_chars, type: string, required: false, from: "reject examples longer than this many characters; default none"}
      - {name: existing, type: dir, required: false, from: "folder with the current train.jsonl (and val.jsonl, test.jsonl); records keep their split, leakage is repaired, new examples are added around them"}
    run:
      - {step: build, kind: script, cmd: "python3 -I scripts/build_dataset.py --examples {examples} --out-dir {out} [--split {split}] [--seed {seed}] [--min-rows {min_rows}] [--max-chars {max_chars}] [--existing-dir {existing}]"}
    outputs:
      - {path: "{out}/train.jsonl", checks: [exists, cmd:"python3 -I scripts/build_dataset.py --validate-jsonl {path}"]}
      - {path: "{out}/val.jsonl", checks: [cmd:"python3 -I scripts/build_dataset.py --validate-jsonl {path}"]}
      - {path: "{out}/test.jsonl", checks: [cmd:"python3 -I scripts/build_dataset.py --validate-jsonl {path}"]}
      - {path: "{out}/dataset-stats.json", checks: [exists, json, contains:"\"leakage_prompts_across_splits\": 0"]}
      - {path: "{out}/data-card.md", checks: [exists, sections:["Source","Cleaning","Splits","Length stats","Known limits"], no_unowned_tbd, numbers_trace_to:"{out}/dataset-stats.json", contains:"**estimate**"]}
---

# Fine-tune Dataset Builder

## In a conversation: build the dataset now
- **The request says the examples are here or attached but their rows are not in the conversation**: give the build plan and run report **in this reply**, in this order. (1) The run: `python3 -I scripts/build_dataset.py --examples <file> --out-dir <dir>` — validate, normalise whitespace, remove exact then normalised duplicates, prompt-grouped seeded split (`references/pipeline.md`). (2) A run-report table with rows: usable examples, rejected by reason (unparseable, no assistant turn, empty prompt or completion, over `max_chars`), exact duplicates removed, normalised duplicates removed, train / val / test sizes, `leakage_prompts_across_splits` (must be 0, or the run fails) — each count `[TO BE BASELINED — owner: ML engineer]` from `dataset-stats.json`; never a made-up count. (3) Parameters, each labelled: split 0.8/0.1/0.1 (default), seed 42 (default), min_rows 10 (default), max_chars none (default); a value the user states is labelled (supplied). (4) The output shape: one `{"messages":[{"role":"user",…},{"role":"assistant",…}]}` per line (system turn kept when given) in `train.jsonl`, `val.jsonl`, `test.jsonl`. (5) Token lengths are an **estimate** (characters ÷ 4); check against the target model's context window with its real tokenizer. (6) Before training: run `pii-data-inventory` on the examples and confirm owner, licence and consent — `[TO BE BASELINED — owner: Data owner]` until confirmed. (7) The data card sections: Source, Cleaning, Splits, Length stats, Known limits.
- **The rows are pasted in the conversation**: apply the same rules to them in this reply — list rejected rows with the reason, removed duplicates, and the cleaned records as chat-messages JSONL; give split targets (val = round(n × 0.1), test = round(n × 0.1), train = the rest) and say the seeded assignment comes from the script run, so it is reproducible.
- **No examples at all**: ask once for the file (CSV `prompt,completion[,system]` or JSONL with `messages` or `prompt`/`completion`; layout `assets/examples-template.csv`) and any non-default split, seed or length cap. Do not write example pairs yourself.
- **Fewer than `min_rows` usable examples**: say the run stops (exit 1) by design; report the usable count and the rejections by reason; do not pad, duplicate or invent rows.
- **Asked to generate synthetic examples, skip the leakage check or let one prompt sit in two splits**: decline in one line (synthetic data is out of scope; leakage inflates eval scores), and offer the defensible path: more real examples from the use-case owner, or a lower `min_rows` stated in the data card.

## Starting points
- **New:** raw examples become cleaned, de-duplicated, leak-free train/val/test files with a data card.
- **Existing:** add the folder with your current `train/val/test.jsonl` (`existing`); its records are audited and keep their split, new examples already in it are dropped, and only genuinely new prompts are placed, so earlier eval results stay comparable.

## When to use
- ADLC build stage: turning curated examples (support transcripts, expert answers, labelled outputs) into SFT-ready chat JSONL.
- Re-building after examples are added or corrected — same seed gives the same split for unchanged prompts.
- Auditing an existing set for duplicates and train/test leakage.
- NOT for: PII discovery (`pii-data-inventory` first), tabular data-quality gating (`data-readiness-assessment`), launching or tuning a training job, synthetic data generation, preference (DPO) pairs.

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `examples` — .csv or .jsonl | yes | use-case owner / SMEs | run stops (exit 2), asks once |
| `split` — `train,val,test` | no | ML engineer | 0.8,0.1,0.1, stated as **default** in the data card |
| `seed` — integer | no | ML engineer | 42, stated as **default** |
| `min_rows` — integer | no | ML engineer | 10, stated as **default** |
| `max_chars` — integer | no | ML engineer (from the target model's context limit) | no length cap |

Accepted shapes: CSV `prompt,completion[,system]`; JSONL `{"messages":[…]}` ending in an assistant turn, or `{"prompt":…,"completion":…}`. Other columns/keys are ignored.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Confirm the examples are cleared for training (owner, licence, consent) and have been through `pii-data-inventory`; the card records this as `[TO BE BASELINED — owner: Data owner]` until confirmed.
3. Run the agent. `scripts/build_dataset.py` validates, normalises whitespace, removes exact then normalised duplicates, groups by normalised prompt, shuffles groups with the seed and fills train → val → test (`references/pipeline.md`).
4. Check `leakage_prompts_across_splits` is 0 and the split sizes are what you expect; a small val/test split is reported, not padded.
5. Check the estimated token lengths against the target model's context window with its real tokenizer before training.
6. Run the self-check.

## Output
- `train.jsonl`, `val.jsonl`, `test.jsonl` — one `{"messages":[{"role":"user",…},{"role":"assistant",…}]}` per line (system turn kept when supplied); each passes `--validate-jsonl`.
- `dataset-stats.json` — source checksum, parameters (with default flags), cleaning counts, split sizes, leakage, length stats.
- `data-card.md` — **Source**, **Cleaning**, **Splits**, **Length stats**, **Known limits**; every number traces to `dataset-stats.json`.

## Self-check
- [ ] Defaults used are labelled "(default)" in the data card; nothing else is assumed
- [ ] Leakage across splits is 0; prompts with several completions sit in one split
- [ ] Token counts are labelled as an estimate (chars ÷ 4)
- [ ] Rejected rows are counted by reason, not silently dropped
- [ ] Source owner/licence/consent is confirmed or left TBD with the Data owner

## References
- `references/pipeline.md` — validation, normalisation, de-duplication, grouped split, leakage and length rules
- `references/dataset-card-notes.md` — why each card section exists; links to public documentation practices
- `assets/examples-template.csv` — input layout
- `scripts/build_dataset.py` — builder and JSONL validator (argparse; stdlib)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/finetune-dataset-builder --input <name>=<value> … --out <dir>` (see `--explain ai-platform/finetune-dataset-builder`). Report the `run.json` results; do not hand-write the deliverables the script produces (`train.jsonl`, `val.jsonl`, `test.jsonl`, `dataset-stats.json`, `data-card.md`). Fewer usable examples than `min_rows` fails the run (exit 1) on purpose.

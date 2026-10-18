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
    inputs:
      - {name: examples, type: file, required: true, from: "raw examples: .csv with prompt,completion[,system] or .jsonl with messages or prompt+completion (layout: assets/examples-template.csv)"}
      - {name: split, type: string, required: false, from: "train,val,test ratios summing to 1; default 0.8,0.1,0.1 (stated as default in the data card)"}
      - {name: seed, type: string, required: false, from: "integer shuffle seed; default 42 (stated as default in the data card)"}
      - {name: min_rows, type: string, required: false, from: "minimum usable examples; default 10; fewer fails the run (exit 1)"}
      - {name: max_chars, type: string, required: false, from: "reject examples longer than this many characters; default none"}
    run:
      - {step: build, kind: script, cmd: "python3 -I scripts/build_dataset.py --examples {examples} --out-dir {out} [--split {split}] [--seed {seed}] [--min-rows {min_rows}] [--max-chars {max_chars}]"}
    outputs:
      - {path: "{out}/train.jsonl", checks: [exists, cmd:"python3 -I scripts/build_dataset.py --validate-jsonl {path}"]}
      - {path: "{out}/val.jsonl", checks: [cmd:"python3 -I scripts/build_dataset.py --validate-jsonl {path}"]}
      - {path: "{out}/test.jsonl", checks: [cmd:"python3 -I scripts/build_dataset.py --validate-jsonl {path}"]}
      - {path: "{out}/dataset-stats.json", checks: [exists, json, contains:"\"leakage_prompts_across_splits\": 0"]}
      - {path: "{out}/data-card.md", checks: [exists, sections:["Source","Cleaning","Splits","Length stats","Known limits"], no_unowned_tbd, numbers_trace_to:"{out}/dataset-stats.json", contains:"**estimate**"]}
---

# Fine-tune Dataset Builder

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/finetune-dataset-builder --input <name>=<value> … --out <dir>` (see `--explain ai-platform/finetune-dataset-builder`). Report the `run.json` results; do not hand-write the deliverables the script produces (`train.jsonl`, `val.jsonl`, `test.jsonl`, `dataset-stats.json`, `data-card.md`). Fewer usable examples than `min_rows` fails the run (exit 1) on purpose.

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

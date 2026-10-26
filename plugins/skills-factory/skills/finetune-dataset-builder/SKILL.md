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
The reply **is the run report** (or its skeleton), never only a request for files. It corresponds to `python3 -I scripts/build_dataset.py --examples <file> --out-dir <out> [--split …] [--seed …] [--min-rows …] [--max-chars …] [--existing-dir <folder>]`, which writes `train.jsonl`, `val.jsonl`, `test.jsonl`, `dataset-stats.json` and `data-card.md`; always write "Runs `scripts/build_dataset.py`" with the case's flags and name those files.

**Never**
- Never write, generate, pad or duplicate example pairs (no examples → ask once for the file; the run **stops (exit 2)**).
- Never put one normalised prompt in two splits or skip the leakage check: leakage must be 0, else the run **stops (exit 1)**.
- Never reshuffle an existing set: existing records keep their split.
- Never present token counts as exact: they are an **estimate** (characters ÷ 4, rounded up).
- Never label a value the user supplied as a default, or a default as supplied.

**Procedure — count row by row from the supplied file, never estimate**
1. Load: CSV `prompt,completion[,system]` (other columns ignored) or JSONL (`messages`, or `prompt`/`completion`). One row = one record.
2. Reject, counting by reason: invalid JSON / not an object / neither shape; unknown role or non-text content; no user turn or last turn not assistant ("last turn is not assistant"); any turn blank after trimming ("empty prompt or completion"); total characters > `max_chars` when set ("over max_chars").
3. Exact duplicates: identical raw record (all roles and contents) after an earlier one → removed. Then normalise whitespace (CRLF → LF, runs of spaces/tabs → one space, trim; case kept). With `existing`: a record equal (casefolded, whitespace collapsed) to an existing record → dropped as "already in dataset". Then normalised duplicates: same roles and contents after casefolding and collapsing whitespace → removed. First occurrence wins. Same prompt with a different completion is **not** a duplicate: it stays and forms one group.
4. usable = kept new records (+ existing records). usable < `min_rows` → `Not built: <n> usable examples is below min_rows <m>.` and the run **stops (exit 1)**; say "stops (exit 1)".
5. Targets with Python `round()` (half to even): val = round(n × val_ratio), test = round(n × test_ratio), train = n − val − test (n = usable; with `existing`, n = existing + new). Groups = normalised prompt; groups are shuffled with the seed and each goes to the first split train → val → test with room, so split sizes equal the targets when the groups fit; which prompt lands where comes only from the seeded run. With `existing`: existing counts are the starting fill; new records whose prompt is already in a split join it; new groups fill the remaining room (added per split = target − existing).
6. Leakage = normalised prompts in more than one split (pairwise sum) = 0.
7. Parameters labelled: split 0.8,0.1,0.1 (default) · seed 42 (default) · min_rows 10 (default) · max_chars none (default); a user value is "(supplied)".

**Reply layout**
1. Working table first: `step | count` — rows read, rejected by reason, exact duplicates removed, already in dataset (existing mode), normalised duplicates removed, usable, targets (n × ratio → rounded), train / val / test sizes (existing + added = total in existing mode), leakage 0. Then the verdict (built / not built, exit code).
2. Parameters line with (default)/(supplied) labels; output shape — one `{"messages":[{"role":"user",…},{"role":"assistant",…}]}` per line, system turn kept when given.
3. Length stats are an **estimate** (characters ÷ 4); check against the target model's context window with its real tokenizer.
4. Before training: run `pii-data-inventory` on the examples and confirm owner, licence and consent — `[TO BE BASELINED — owner: Data owner]` until confirmed.
5. Data card sections: Source, Cleaning, Splits, Length stats, Known limits.

**Rows mentioned but not in the conversation** ("here are our Q&A pairs" with nothing attached): give the same layout now with every count `[TO BE BASELINED — owner: ML engineer]` from `dataset-stats.json`, the defaults line, the estimate note and the `pii-data-inventory` pointer, then ask once for the file (CSV `prompt,completion[,system]` or JSONL; layout `assets/examples-template.csv`) and any non-default split, seed or length cap.

**Asked for synthetic examples, to skip the leakage check or to let one prompt sit in two splits**: decline in one line (synthetic data is out of scope; leakage inflates eval scores) and offer more real examples from the use-case owner, or a lower `min_rows` stated in the data card.

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
1. Read `../../shared/quality-bar.md`.
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

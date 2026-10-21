---
name: eval-engineering-runner
description: Use when the user has an eval dataset (or SME-written test cases in a spreadsheet) and wants to know whether it is fit to score with — "audit our eval set", "do we have enough cases per category", "we need N safety and M refund cases — are we covered?", "turn our SMEs' test cases into a clean eval set and check them against first-cut targets", "find duplicates and leakage in the golden set", "clean this eval file". Produces eval-audit.json and eval-audit.md (verdict, per-category coverage vs targets, duplicates and near-duplicates, empty references, conflicting references, split leakage, grader coverage, balance, recommendations per category) and a cleaned eval-clean.jsonl; optional LLM review against the upstream eval-engineering guidance. Not for running evals or LLM-as-judge scoring (llm-eval-harness) or retrieval metrics (rag-pipeline-design).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: evaluate
  version: 0.2.0
  author: giri-skills
  agent:
    modes:
      new:      {case: agent-mode-new, bring: "the first test cases your experts wrote in a spreadsheet"}
      existing: {case: agent-happy-path, bring: "your current eval set and its coverage targets"}
    inputs:
      - {name: dataset, type: file, required: true, from: "eval set JSONL or CSV: id, input, expected/reference, category or tags, optional grader, split, label (layout: assets/eval-dataset.example.jsonl)"}
      - {name: targets, type: csv, required: false, from: "coverage targets CSV: category, min_cases (layout: assets/coverage-targets.example.csv); without it coverage is reported, not gated"}
      - {name: near_dup_threshold, type: string, required: false, default: "0.9", from: "token Jaccard at or above which two inputs count as near-duplicates (method parameter)"}
      - {name: review, type: flag, required: false, flag: "--review", from: "yes to add an LLM review of the audit against the upstream eval-engineering guidance"}
    run:
      - {step: audit, kind: script, cmd: "python3 -I scripts/audit_evals.py --dataset {dataset} [--targets {targets}] --near-dup-threshold {near_dup_threshold} --out-dir {out}", stdout: "{out}/audit.log"}
      - {step: upstream-review, kind: llm, template: assets/eval-review-template.md, context: ["../../../vendor/eval-engineering/SKILL.md", "../../../vendor/eval-engineering/references/verifier-design.md", "../../../vendor/eval-engineering/references/calibration.md", "{out}/eval-audit.md", "{out}/eval-audit.json"], out: "{out}/eval-review.md", skip_if_missing: [review]}
    outputs:
      - {path: "{out}/eval-audit.json", checks: [exists, json, contains:"\"coverage\""]}
      - {path: "{out}/eval-audit.md", checks: [exists, sections:["Verdict","Coverage","Quality issues","Recommendations"], no_unowned_tbd]}
      - {path: "{out}/eval-clean.jsonl", checks: [exists, cmd:"python3 scripts/check_jsonl.py {path} --require id --require input --require category"]}
---

# Eval Engineering Runner

Wraps eval-engineering from langchain-ai/langchain-skills (pinned in vendor/pins.json). The upstream skill designs Harbor tasks and verifiers by interview; this skill applies its dataset-level concerns (leakage, coverage, independent verifier evidence, fairness of the case mix) as a deterministic audit of a flat eval set. Upstream text is not copied: the optional review step reads `vendor/eval-engineering/SKILL.md` and two of its references directly.

## In a conversation: audit the set now
- **The request carries the set or the targets** (cases pasted, counts per category, or "here is our golden set and the minimum cases per category" with the file contents not in the conversation): write the audit **in this reply**, in this order. Never reply with only a request for the file.
  1. **Verdict** from the targets: PASS, FAIL (any category BELOW its `min_cases`, exit 1) or NOT GATED (no targets). Name the command that produces it: `python3 -I scripts/audit_evals.py` via the runner (see "How to run" below).
  2. **Coverage table per category**: category | min_cases | clean cases | gap | status (OK / BELOW). Counts on the cleaned set; a category with a target but no cases is BELOW. Counts not visible read `[TO BE BASELINED — owner: Eval owner]`.
  3. **Quality issues** by the `references/audit-method.md` rules with severity and action: empty input (high, dropped), empty reference for a reference-based grader (high, dropped), conflicting reference (high, later row dropped, domain owner resolves), split leakage (high, re-split), exact duplicate (medium, dropped), near-duplicate at token Jaccard ≥ 0.9 (medium, kept for review), missing grader (medium), missing category, duplicate id. Apply them to any cases shown; for an unseen file, list each check with its result `[TO BE BASELINED — owner: Eval owner, from the audit run]`.
  4. **eval-clean.jsonl**: the cleaned cases, one JSON object per line with `id, input, expected, category, tags, grader, split` (written from the cases shown; for an unseen file, state it is written by the run). The original is kept for provenance.
  5. **Recommendations with exact counts**: "add 3 safety cases (3 of 6)", "replace 2 near-duplicates", "assign a grader to 4 cases" — counts, not adjectives.
  6. One line: this audits the dataset only; it does not run the evals or judge outputs (`llm-eval-harness` does that on `eval-clean.jsonl`).
- **Targets stated, counts stated** ("we need 6 safety, 5 refund, 2 escalation cases — are we covered?"): give the coverage table with the exact gap per category and the verdict; never write new cases to close a gap, name how many to add.
- **No targets agreed**: verdict NOT GATED; each category's `min_cases` is `[TO BE BASELINED — owner: Eval owner]`; still report counts, issues and balance (largest/smallest category ratio).
- **Nothing to audit** (no set, no counts): ask once for the dataset (JSONL or CSV with id, input, expected/reference, category; optional grader, split) and the per-category targets; say no cases or targets will be invented.

## Starting points
- **New:** a spreadsheet of first cases from subject experts becomes a clean JSONL eval set, with duplicates dropped and coverage measured against first-cut targets.
- **Existing:** your current eval set is audited for duplicates, near-duplicates, leakage, missing graders and coverage gaps against its targets, and a cleaned file is written.

## When to use
- Before trusting a score: is the eval set big enough per category, free of duplicates and leakage, and gradable?
- After merging cases from several sources (logs, SMEs, synthetic) into one golden set.
- NOT for: running the evals or judging outputs (`llm-eval-harness` runs them; this skill engineers the dataset), retrieval metrics (`rag-pipeline-design`), designing Harbor tasks (the upstream skill itself).

## Inputs required
| Input | Required | Source |
|---|---|---|
| `dataset` — JSONL or CSV with id, input, expected/reference, category or tags; optional grader type, split, label | yes | eval owner; layout `assets/eval-dataset.example.jsonl` |
| `targets` — CSV category, min_cases | no (without it the verdict is NOT GATED) | eval owner + product owner; layout `assets/coverage-targets.example.csv` |
| `near_dup_threshold` — token Jaccard (default 0.9, a method parameter printed in the report) | no | eval owner |
| `review` — flag for the optional LLM review | no | user |

Targets are never invented: without a targets file each category's `min_cases` is `[TO BE BASELINED — owner: Eval owner]`.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Export the eval set to JSONL or CSV; set per-category `min_cases` with the product owner.
3. Run the skill. `scripts/audit_evals.py` applies `references/audit-method.md`: normalise inputs; drop empty inputs, empty references (unless the grader is reference-free), and exact duplicates; flag conflicting references, cross-split leakage, near-duplicates, missing or unknown graders, repeated ids; count cleaned cases per category against targets.
4. On exit 1 (FAIL) add the cases named in Recommendations, then re-run. Fix high-severity issues before scoring with `llm-eval-harness`.
5. Use `eval-clean.jsonl` as the scored set; keep the original for provenance.
6. Optional: pass `review=yes` for `eval-review.md` on `assets/eval-review-template.md`.
7. Run the self-check.

## Output
| File | Content | Checks |
|---|---|---|
| `eval-audit.json` | verdict, coverage per category, balance, label distribution, issues, issue counts, recommendations, columns used | json; has coverage |
| `eval-audit.md` | Verdict, Coverage, Quality issues, Recommendations | sections; no unowned TBD |
| `eval-clean.jsonl` | cleaned cases: id, input, expected, category, tags, grader, split (+ label) | every line JSON; id, input, category non-empty; ids unique (`scripts/check_jsonl.py`) |
| `eval-review.md` (optional) | Upstream alignment, Dataset gaps, Next actions | eval case `agent-with-review` |

## Self-check
- [ ] Every category in scope has a target; none is below it
- [ ] No input appears in more than one split; conflicting references resolved
- [ ] Every case has a grader type; reference-based graders have references
- [ ] Near-duplicates reviewed: kept only where they test something different
- [ ] Recommendations name counts, not adjectives
- [ ] The scored set is `eval-clean.jsonl`, regenerated after every change

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/eval-engineering-runner --input <name>=<value> … --out <dir>` (see `--explain ai-platform/eval-engineering-runner`). Report the `run.json` results; do not hand-write the deliverables the scripts produce (`eval-audit.json`, `eval-audit.md`, `eval-clean.jsonl`). A FAIL (exit 1) means a category is below its target: add cases and re-run.

## References
- `references/audit-method.md` — rules, severities, normalisation, and limits
- `scripts/audit_evals.py` — auditor and cleaner (argparse; stdlib)
- `scripts/check_jsonl.py` — JSONL validator used by the output check
- `assets/eval-dataset.example.jsonl`, `assets/coverage-targets.example.csv` — input layouts
- `assets/eval-review-template.md` — template for the optional review
- Upstream: `vendor/eval-engineering/SKILL.md` (langchain-ai/langchain-skills, MIT, pinned in vendor/pins.json)

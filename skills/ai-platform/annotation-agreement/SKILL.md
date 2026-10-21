---
name: annotation-agreement
description: Use when the user needs to know how consistently humans labelled data for AI evaluation or training — "measure inter-annotator agreement", "what's our Cohen's / Fleiss' kappa", "Krippendorff's alpha for these labels", "which items do annotators disagree on", "which labels do our guidelines need to clarify". Produces agreement.json, disputed-items.csv, label-agreement.csv and agreement-report.md from item_id,annotator,label rows - percent agreement, pairwise Cohen's kappa, Fleiss' kappa, nominal Krippendorff's alpha (handles missing ratings), per-label agreement, confusion pairs and low-agreement labels the guidelines do not define. Exit 1 when alpha is below the supplied minimum or no item has 2+ ratings (no score is faked). Not for scoring model outputs (llm-eval-harness), data quality (data-readiness-assessment) or building training sets (finetune-dataset-builder).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: data
  version: 0.2.0
  author: giri-skills
  agent:
    modes:
      new:      {case: agent-happy-path, bring: "labels from your pilot round and your draft guidelines"}
      existing: {case: agent-mode-existing, bring: "this round's labels plus last round's agreement results"}
    inputs:
      - {name: labels, type: csv, required: true, from: "one row per rating item_id,annotator,label (layout: assets/labels-template.csv); blank label = not rated"}
      - {name: guidelines, type: md, required: false, from: "annotation guidelines in Markdown (layout: assets/guidelines-template.md); without it guideline coverage is TBD for the Annotation lead"}
      - {name: min_agreement, type: string, required: false, from: "minimum Krippendorff's alpha agreed with the eval or data owner (e.g. 0.667 or 0.800); absent = no gate"}
      - {name: previous, type: json, required: false, from: "agreement.json from an earlier labelling round (e.g. the pilot); the report adds alpha and per-label change"}
    run:
      - {step: agreement, kind: script, cmd: "python3 -I scripts/agreement.py --labels {labels} [--guidelines {guidelines}] [--min-agreement {min_agreement}] [--previous {previous}] --out-dir {out}"}
    outputs:
      - {path: "{out}/agreement.json", checks: [exists, json, contains:"\"krippendorff_alpha\"", cmd:"python3 -I scripts/agreement.py --verify {path} --labels {labels}"]}
      - {path: "{out}/disputed-items.csv", checks: [exists, csv:[item_id,labels,majority,agreement], contains:"item_id,labels,majority,agreement", cmd:"python3 -I scripts/agreement.py --verify {path} --labels {labels}"]}
      - {path: "{out}/label-agreement.csv", checks: [exists, csv:[label,n,agreement,defined_in_guidelines], csv_rows:defined_in_guidelines!empty, "csv_rows:agreement~^(n/a|[01]\\.\\d{3})$", cmd:"python3 -I scripts/agreement.py --verify {path} --labels {labels}"]}
      - {path: "{out}/agreement-report.md", checks: [exists, sections:["Summary","Agreement","Disputed items","Guideline gaps","Method & limits"], no_unowned_tbd, cmd:"python3 -I scripts/agreement.py --verify {path} --labels {labels}"]}
---

# Annotation Agreement (inter-annotator reliability)

## In a conversation: write the agreement assessment now
The reply **is the agreement assessment draft**, never only a request for the CSV. No label rows are in the conversation, so no alpha, kappa or count is printed; each is a marker until the run.
- **The request describes a labelling round** (annotators, items, label set, purpose) but the labels are not in the conversation: write the report skeleton **in this reply**, in the order of `agreement-report.md`:
  1. **Summary** — gate verdict first: `Gate: not set — the minimum alpha is the data owner's decision` (ask them for it; never choose one), or the stated minimum against `alpha [TO BE BASELINED — computed by the run]`. Line 2: how it is computed — export one row per rating as `item_id, annotator, label` and run `scripts/agreement.py` (`python3 scripts/run_skill.py ai-platform/annotation-agreement --input labels=<labels.csv> [--input guidelines=<guidelines.md>] [--input min_agreement=<alpha>] --out <dir>`).
  2. **Agreement** — Krippendorff's alpha (nominal) is the headline; then percent agreement, pairwise Cohen's kappa per annotator pair and Fleiss' kappa (n/a with the reason when items have different numbers of ratings). State the interpretation bands as **conventions, not tests**: Krippendorff ≥ 0.800 commonly relied on, 0.667–0.800 tentative conclusions only, < 0.667 discard; Landis & Koch for kappa (< 0 poor, 0.00–0.20 slight, 0.21–0.40 fair, 0.41–0.60 moderate, 0.61–0.80 substantial, 0.81–1.00 almost perfect).
  3. **Disputed items** — table `item_id | labels (label:count) | majority (or tie) | agreement`, lowest first, to send to an adjudicator.
  4. **Guideline gaps** — per-label agreement (`label | n | agreement | defined_in_guidelines`); a low-agreement label is one below overall percent agreement; a gap is such a label the guidelines do not define, plus boundary rules for the top confusion pairs. Without guidelines: `[TO BE BASELINED — owner: Annotation lead]`.
  5. **Method & limits** — ratings must be independent; items with one rating are excluded and counted; nominal labels only; no confidence intervals; agreement measures consistency, not correctness.
- **Each item has only one annotator**: say agreement cannot be computed without two or more independent ratings per item, report no score, and recommend double-labelling a sample.
- **No labelling round described at all**: ask once for the labels export, the guidelines and the data owner's minimum alpha.
- **Asked to pick the threshold, declare labels defined without guidelines, or report a score anyway**: decline in one line (the threshold is the data owner's; definitions come from written guidelines; no score without paired ratings) and show the marker.

## Starting points
- **New:** labels from a pilot round (and draft guidelines) give alpha, disputed items and the label boundaries to sharpen before labelling at scale.
- **Existing:** add the `agreement.json` from the previous round (`previous`); the report adds alpha, percent agreement, disputed items and per-label agreement then vs now, and names labels whose agreement fell.

## When to use
- ADLC data stage: before human labels become an eval golden set, an LLM-as-judge calibration set or fine-tuning data.
- Pilot labelling round: find disputed items and the label boundaries the guidelines must sharpen before labelling at scale.
- Gate: labels may be used only when alpha meets the minimum the data owner set.
- NOT for: scoring model outputs against labels (`llm-eval-harness`), data quality or PII scans (`data-readiness-assessment`, `pii-data-inventory`), building the training file (`finetune-dataset-builder`), ordinal or interval scales (nominal labels only).

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `labels` — `item_id, annotator, label` | yes | labelling tool export (one row per rating) | run stops (exit 2), asks once |
| `guidelines` — Markdown | no | Annotation lead | `defined_in_guidelines` and the gap list read `[TO BE BASELINED — owner: Annotation lead]` |
| `min_agreement` — alpha threshold | no | eval / data owner | no gate; the report says none was set |

A blank `label` means "not rated" and is skipped. Two ratings of the same item by the same annotator stop the run (exit 2).

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Confirm ratings were independent (annotators did not see each other's labels); agreement on shared work is inflated.
3. Run the agent. `scripts/agreement.py` builds the coincidence matrix and computes alpha, Fleiss' kappa (equal ratings per item only), pairwise Cohen's kappa, per-label agreement and confusion pairs.
4. Read Disputed items worst-first; send them to an adjudicator.
5. Read Guideline gaps: define each low-agreement label the guidelines do not mention, and write a boundary rule for the top confusion pairs.
6. Re-label a fresh sample after the guideline change and re-run; compare alpha.
7. Run the self-check.

## Output
- `agreement.json` — every statistic, per-item agreement, pairs, confusion pairs, gate result, settings for `--verify`.
- `disputed-items.csv` — `item_id, labels, majority, agreement` (labels as `label:count`; `majority` is the plurality label or `tie`), lowest agreement first.
- `label-agreement.csv` — `label, n, agreement, defined_in_guidelines`.
- `agreement-report.md` — **Summary** (gate verdict first), **Agreement**, **Disputed items**, **Guideline gaps**, **Method & limits**.

## Self-check
- [ ] Alpha is reported with its band labelled as a convention (Krippendorff 0.667 / 0.800); kappas with Landis & Koch bands, also a convention
- [ ] Fleiss' kappa is n/a (with the reason) when items have different numbers of ratings — alpha is the headline
- [ ] Items with one rating are excluded and counted, not scored
- [ ] Guideline gaps come from the supplied guidelines; without them the gap list is TBD for the Annotation lead
- [ ] Limits stated: nominal only, no confidence intervals, agreement is not correctness

## References
- `references/method.md` — formulas, the worked examples the tests reproduce, per-label agreement definition
- `references/sources.md` — Cohen 1960, Fleiss 1971, Krippendorff 2011, Landis & Koch 1977; verified URLs and dates
- `assets/labels-template.csv`, `assets/guidelines-template.md` — input layouts
- `scripts/agreement.py` — statistics and `--verify` (argparse; stdlib)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/annotation-agreement --input <name>=<value> … --out <dir>` (see `--explain ai-platform/annotation-agreement`). Report the `run.json` results; do not hand-write the deliverables the script produces (`agreement.json`, `disputed-items.csv`, `label-agreement.csv`, `agreement-report.md`). Alpha below `min_agreement` fails the run (exit 1) with every output written. If no item has two or more ratings the run exits 1 and reports no score. Each output passes `--verify`, which re-derives it from the labels and the settings recorded in `agreement.json`.

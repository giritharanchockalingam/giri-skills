---
name: ai-transparency-notice
description: Use when an AI system is about to reach users and needs its transparency material — "write the 'you are talking to an AI' notice", "draft a system card", "what must we disclose under EU AI Act Article 50", "is our AI disclosure readable", "transparency checklist for our chatbot". Produces notice.md (short plain-language user notice, every sentence traced to a fact, Flesch-Kincaid graded), system-card.md (Overview, Intended use, Not intended for, Data, Model, Human oversight, Limitations, Contact, Change log), disclosure-checklist.csv (Art. 50 duties as applies / provided / missing with owners) and transparency.json from a facts CSV and an optional eu-ai-act-classifier classification.json. Exit 1 when the notice grade is above max_grade. Never claims compliance. Not for risk-tier classification (use eu-ai-act-classifier), the AI risk register (use ai-governance-risk) or rollout gates (use ai-release-plan).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: deploy
  version: 0.2.0
  author: giri-skills
  agent:
    modes:
      new:      {case: agent-happy-path, bring: "the facts about your AI system and its classification"}
      existing: {case: agent-mode-existing, bring: "current facts plus the notice users see today"}
    inputs:
      - {name: facts, type: csv, required: true, from: "system facts key,value,source,notes (layout: assets/facts-template.csv) - system_name, provider, purpose, model, data_sources, human_oversight, known_limitations, intended_users, not_intended_for, contact, yes/no flags, last_updated, Art. 50 evidence facts"}
      - {name: classification, type: json, required: false, from: "classification.json from ai-platform/eu-ai-act-classifier (tier and basis read if present); absent -> TBD for the Compliance lead"}
      - {name: max_grade, type: string, required: false, from: "reading-grade ceiling for the notice (default 8)"}
      - {name: published_notice, type: md, required: false, from: "the notice users see today (Markdown or text); redlined sentence by sentence into notice-redline.md"}
      - {name: strict, type: flag, required: false, flag: "--strict", from: "true to fail the run (exit 1) when a fact the notice needs is missing"}
    run:
      - {step: notice, kind: script, cmd: "python3 -I scripts/transparency_notice.py --facts {facts} [--classification {classification}] [--max-grade {max_grade}] {strict} [--published-notice {published_notice}] --out-dir {out}"}
    outputs:
      - {path: "{out}/notice.md", checks: [exists, contains:"It is an AI system, not a person.", max_lines:30, cmd:"python3 -I scripts/transparency_notice.py --verify {path}"]}
      - {path: "{out}/system-card.md", checks: [exists, sections:["Overview","Intended use","Not intended for","Data","Model","Human oversight","Limitations","Contact","Change log"], no_unowned_tbd, contains:"does not claim compliance"]}
      - {path: "{out}/disclosure-checklist.csv", checks: [exists, csv:[duty,article,applies,provided,evidence,owner], csv_rows:owner!empty, "csv_rows:article~^Art\\. 50\\(\\d\\)$", "csv_rows:status~^(provided|partial|missing|to confirm|not applicable)$"]}
      - {path: "{out}/transparency.json", checks: [exists, json, contains:"\"grade\"", contains:"\"missing_facts\""]}
---

# AI Transparency Notice (user notice, system card, Art. 50 checklist)

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ai-transparency-notice --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ai-transparency-notice`). Report the `run.json` results; do not hand-write the deliverables the script produces (`notice.md`, `system-card.md`, `disclosure-checklist.csv`, `transparency.json`). A notice above the reading-grade ceiling fails the run (exit 1) on purpose; every output is still written so the facts can be rewritten in plainer words.

## Starting points
- **New:** the system's facts (and the classifier output) give the user notice, the system card and the Art. 50 checklist.
- **Existing:** add the notice users see today (`published_notice`); notice-redline.md marks each sentence unchanged, changed, added or removed, and every removed sentence is a published claim the facts no longer support.

## When to use
- ADLC deploy stage: before users first see an AI assistant, chatbot or content generator.
- "What do we tell users, and what does Article 50 expect us to disclose?" — notice plus a duty-by-duty checklist with evidence and owners.
- Reviewer pack: a system card whose every row cites the source of the fact.
- NOT for: deciding the EU AI Act risk tier (`eu-ai-act-classifier`), the risk register (`ai-governance-risk`), staged rollout (`ai-release-plan`), legal sign-off (route to counsel — this skill never claims compliance).

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `facts` — kv-csv `key,value,source,notes` | yes | Product owner (copy `assets/facts-template.csv`) | run stops (exit 2), asks once |
| `classification` — `classification.json` | no | output of `ai-platform/eu-ai-act-classifier` | system card classification line is `[TO BE BASELINED — owner: Compliance lead]` |
| `max_grade` — reading grade | no | accessibility or brand standard | 8 |
| `strict` — true/false | no | release owner | false: notice written with TBD markers, exit 0 |

Each missing fact is `[TO BE BASELINED — owner: Product owner]` in the card and notice. Yes/no facts (`generates_synthetic_content`, `emotion_recognition`, `biometric_categorisation`, `interacts_directly`, `deep_fake`, `public_interest_text`) accept only yes or no; anything else exits 2.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. The Product owner fills `assets/facts-template.csv`, writing each fact as a plain phrase that completes its template sentence, with a source for every row.
3. Optionally run `ai-platform/eu-ai-act-classifier` first and pass its `classification.json`.
4. Run the agent. `scripts/transparency_notice.py` assembles the notice from `assets/notice-sentences.csv`, grades it (`references/readability.md`), writes the system card and evaluates `assets/art50-duties.csv` (`references/method.md`).
5. Grade above `max_grade` → exit 1: rewrite the long facts, not the notice.
6. Work every `missing` and `to confirm` checklist row with its owner. Treat `partial` on Art. 50(5) as a prompt for an accessibility review.
7. Have counsel review the checklist before launch; run the self-check.

## Output
- `notice.md` — the user-facing notice (one sentence per line, ≤ 15 sentences).
- `system-card.md` — Overview (with classification), Intended use, Not intended for, Data, Model, Human oversight, Limitations, Contact, Change log (grade, checklist counts, facts not supplied).
- `disclosure-checklist.csv` — `duty, article, addressee, applies, provided, status, evidence, owner`.
- `transparency.json` — `grade`, `max_grade`, `grade_ok`, `word_count`, `sentence_count`, `syllable_count`, `notice_sentences`, `notice_missing_facts`, `missing_facts`, checklist counts, classification.

## Self-check
- [ ] Every notice sentence comes from a template and a fact; `--verify` re-grades `notice.md` to the same numbers
- [ ] Grade within `max_grade`, or the run failed and says so
- [ ] Every checklist row has an owner; nothing says "compliant"
- [ ] Missing facts are TBD for the Product owner; missing classification is TBD for the Compliance lead
- [ ] Limits stated: heuristic syllable count, exemptions not assessed, not a legal determination

## References
- `references/sources.md` — Article 50, 111(4), 113 text checked 2026-10-18; Flesch–Kincaid source
- `references/readability.md` — grade formula, syllable heuristic and its limits
- `references/method.md` — notice assembly, card rules, checklist rules
- `assets/facts-template.csv`, `assets/notice-sentences.csv`, `assets/art50-duties.csv` — input layout, templates, duty catalog
- `scripts/transparency_notice.py` — builder and `--verify` (argparse; stdlib)

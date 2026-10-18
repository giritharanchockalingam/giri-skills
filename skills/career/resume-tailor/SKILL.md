---
name: resume-tailor
description: Use when the user asks to tailor, rewrite, or ATS-optimize their résumé for a specific job description (JD), or to produce a targeted executive summary or bullet set for a senior director / VP / executive IT role. Produces an ATS keyword map, rewritten bullets (action + scope + metric + outcome), a before/after diff, and a traceability table. TRUTH LOCK - every bullet must trace to a line in the user's master résumé; the skill refuses to add claims that are not in it.
license: MIT
metadata:
  domain: career
  adlc_stage: career
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: jd, type: file, required: true, from: "job description text file"}
      - {name: master, type: md, required: true, from: "master résumé with MR-Lnn | line ids (layout: assets/master-resume.example.md)"}
    run:
      - {step: map, kind: script, cmd: "python3 -I scripts/tailor.py --jd {jd} --master {master} --keyword-map {out}/keyword-map.csv --gap-list {out}/gap-list.md --bullets {out}/candidate-bullets.md"}
      - {step: draft, kind: llm, template: assets/tailored-resume-template.md, context: ["{out}/candidate-bullets.md", "{out}/keyword-map.csv", "{out}/gap-list.md", "{master}", "references/bullet-formula.md"], out: "{out}/tailored-resume.md"}
      - {step: trace, kind: script, cmd: "python3 -I scripts/check_traceability.py --resume {out}/tailored-resume.md --master {master} --out {out}/traceability.csv"}
    outputs:
      - {path: "{out}/keyword-map.csv", checks: [exists, csv:[jd_keyword,present_in_master,master_line_ids,weight], csv_rows:present_in_master~^(yes|no)$]}
      - {path: "{out}/gap-list.md", checks: [exists, sections:["Gap list"]]}
      - {path: "{out}/candidate-bullets.md", checks: [exists, sections:["Candidate bullets"]]}
      - {path: "{out}/tailored-resume.md", checks: [exists, sections:["Summary","Selected experience","Skills"], no_unowned_tbd, cmd:"python3 -I scripts/check_traceability.py --resume {path} --master {master} --out {out}/traceability.csv"]}
      - {path: "{out}/traceability.csv", checks: [exists, csv:[bullet,cited_ids,all_ids_exist,numbers_in_bullet_found_in_cited_lines]]}
---

# Résumé Tailor (truth-locked)

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py career/resume-tailor --input <name>=<value> … --out <dir>` (see `--explain career/resume-tailor`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.

## When to use
- "Tailor my résumé for this JD", "make this ATS-friendly", "rewrite my summary for a VP role", "which keywords am I missing".
- After `jd-fit-scorer` returns GO / LEAN GO.
- NOT for: scoring fit (use `jd-fit-scorer`), cover letters or recruiter messages (use `outreach-and-followup`), interview stories (use `interview-prep`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Master résumé (full, untailored, with line numbers or stable bullet IDs) | yes | user file; format in `assets/master-resume.example.md` |
| JD full text | yes | user paste |
| Target title and level | no | JD; default Sr Director |
| Fit output from `jd-fit-scorer` | no | prior step; speeds keyword mapping |
| Page limit and format (2-page, ATS plain, LinkedIn) | no | user; default 2-page ATS plain |

If the master résumé is missing, stop and ask for it. Do not build from memory, LinkedIn recollection, or prior conversations.

## TRUTH LOCK (hard rule)
1. The master résumé is the only source of facts: employers, titles, dates, team sizes, budgets, metrics, technologies, awards.
2. Every tailored bullet carries a source reference `[MR-L<line>]` or `[MR-<bullet-id>]`.
3. Allowed transformations: reorder, reword, merge two source bullets, drop detail, change emphasis, swap synonyms for JD keywords **when the master résumé supports the underlying fact**.
4. Not allowed: new metrics, inflated numbers, new technologies, new scope, new titles, implied certifications, "led" where the source says "contributed to".
5. If the user asks to add a claim with no source line, refuse that claim, explain why in one sentence, and offer two options: (a) add the fact to the master résumé first with their confirmation it is true, or (b) phrase the adjacent true fact instead. Continue with the rest of the tailoring.
6. The output must include a traceability table. A bullet with no source row is a defect; remove it before returning.

## Procedure
1. Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md`.
2. Number the master résumé lines if not already numbered (`MR-L1`…). Do not alter content.
3. Build the ATS keyword map per `references/ats-keyword-mapping.md`: JD keyword → exact/synonym → master résumé evidence line → placement (summary, core competencies, bullet, skills).
4. Flag JD keywords with no evidence as **UNSUPPORTED**. These go in the gap note to the user, never into the résumé.
5. Rewrite the executive summary (≤4 lines) using only supported keywords; structure per `references/executive-resume-structure.md`.
6. Rewrite bullets with the formula in `references/bullet-formula.md`. Prioritize the 8–12 bullets most relevant to the JD's must-haves; demote the rest. Patterns (not facts) are in `assets/bullet-bank.md`.
7. Produce the before/after diff per `references/diff-format.md`.
8. Produce the traceability table: tailored bullet → `[MR-Lxx]` → transformation type.
9. Run the self-check. Reply ≤50 words outside the artifact.

## Output
Markdown file `resume-<company>-<role>.md` containing, in order:
1. Keyword map table (JD keyword | status | evidence | placement)
2. Tailored résumé (ATS plain: no tables, no columns, no graphics, standard headings)
3. Before/after diff
4. Traceability table
5. Unsupported-claims note (what the JD wants that the master résumé cannot support, and what to do about it)

## Self-check
- [ ] Every tailored bullet has a `[MR-…]` source and appears in the traceability table
- [ ] No number, employer, title, date, or technology appears that is absent from the master résumé
- [ ] Any user-requested unsupported claim was refused with an explanation and alternatives
- [ ] Summary ≤4 lines; bullets ≤2 lines each; action verb first; metric present where the source has one
- [ ] ATS plain formatting: standard section names, no tables inside the résumé body, dates as `Mon YYYY – Mon YYYY`
- [ ] Banned words from `writing-style.md` absent (leverage, synergy, robust, seamless, cutting-edge)
- [ ] No author personal data pulled from memory; everything comes from the supplied master résumé

## References
- `scripts/tailor.py` — JD keyword → master-line evidence map, gap list, verbatim candidate bullets (stdlib, offline)
- `scripts/check_traceability.py` — the TRUTH LOCK gate: exit 1 on an uncited bullet, an unknown id, or a number absent from its cited lines
- `assets/tailored-resume-template.md` — the llm step fills this; every bullet ends with `[MR-Lnn]`
- `references/ats-keyword-mapping.md` — mapping method, synonym rules, density limits
- `references/bullet-formula.md` — action + scope + metric + outcome, exec verbs, anti-patterns
- `references/executive-resume-structure.md` — section order, length, what to cut at exec level
- `references/diff-format.md` — before/after and traceability table layouts
- `assets/master-resume.example.md` — EXAMPLE master résumé format (fictional)
- `assets/bullet-bank.md` — reusable bullet patterns (no facts)

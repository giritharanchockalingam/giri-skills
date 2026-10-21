---
name: jd-fit-scorer
description: Use when the user pastes a job description (JD) or job link and asks whether to apply, how well they fit, or to score/rank roles — including a scoring request made before the résumé or profile is shared, and how strict the matching should be ("exact matches only", a higher match threshold). Produces a weighted fit score (must-haves 60%, nice-to-haves 25%, culture/logistics 15%, red flags subtract), a gap table, and a go/no-go call for senior director / VP / executive IT roles. Requires the user's profile keywords or master résumé; never invents experience.
license: MIT
metadata:
  domain: career
  adlc_stage: career
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: jd, type: file, required: true, from: "job description text file"}
      - {name: profile, type: file, required: true, from: "profile keyword file (layout: assets/profile-keywords.example.txt)"}
      - {name: threshold, type: string, required: false, default: "0.5"}
      - {name: resume, type: md, required: false, from: "your existing résumé (MR-Lnn | lines or bullets); its lines are matched as evidence and cited by line id"}
    run:
      - {step: score-json, kind: script, cmd: "python3 -I scripts/score.py --jd {jd} --profile {profile} [--resume {resume}] --threshold {threshold} --json", stdout: "{out}/fit.json"}
      - {step: score-table, kind: script, cmd: "python3 -I scripts/score.py --jd {jd} --profile {profile} [--resume {resume}] --threshold {threshold}", stdout: "{out}/fit.md"}
    outputs:
      - {path: "{out}/fit.json", checks: [exists, json, contains:"verdict"]}
      - {path: "{out}/fit.md", checks: [exists, contains:"/100"]}
    modes:
      new: {case: agent-happy-path, bring: "the job description and a skills-and-limits list"}
      existing: {case: agent-mode-existing, bring: "the job description and the résumé you already have"}
---

# JD Fit Scorer

## In a conversation: score the role now
- **The JD and the profile (keyword file or résumé) are both supplied** (even if "pasted" or "attached" and only partly visible): score in this reply, in this order: (1) first line is the verdict — `GO / LEAN GO / LEAN NO / NO-GO — <score>/100 — <reason>`; (2) bucket table with weights must-haves 60 / nice-to-haves 25 / culture-logistics 15, items, MATCH / PARTIAL / GAP counts and the math (`bucket = weight × Σcredit ÷ items`, MATCH 1.0, PARTIAL 0.5, total minus red-flag penalties); (3) gap table — every MATCH or PARTIAL cites the profile line it rests on, every GAP has a mitigation or "accept gap"; (4) red flags with penalties, or "none detected"; (5) next action. Requirements or profile lines not visible in the conversation are `[TO BE BASELINED — owner: ___]`, and the verdict line says which inputs it still depends on. Never reply with only a request for files.
- **A hard constraint is breached** (active clearance required but the profile says none; travel above the profile's max + 15 points; location, comp floor): check these before any score. The verdict is **NO-GO** regardless of the keyword score; name each constraint hit explicitly with the JD text and the profile line; suggest logging the role in the tracker as Passed with the reason (`application-tracker`).
- **Asked to change how strict matching is** ("only count exact matches", "be strict"): raise the match threshold (the share of a requirement's words the profile must carry; default 0.5, e.g. 0.9 for near-exact) and rescore — weaker overlaps become GAP, not PARTIAL. The verdict still comes from the same weights and rules; say in the verdict line which threshold was used.
- **No profile or résumé supplied**: ask once for the profile keyword file or master résumé. Do not score from memory, from the user's job title or from earlier conversation, and do not state any experience the user has not supplied.

## Starting points
- **New** — write a short profile from the template (skills plus your limits: location, travel, comp floor, clearance) and the JD is scored against it: must-have / nice-to-have / culture fit, red flags, a go/no-go verdict.
- **Existing** — add the résumé you already have: its lines are read as evidence and each matched requirement cites the résumé line id, so a profile with only your limits is enough.

## When to use
- User pastes a JD, posting URL text, or recruiter summary and asks "should I apply?", "how well do I fit?", "score this", or "rank these roles".
- User wants a gap list before tailoring a résumé.
- NOT for: rewriting the résumé (use `resume-tailor`), evaluating an offer (use `offer-evaluator`), or logging the application (use `application-tracker`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| JD full text (title, responsibilities, requirements, location, comp if listed) | yes | user paste or file |
| Profile keyword file or master résumé | yes | `assets/profile-keywords.example.txt` format; user supplies the real one |
| Hard constraints (location, travel, remote, comp floor, clearance) | no | user; defaults in `references/scoring-rubric.md` |
| Target level (Sr Director / VP / CxO) | no | user; default Sr Director |

If the JD or the profile is missing, ask once. Do not score from memory or from a job title alone.

## Procedure
1. Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md`.
2. Parse the JD into three buckets: **must-haves** (required, "must", years, certifications, degree, clearance), **nice-to-haves** (preferred, "plus", "ideally"), **culture/logistics** (location, remote policy, travel, reporting line, team size, comp band, industry).
3. Normalize each requirement to a short keyword phrase (≤6 words). Collapse duplicates.
4. Match each requirement against the profile keyword file. Mark `MATCH`, `PARTIAL` (adjacent skill or older than 7 years), or `GAP`. Cite the profile line for every MATCH/PARTIAL; a match with no citation is a GAP.
5. Scan the JD against `references/red-flag-catalog.md`. Record each hit with its penalty.
6. Score using `references/scoring-rubric.md`. Optional: run `scripts/score.py` (`--jd jd.txt --profile profile.txt`) for the deterministic keyword pass, then apply judgement to PARTIALs.
7. Apply the go/no-go thresholds in `references/go-no-go.md`. Hard-constraint violations force NO-GO regardless of score.
8. Produce the output below. Run the self-check.

## Output
Markdown, first line is the verdict. Save as `fit-<company>-<role>.md` if a file is requested.

```
GO / LEAN GO / LEAN NO / NO-GO — <score>/100 — <one-sentence reason>

| Bucket | Weight | Items | Matched | Partial | Gap | Bucket score |
| Red flags | — | <n> hits | penalty −<n> |

Gap table: | Requirement | Bucket | Status | Evidence (profile line) | Mitigation |
Red flags: | Flag | Penalty | JD text |
Next action: apply via … / tailor résumé / ask recruiter X before applying / pass
```

## Self-check
- [ ] Every MATCH/PARTIAL cites a profile line; none inferred from job titles alone
- [ ] Weights sum to 100 before penalties; math shown
- [ ] Hard constraints checked before the score is reported
- [ ] Gap table includes a mitigation or "accept gap" for every GAP
- [ ] Verdict is the first line; reply ≤50 words outside the artifact
- [ ] No author personal data pulled from memory; profile comes from the supplied file only

## References
- `references/scoring-rubric.md` — weights, status values, bucket math
- `references/red-flag-catalog.md` — penalties and detection phrases
- `references/go-no-go.md` — thresholds and hard-constraint overrides
- `scripts/score.py` — offline keyword pass (stdlib only)
- `assets/profile-keywords.example.txt` — profile file format (EXAMPLE, fictional)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py career/jd-fit-scorer --input <name>=<value> … --out <dir>` (see `--explain career/jd-fit-scorer`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.

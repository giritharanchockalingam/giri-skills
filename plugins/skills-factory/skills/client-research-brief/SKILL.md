---
name: client-research-brief
description: Use when the user asks to research a company, account, or prospect before a pitch, discovery call, or proposal ("research <company> before the meeting", "build me a brief on <account>"). Produces a sourced one-page brief — business snapshot, filings and financial signals, technology-stack signals, leadership, recent news, likely initiatives, and hypotheses for the call — with every claim carrying a source and every unknown marked. Includes a no-network script that turns a notes/links file into the brief skeleton. Do not use for competitor battle cards (competitive-positioning) or for synthesizing a call (discovery-interview).
license: MIT
metadata:
  domain: presales
  adlc_stage: opportunity
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: notes, type: file, required: true, from: "notes/links file the user collected (.md or .txt); nothing is fetched"}
      - {name: company, type: string, required: true}
      - {name: purpose, type: string, required: false, default: "discovery", from: "discovery | proposal | exec-meeting | pitch"}
      - {name: previous, type: md, required: false, from: "the brief written last time for this client; new material is marked and dropped sources listed"}
      - {name: draft_only, type: flag, required: false, flag: "--draft-only", from: "true to skip the model step: brief.md is written from the notes, every item cited, labelled as a draft"}
    run:
      - {step: skeleton, kind: script, cmd: "python3 -I scripts/brief_skeleton.py --notes {notes} --company {company} --purpose {purpose} [--previous {previous}] --out {out}/brief-skeleton.md --final {out}/brief.md {draft_only}"}
      - {step: brief, kind: llm, template: assets/brief-template.md, context: ["{out}/brief-skeleton.md", "{notes}", "references/research-method.md"], out: "{out}/brief.md", skip_if_present: [draft_only]}
    outputs:
      - {path: "{out}/brief-skeleton.md", checks: [exists, sections:["Bottom line","Sources"]]}
      - {path: "{out}/brief.md", checks: [exists, sections:["Bottom line","Snapshot","Technology signals","Questions for the call","Sources"], no_unowned_tbd, cites_source_ids:"{out}/brief-skeleton.md"]}
    modes:
      new: {case: agent-mode-new, bring: "your notes and links on the company"}
      existing: {case: agent-mode-existing, bring: "fresh notes plus the last brief on this client"}
---

# client-research-brief

## In a conversation: write the brief now
- **The request names the company and the purpose** (the angle is optional — when it is missing, the brief is still written and the angle shows `[TO BE BASELINED — owner: ___]`; with or without a notes file — if the notes are said to be attached but their contents are not in the conversation, work from what the request states): write the brief **in this reply**, applying the skeleton script's classification by hand (sort each note item — filing link, job posting, announcement — into its section and number it as a source `[S1]…`). Never reply with only a request for the file. In template order (`assets/brief-template.md`):
  1. **Bottom line** — three facts the reader must walk in knowing, each with its source.
  2. **Snapshot** — each cell sourced or `[TO BE BASELINED — owner: ___]`.
  3. **Financial signals** — each number cites the filing and its section/page (e.g. "10-K, Item 7, p. __"); figures not quoted in the request stay `[TO BE BASELINED — owner: ___]` naming the filing section to read.
  4. **Technology signals table** — signal, source and tier, confidence (High / Med / Low per the playbook), and the confirming question for the call.
  5. **Leadership** — public-record facts only (title, since, prior employer, quoted priorities); no personality inference.
  6. **Recent news** (≤6, dated) · **Likely initiatives** labelled *Hypothesis*, each with the signal and its tier and the confirming question · **Risks and landmines** · **Questions for the call**.
  7. **Sources** — every URL or document with date accessed and tier.
  Keep the reply to about one page (≈700 words) so the Sources list is always complete.
- **Company or purpose missing or ambiguous** ("a brief on Apex"): ask once which company (legal name, HQ country, ticker if listed) and the purpose and date of the meeting. Do not produce a brief for a guessed company and do not invent a notes file or sources.
- **Asked to fill revenue, IT spend or other figures that no source gives** (private company, "use what you think it is"): say in one line that private-company figures are not estimated without a cited public source. Show those cells as `[TO BE BASELINED — owner: ___]` — never print an estimate anywhere, and never cite aggregator revenue estimates. Use only the user's notes as sources, rate a fact resting on a single signal **Low**, and give the specific discovery question that would baseline each figure (e.g. "What is the annual run cost of your WMS and integration estate?").

## Starting points
- **New** — your notes and links are sorted into the brief's sections with every source numbered; the model step writes the brief, or with `draft_only` the brief is your notes verbatim, each item cited, the so-what left as owned markers.
- **Existing** — add `previous` (the last brief on this client): material already in it is carried, new material is marked NEW, and sources it cited that your notes no longer carry are listed to re-check or drop.

## When to use
- "Research <company> before the pitch on <date>."
- "What is <account> likely to be spending on in the next 12 months?"
- "Build a brief on the new CIO at <company>."
- NOT for: competitor analysis (`competitive-positioning`), quarterly account strategy (`account-plan`), call synthesis (`discovery-interview`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Company legal/common name, HQ country | yes | user |
| Purpose: pitch / discovery / proposal / exec meeting, and date | yes | user |
| Our angle: the service line or initiative we are positioning | yes | user |
| Notes/links file (`notes.md` or `.txt`: URLs, pasted excerpts, prior-contact notes) | no | file |
| Named stakeholders to profile | no | user |
| Network access available? (yes/no) | yes | environment |

If company name or purpose is missing, ask once. A missing notes file or angle does not stop the brief: unsourced cells are marked `[TO BE BASELINED — owner: ___]`. Never guess which company is meant when names collide (ask "Acme Corp (NYSE: ACM) or Acme Ltd (UK)?").

## Procedure
Read `../../shared/quality-bar.md` and `../../shared/writing-style.md` first.

1. **Scope the brief to the purpose.** A discovery brief emphasizes initiatives and pains; a proposal brief emphasizes procurement, incumbents, and financial capacity; an exec-meeting brief emphasizes the individual and their public positions. Use `references/research-method.md` §1 to pick the emphasis weights.
2. **Build the source plan** from `references/research-method.md` §2 (source tiers: filings > investor materials > regulator/press releases > reputable press > job postings > vendor case studies > social). Decide which tiers are reachable: if no network, only the notes file and user-provided excerpts count as sources; everything else is `[TO BE BASELINED — owner: ___]`.
3. **Run the skeleton script** when a notes file exists: `python3 -I scripts/brief_skeleton.py --notes notes.md --company "<name>" --out brief.md`. It classifies links and excerpts into the brief sections and lists what is still empty. Then fill each section by reading the sources (the script does not fetch).
4. **Extract tech-stack signals** using `references/tech-signal-playbook.md`: job postings (platform names, team sizes), engineering blogs, case studies by vendors, conference talks, open-source repos, status pages, DNS/MX hints if provided. Record each signal with confidence (High / Med / Low) per the playbook rubric; never upgrade confidence without a second independent source.
5. **Decision point — financial capacity.** If public: pull revenue, operating margin trend, capex/opex guidance, and any stated cost-out or transformation program from the latest annual/quarterly filing (cite the document and page). If private: state ownership (PE / founder / family), last funding or acquisition event if public, and mark capacity `[TO BE BASELINED — owner: ___]`. Do not estimate revenue for a private company.
6. **Profile leadership** limited to the roles that matter for our angle (CIO/CTO/CDO, the business sponsor, CFO, CISO where security gates apply). Tenure, prior employer, public statements, and what they have changed since arrival. Public-record facts only; no inference about personality or politics.
7. **Derive likely initiatives** as hypotheses, not facts: each row cites the signal(s) behind it and states what question on the call would confirm it. Feed these to `discovery-interview`.
8. **Write the brief** on `assets/brief-template.md`. One page. Bottom line first: the three facts the reader must walk in knowing. Sources appendix lists every URL/document with the date accessed.
9. Run the self-check. Delete any sentence you cannot trace to a source line or to the user's notes.

## Output
- File: `client-brief-<company-slug>-<yyyy-mm-dd>.md`
- Sections (template order): Bottom line · Snapshot · Financial signals · Technology signals (table with confidence) · Leadership · Recent news (≤6 items, dated) · Likely initiatives and hypotheses · Risks and landmines · Questions for the call · Sources
- Length: ≤ 1 page body plus sources. If longer, move detail to an appendix.

## Self-check
- [ ] Every number carries a source (document + page/section, or URL + date)
- [ ] No revenue, headcount, or spend estimate for a private company unless from a cited public source
- [ ] Tech signals carry a confidence rating; no "they use X" at Low confidence
- [ ] Leadership section contains only public-record facts; no personal characterizations
- [ ] Likely initiatives are labeled hypotheses with the confirming question
- [ ] No content from other clients or from the author's own history
- [ ] Bottom line is three facts, first lines of the document

## References
- `references/research-method.md` — emphasis by purpose, source tiers, financial-signal extraction, writing rules
- `references/tech-signal-playbook.md` — where tech-stack signals live and how to rate confidence
- `assets/brief-template.md` — one-page brief template
- `scripts/brief_skeleton.py` — notes/links file → brief skeleton with empty-section report (no network)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py presales/client-research-brief --input <name>=<value> … --out <dir>` (see `--explain presales/client-research-brief`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.

---
name: client-research-brief
description: Use when the user asks to research a company, account, or prospect before a pitch, discovery call, or proposal ("research <company> before the meeting", "build me a brief on <account>"). Produces a sourced one-page brief — business snapshot, filings and financial signals, technology-stack signals, leadership, recent news, likely initiatives, and hypotheses for the call — with every claim carrying a source and every unknown marked. Includes a no-network script that turns a notes/links file into the brief skeleton. Do not use for competitor battle cards (competitive-positioning) or for synthesizing a call (discovery-interview).
license: MIT
metadata:
  domain: presales
  version: 0.1.0
  author: giri-skills
---

# client-research-brief

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

If company name or purpose is missing, ask once. Never guess which company is meant when names collide (ask "Acme Corp (NYSE: ACM) or Acme Ltd (UK)?").

## Procedure
Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md` first.

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

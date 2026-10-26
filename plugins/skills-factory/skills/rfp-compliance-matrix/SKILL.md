---
name: rfp-compliance-matrix
description: Use when an RFP, RFI, RFQ, or tender document is received and the user asks to inventory requirements, build a compliance matrix, assess bid/no-bid, or draft clarification questions. Produces a numbered requirement inventory (CSV), a compliance matrix (Comply / Partial / Non-comply / Clarify, with owner, evidence, and response pointer), a gaps-and-risks list, a clarification-question list, and a bid/no-bid recommendation. Includes a script that extracts numbered and shall/must requirements from .txt/.md/.docx/.pdf into CSV. Do not use for writing the proposal narrative (proposal-writer) or pricing (effort-estimator).
license: MIT
metadata:
  domain: presales
  adlc_stage: opportunity
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: rfp, type: file, required: true, from: "the RFP document (.txt .md .docx .pdf)"}
      - {name: capabilities, type: csv, required: true, from: "our capability inventory (columns: capability_id, keywords, status, evidence, owner, gap_condition, mitigation, category)"}
      - {name: min_words, type: string, required: false, default: "4"}
      - {name: previous, type: csv, required: false, from: "matrix.csv from the earlier round (before an addendum or re-bid); reviewed answers for unchanged clauses are carried"}
    run:
      - {step: extract, kind: script, cmd: "python3 -I scripts/extract_requirements.py {rfp} --out {out}/requirements.csv --min-words {min_words}"}
      - {step: score, kind: script, cmd: "python3 -I scripts/score_matrix.py {out}/requirements.csv --capabilities {capabilities} [--previous {previous}] --out {out}/matrix.csv --gaps {out}/gaps.md --summary {out}/bid-score.json"}
    outputs:
      - {path: "{out}/requirements.csv", checks: [exists, csv:[req_id,client_id,text,mdo_hint]]}
      - {path: "{out}/matrix.csv", checks: [exists, csv:[req_id,mdo,compliance,evidence,gap_condition,mitigation,owner,clarification_id]]}
      - {path: "{out}/gaps.md", checks: [exists, sections:["Bottom line","Mandatory gaps","Clarification questions"], no_unowned_tbd]}
      - {path: "{out}/bid-score.json", checks: [exists, json]}
    modes:
      new: {case: agent-happy-path, bring: "the RFP document and your capability inventory"}
      existing: {case: agent-mode-existing, bring: "the revised RFP plus your reviewed matrix from the last round"}
---

# rfp-compliance-matrix

## In a conversation: build the matrix now
- **The request carries the RFP and the capability source** — including when the RFP PDF and catalog are said to be attached but their contents are not in the conversation: produce the bid review **in this reply** from the stated facts. Never reply with only a request for files. In this order:
  1. **Bid call on line 1** — `BID / BID-WITH-CONDITIONS / NO-BID` (provisional where the gate tests are open) with its three drivers.
  2. **Requirement inventory** — apply `scripts/extract_requirements.py`'s rules by hand: numbered clauses and shall/must/required sentences, wrapped lines merged, boilerplate moved to Administrative, items from tables and appendices added, client IDs kept with our `REQ-nnn` alongside.
  3. **Classification** — every requirement by category (`FUN TEC SEC COM DEL ADM`) and `M/D/O` per `references/requirement-taxonomy.md`; hidden mandatories flagged.
  4. **Compliance matrix** in the column order of `assets/compliance-matrix-columns.md` (`req_id, client_id, section, page, text, category, mdo, weight, flags, compliance, evidence, gap_condition, mitigation, owner, response_section, status, clarification_id`). No `C` without an evidence citation from the capability catalog; no evidence → `P` or `Q`.
  5. **Gaps and risks** — every `P`/`N` with mitigation, risk if unmitigated and owner.
  6. **Clarification questions** — one per item, neutral, citing the clause ID, revealing no gap.
  7. **Deadlines** (Q&A, submission) with the RFP page, or page `[TO BE BASELINED — owner: ___]` · **Response plan** (section, owner, due).
  Rows the request cannot fill show `[TO BE BASELINED — owner: ___]`; end with the few questions that close them.
- **No RFP at all**: ask once for the document. **No capability source**: ask once for the capability statement or service catalog, and still produce the requirement inventory and taxonomy classification now; if the user declines, mark every compliance cell `Q` with `owner: ___` rather than guessing `C`.
- **Asked to mark items Comply without evidence** ("we are basically SOC 2 ready, ISO 27001 next quarter", "no partials in front of the client"): say in one line that `C` requires current, in-scope certification evidence. Score those requirements `P` with mitigation `roadmap` and the expected date `[TO BE BASELINED — owner: ___]` (never the hoped-for date); flag the mandatory items in gaps-and-risks with an owner; offer client-facing wording that presents the roadmap commitment without misrepresenting current status.

## Starting points
- **New** — the RFP is split into requirements, each scored against your capability inventory (C/P/Q with evidence and owner), with mandatory gaps, clarification questions and a provisional bid gate.
- **Existing** — add `previous` (your reviewed matrix from the last round): unchanged clauses keep their reviewed answer, changed clauses are re-scored and flagged for re-review, new clauses are flagged, and withdrawn ones are listed to drop from the response.

## When to use
- "We received an RFP from <client>; break it down."
- "Build the compliance matrix for this RFI."
- "Should we bid on this?"
- "What clarification questions do we send before the deadline?"
- NOT for: proposal prose (`proposal-writer`), pricing (`effort-estimator`), SOW (`sow-drafter`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| RFP document(s): .pdf / .docx / .md / .txt, including appendices | yes | file |
| Submission deadline, Q&A deadline, format rules (page limits, forms) | yes (extract or ask) | document / user |
| Our capability statement or service catalog (what we can claim) | yes | file / user |
| Named owners for response sections (or "assign later") | no | user |
| Known incumbent / competitive context | no | user |

If the RFP file is missing, ask once. If the capability source is missing, ask once and still produce the inventory and classification; if it stays missing, mark every compliance cell `Q` (Clarify) with `owner: ___` rather than guessing what we comply with. Missing deadlines or owners do not stop the matrix: they are marked `[TO BE BASELINED — owner: ___]`.

## Procedure
Read `../../shared/quality-bar.md` and `../../shared/writing-style.md` first.

1. **Extract the requirement inventory.** Run `python3 -I scripts/extract_requirements.py <rfp-file> --out requirements.csv`. The script captures numbered clauses (1.2.3, (a), R-014), and sentences with shall / must / required / will provide, with section context and page. Review the CSV: merge split sentences, drop boilerplate (definitions, instructions to bidders go in a separate "Administrative" category), and add any requirements the script missed from tables and appendices. Never renumber the client's IDs; add our `REQ-nnn` alongside.
2. **Classify every requirement** using `references/requirement-taxonomy.md`: Category (Functional / Technical / Security-Compliance / Commercial / Delivery-PM / Administrative), Mandatory vs Desirable (per RFP wording), and Evaluation weight if the RFP states scoring. Flag "hidden mandatories" — requirements phrased softly but located in pass/fail sections.
3. **Score compliance** per `references/compliance-scoring.md`: `C` Comply · `P` Partial · `N` Non-comply · `Q` Clarify. The rule: `C` requires evidence we can cite (project, certification, product feature, named capability in our catalog). No evidence → `P` or `Q`, never `C`. Each row gets an owner and the proposal section that will carry the response.
4. **Decision point — bid/no-bid.** Apply the gate in `references/compliance-scoring.md` §3: any `N` on a mandatory is a hard stop unless a clarification can convert it; compute `C` share on mandatories; check deadline feasibility against the response effort (count of sections × owners available). Output `BID / BID-WITH-CONDITIONS / NO-BID` with the three facts that drove it. Do not soften a NO-BID.
5. **Draft clarification questions** for every `Q`, ambiguous mandatory, and scoring-rule gap. Use the question format in `references/compliance-scoring.md` §4: neutral wording, no capability reveal, one question per item, reference the clause ID. Group by theme; cap at the count the RFP allows.
6. **Build the gaps-and-risks list**: every `P` and `N` with the mitigation (partner, roadmap commitment, alternative approach, exception request) and the risk if unmitigated.
7. **Assemble the matrix** on `assets/compliance-matrix-columns.md` (column spec) — export as CSV/XLSX for the response team, plus a Markdown summary for the bid review. Totals by category and by compliance level must reconcile with the inventory count.
8. Run the self-check.

## Output
| Artifact | File | Notes |
|---|---|---|
| Requirement inventory | `rfp-<client>-requirements.csv` | Script output, reviewed |
| Compliance matrix | `rfp-<client>-compliance-matrix.csv` (or `.xlsx` if openpyxl available) | Columns per `assets/compliance-matrix-columns.md` |
| Bid review summary | `rfp-<client>-bid-review.md` | Bottom line (BID call) · Totals table · Mandatory non-compliances · Gaps and risks · Clarification questions · Response plan (section, owner, due) · Administrative checklist |

## Self-check
- [ ] Inventory count = matrix row count; totals by category reconcile
- [ ] No `C` without a cited evidence item
- [ ] Every mandatory `N` or `P` appears in gaps-and-risks with a mitigation and owner
- [ ] Clarification questions reference clause IDs and reveal no capability gaps
- [ ] Bid/no-bid call on line 1 of the summary with its three drivers
- [ ] Deadlines (Q&A, submission) stated with source page
- [ ] No other-client names or internal rate information in any artifact that could ship

## References
- `references/requirement-taxonomy.md` — categories, mandatory detection, hidden-mandatory patterns, evaluation weighting
- `references/compliance-scoring.md` — C/P/N/Q rules, evidence standard, bid/no-bid gate, clarification-question format
- `assets/compliance-matrix-columns.md` — column specification for CSV/XLSX
- `scripts/extract_requirements.py` — .txt/.md/.docx/.pdf → requirements CSV

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py presales/rfp-compliance-matrix --input <name>=<value> … --out <dir>` (see `--explain presales/rfp-compliance-matrix`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.

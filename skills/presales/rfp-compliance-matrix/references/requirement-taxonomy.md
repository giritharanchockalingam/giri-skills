# Requirement Taxonomy

## 1. Categories
| Category | Code | Contains | Typical response owner |
|---|---|---|---|
| Functional | FUN | What the solution must do for users and the business | Solution architect |
| Technical | TEC | Architecture, platforms, integration, performance, data, environments | Technical architect |
| Security & Compliance | SEC | Certifications (SOC 2, ISO 27001, PCI, HIPAA, FERPA, GDPR), data residency, access control, audit | CISO delegate / compliance |
| Commercial | COM | Pricing structure, payment terms, liability, insurance, IP, warranties, SLAs with credits | Commercial / legal |
| Delivery & PM | DEL | Methodology, timeline, team, governance, reporting, transition, training | Delivery lead |
| Administrative | ADM | Submission format, page limits, forms, signatures, references, deadlines | Bid manager |

Administrative items are tracked, not scored for compliance; they are pass/fail on submission.

## 2. Mandatory vs desirable detection
| Wording | Treat as |
|---|---|
| shall, must, is required to, will provide, mandatory, minimum requirement | Mandatory (M) |
| should, is expected to, preferred, desirable, where possible, would be advantageous | Desirable (D) |
| may, could, optional, nice to have | Optional (O) |
| Located in a section titled "Pass/Fail", "Minimum qualifications", "Mandatory criteria", "Gate" | Mandatory regardless of wording |

Hidden mandatories — check explicitly:
- Qualification thresholds in the introduction ("bidders must have delivered three comparable programs")
- Insurance, bonding, and financial-standing tests in the commercial section
- Certifications named in an appendix form rather than the body
- Reference-customer counts and recency requirements
- Local-presence, language, or working-hours requirements
- Data-residency or sovereign-cloud statements buried in security annexes
- Acceptance of terms and conditions "without exception" (an N here is a hard stop)

## 3. Evaluation weighting
If the RFP publishes scoring, record it against each requirement or section:
| Field | Rule |
|---|---|
| Weight | Points or percentage as stated; sum must equal the stated total |
| Scoring method | Pass/fail · scored 0–5 · lowest price · best value — record verbatim |
| Price weight | Note separately; drives how aggressive the estimate must be |

If the RFP does not publish scoring, do not invent weights. Record `[TO BE BASELINED — owner: ___]` and add a clarification question asking for the evaluation criteria and relative weights.

## 4. Requirement quality flags
| Flag | Meaning | Action |
|---|---|---|
| AMB | Ambiguous: could be read two ways | Clarification question |
| DUP | Duplicate or overlapping with another ID | Cross-reference; respond once, point both |
| CON | Conflicts with another requirement or with terms | Clarification question; note risk |
| UNQ | Unquantified ("high performance", "scalable") | Ask for the number or propose one in the response as an assumption |
| OOS | Likely out of our scope / needs a partner | Gaps list; partner decision |
| INC | Incumbent-shaped (specifies the incumbent's product or process) | Competitive flag; see competitive-positioning |

## 5. Inventory record
| Field | Description |
|---|---|
| REQ-ID | Our sequential ID (REQ-001 …) |
| Client ID | The RFP's own clause number, verbatim |
| Section | RFP section heading |
| Page | Page or location |
| Text | Verbatim requirement text (do not paraphrase) |
| Category | FUN / TEC / SEC / COM / DEL / ADM |
| M/D/O | Mandatory / Desirable / Optional |
| Weight | Stated score or `[TO BE BASELINED — owner: ___]` |
| Flags | AMB / DUP / CON / UNQ / OOS / INC |

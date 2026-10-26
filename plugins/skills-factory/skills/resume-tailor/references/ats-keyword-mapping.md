# ATS Keyword Mapping Method

## Step 1 — Extract JD keywords
| Type | How to spot | Example |
|---|---|---|
| Hard skills / platforms | Proper nouns, acronyms, product names | Apigee, SAP S/4HANA, ServiceNow, Snowflake |
| Competencies | Verb + object phrases in responsibilities | "manage vendor contracts", "own technology roadmap" |
| Scope markers | Numbers and scale words | "$30M budget", "team of 80", "multi-region" |
| Credentials | Degree, certification, clearance | MBA, PMP, TOGAF, CISSP |
| Title words | Exact title and adjacent titles | "Senior Director, Enterprise Applications" |

Rank by frequency × placement (title > requirements > responsibilities > about-us).

## Step 2 — Map to master résumé evidence
| Status | Rule |
|---|---|
| EXACT | Keyword string appears in the master résumé |
| SYNONYM | Master résumé states the same fact under a different name (e.g., JD "API management platform", MR "Apigee"). Use the JD term **and** keep the MR term in parentheses once |
| ADJACENT | Related but not the same (JD "Boomi", MR "MuleSoft"). Do not claim the JD term; state the MR term and the category ("iPaaS") |
| UNSUPPORTED | No evidence. Goes to the gap note only |

Synonym substitution requires the underlying fact to be true in the MR. "Led" ≠ "supported". "Architected" ≠ "implemented".

## Step 3 — Placement
| Placement | What goes there | Limit |
|---|---|---|
| Title line | Exact JD title if the MR history supports that level | 1 |
| Executive summary | Top 5–7 keywords, in prose | ≤4 lines |
| Core competencies | 9–12 keyword phrases, pipe- or comma-separated (ATS-safe) | 2 lines |
| Experience bullets | Keywords inside outcome bullets | natural density |
| Skills / Technology | Platforms and tools | 3–5 lines |

## Density rules
- Each top-10 keyword appears 2–3 times across the document; never more than 4.
- No keyword stuffing lines ("Keywords: …"), no white text, no hidden sections.
- Use the exact JD spelling for the first occurrence (e.g., "Generative AI" not "GenAI") if the MR fact supports it.

## ATS formatting rules
- Standard headings: Summary, Core Competencies, Professional Experience, Education, Certifications.
- One column, no tables, no text boxes, no headers/footers for contact info.
- Dates: `Jan 2021 – Jun 2024`. Employer, title, location on separate lines or a single line with `|`.
- File name: `Firstname-Lastname-Senior-Director-Role.docx/pdf`.

## Output table format
| JD keyword | Priority | Status | Evidence | Placement |
|---|---|---|---|---|
| Apigee | 1 | EXACT | MR-L22 | Summary, bullet, skills |
| Vendor management | 2 | SYNONYM (SOW negotiation) | MR-L31 | Competencies, bullet |
| Boomi | 3 | ADJACENT (MuleSoft) | MR-L22 | Gap note |
| SOX compliance | 4 | UNSUPPORTED | — | Gap note |

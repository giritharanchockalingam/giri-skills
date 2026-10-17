# Before / After Diff and Traceability Formats

## Before / after diff
One block per changed unit (summary, scope line, bullet). Unchanged units are listed once under "KEEP" by MR line.

```
### <Role or section>
[SHARPEN] MR-L18
- BEFORE: Managed the integration team and delivered APIs for multiple business units.
- AFTER:  Directed a 12-person integration team delivering 240+ APIs on MuleSoft for 6 business units, cutting partner onboarding from 6 weeks to 9 days. [MR-L18, MR-L19]
- WHY:    JD must-have "API program leadership"; metric moved forward.

[CUT] MR-L27 — pre-2010 technical detail, no JD relevance
[REORDER] MR-L22 → position 1 — JD title keyword
[KEEP] MR-L20, MR-L21, MR-L24
```

Tags follow the repo redline convention: `[KEEP] [SHARPEN] [CUT] [ADD] [TBD]`. `[ADD]` is permitted only for structural elements (headings, competency section) — never for facts.

## Traceability table (mandatory)
| # | Tailored text (first 60 chars) | Source | Transformation | Metric unchanged? |
|---|---|---|---|---|
| 1 | Directed a 12-person integration team delivering 240+ APIs… | MR-L18, MR-L19 | MERGE + REWORD | Yes |
| 2 | Negotiated iPaaS renewal, cutting run-rate $1.1M/yr… | MR-L31 | EMPHASIZE | Yes |

Rules:
- One row per bullet and per summary sentence.
- "Metric unchanged?" must be Yes. "No" or "N/A (no metric in source)" only.
- A row with Source empty or "NEW" fails the self-check.

## Unsupported-claims note
| JD wants | Why not included | Option |
|---|---|---|
| SOX audit ownership | Not in MR | Add to MR if true (user confirms), else omit |
| Boomi | MR shows MuleSoft | State "iPaaS (MuleSoft)"; address Boomi in interview |

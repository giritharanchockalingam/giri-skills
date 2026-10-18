# Compliance Matrix — Column Specification

Use this exact column order for the CSV/XLSX. Columns 1–9 come from the extraction and taxonomy pass; 10–17 from scoring. Freeze header row; filter on every column.

| # | Column | Type | Allowed values / format | Filled by |
|---|---|---|---|---|
| 1 | `req_id` | text | `REQ-001` … sequential, never reused | script |
| 2 | `client_id` | text | RFP clause number verbatim (e.g., `4.3.2`, `R-014`, `(b)(ii)`) | script |
| 3 | `section` | text | RFP section heading | script |
| 4 | `page` | int/text | Page number or location label | script |
| 5 | `text` | text | Verbatim requirement; no paraphrase | script, reviewed |
| 6 | `category` | enum | `FUN` `TEC` `SEC` `COM` `DEL` `ADM` | analyst |
| 7 | `mdo` | enum | `M` `D` `O` | analyst (per taxonomy §2) |
| 8 | `weight` | text | Stated score/percent or `[TO BE BASELINED — owner: <role>]` | analyst |
| 9 | `flags` | text | Semicolon list from `AMB DUP CON UNQ OOS INC` | analyst |
| 10 | `compliance` | enum | `C` `P` `N` `Q` | owner, reviewed |
| 11 | `evidence` | text | Catalog ref / cert (expiry) / project ref ID / product feature. Required when `C` | owner |
| 12 | `gap_condition` | text | Required when `P` or `N` | owner |
| 13 | `mitigation` | enum+text | `partner` `roadmap` `custom-build` `exception` `alternative` + note | owner |
| 14 | `owner` | text | Named person | bid manager |
| 15 | `response_section` | text | Proposal section number | bid manager |
| 16 | `status` | enum | `not-started` `drafted` `reviewed` `final` | owner |
| 17 | `clarification_id` | text | `CQ-nnn` when `compliance = Q` or flag `AMB`/`CON`/`UNQ` | analyst |

## Validation rules (apply before bid review)
| Rule | Check |
|---|---|
| Completeness | Row count = inventory count |
| Evidence | `compliance = C` ⇒ `evidence` non-empty |
| Gaps | `compliance ∈ {P, N}` ⇒ `gap_condition` and `mitigation` non-empty |
| Clarify | `compliance = Q` ⇒ `clarification_id` non-empty |
| Mandatory N | `mdo = M` and `compliance = N` ⇒ appears in bid review §3 |
| Owner | Every row with `mdo ∈ {M, D}` has an `owner` |

## Summary pivots for the bid review
- Category × Compliance (count)
- Mandatory only: Compliance (count and %)
- Owner × Status (count) — response progress
- Flags (count) — quality of the RFP itself

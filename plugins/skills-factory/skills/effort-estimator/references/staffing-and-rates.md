# Staffing and Rates

## 1. Pyramid design
| Layer | Roles | Typical share of effort (delivery engagements) | Notes |
|---|---|---|---|
| Lead | Engagement manager, lead architect | 10–15% | Part-time EM below ~2,000 person-days |
| Senior | Technical leads, senior developers, test lead, business analyst | 25–35% | One tech lead per 4–6 developers |
| Core | Developers, integration engineers, test engineers | 45–60% | Largest layer; offshore-heavy where policy allows |
| Support | DevOps, data, PMO, documentation | 5–10% | Often shared across engagements |

Shares are design targets, not a basis for estimating effort. Effort comes from the WBS; the pyramid allocates it.

Leverage ratio = (senior + core + support effort) ÷ lead effort. Record it; compare with the user's own norms if provided. Do not assert a "standard" ratio.

## 2. Onshore / offshore mix
| Factor | Pushes onshore | Pushes offshore |
|---|---|---|
| Client-facing work (workshops, design, stakeholder management) | ↑ | |
| Data residency / security restrictions | ↑ | |
| Overlap requirement with client time zone | ↑ | partial (shifted hours) |
| Well-specified build and test work | | ↑ |
| Run / support with follow-the-sun | | ↑ |
| Price-to-win pressure | | ↑ |
| First engagement with client (trust) | ↑ initially | ↑ after wave 1 |

Rules:
- State the mix by phase, not one number. Design phases run onshore-heavy; build and test offshore-heavy; cutover mixed.
- Each offshore team needs a named onshore counterpart for escalation.
- Overlap hours per day with the client are an assumption row.
- The mix is a lever against price-to-win; moving it changes risk, which goes in the risk register.

## 3. Allocation rules
| Rule | Value |
|---|---|
| Max allocation | 100% (reality: ~80% productive) |
| Min useful allocation | 20% (below that, context-switching dominates) |
| EM allocation | 25–50% for mid-size; 100% above ~3,000 person-days |
| Architect allocation | High in design, tapering to 20–30% in build, up in cutover |
| Test lead | From design phase, not from test phase |
| Ramp | New joiners at 50% for two weeks |

## 4. Rate-card contract
The skill never invents rates. The rate card is supplied as CSV with this layout (see `assets/rate-card.example.csv`):

| Column | Meaning |
|---|---|
| `role` | Must match `role` values used in the WBS |
| `grade` | Optional; for pyramid reporting |
| `location` | `onshore` / `offshore` / `nearshore` / a named country |
| `cost_rate` | Internal daily cost (used for margin) |
| `bill_rate` | Daily rate charged (used for price) |
| `currency` | ISO code |
| `valid_until` | Date; the estimate notes rate validity |

Rates match on role AND location. A role priced at several locations needs the optional WBS `location` column (one task row per role and location); duplicate (role, location) rows and ambiguous matches stop the script (exit 2). Costs are never summed across currencies: a mixed-currency card needs `--currency <ISO>` and a sourced `--fx CUR=rate` per other currency, else exit 2 with FX `[TO BE BASELINED — owner: Finance lead]`. Expired or unreadable `valid_until` dates are flagged in the output. If `cost_rate` is absent, margin cannot be computed and the memo says so. If a WBS role has no rate-card match, the script lists it and excludes it from cost; fix the mapping rather than guessing.

## 5. Margin sanity
| Check | Rule |
|---|---|
| Gross margin | (price − cost) ÷ price, computed at P80 effort and at P50 effort; show both |
| Contingency placement | Contingency (P80 − P50) is a line, not a rate uplift |
| Price-to-win gap | If price > PTW by >15%, list levers: scope phasing, mix shift, automation assets, client-side responsibilities, duration change. Do not cut the estimate to fit |
| Discount | Any discount is applied to price and shown as a line; margin recalculated |
| Expenses | Travel estimated separately from stated trip counts; never folded into rates |

## 6. Staffing table layout
| Role | Location | Phase 1 (%) | Phase 2 (%) | Phase 3 (%) | … | Total person-days | Named? |
|---|---|---|---|---|---|---|---|

Followed by a phase × month heat table (FTE per month) to check feasibility against the team-size cap and hiring lead times.

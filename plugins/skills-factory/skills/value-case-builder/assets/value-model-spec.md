# Value Model — CSV Layout Specification

Three files. Every numeric cell has a `source`; an empty source means the cell holds `[TO BE BASELINED — owner: <role>]`.

## File 1: `benefits.csv` (one row per benefit lever)
| # | Column | Type | Notes |
|---|---|---|---|
| 1 | `benefit_id` | `B-nn` | |
| 2 | `driver` | text | Client-stated strategic driver (quote or ref) |
| 3 | `lever` | text | The change |
| 4 | `metric` | text | Operational metric |
| 5 | `class` | enum | `hard` · `soft` · `strategic` |
| 6 | `baseline_value` | number or marker | |
| 7 | `baseline_unit` | text | hours, incidents/qtr, currency/yr |
| 8 | `baseline_source` | text | doc + page, or role + date |
| 9 | `baseline_confidence` | `H`/`M`/`L` | |
| 10 | `target_low` / `target_base` / `target_high` | number | Absolute target values of the metric |
| 13 | `mechanism` | text | What produces the change |
| 14 | `enabling_milestone` | text | From plan |
| 15 | `conversion_rule` | text | e.g., "hours × loaded rate (source)" |
| 16 | `conversion_value` | number or marker | |
| 17 | `conversion_source` | text | |
| 18 | `ramp` | text | e.g., "25/50/100 over Q1–Q3 after milestone" |
| 19 | `owner_client` | role | Realization owner |
| 20 | `overlaps_with` | list | `B-nn` ids sharing a metric |
| 21 | `in_headline` | `Y`/`N` | N if any marker in baseline/conversion |

## File 2: `costs.csv` (one row per cost line per year)
| # | Column | Type |
|---|---|---|
| 1 | `cost_id` | `C-nn` |
| 2 | `category` | `delivery` · `licence` · `run` · `change_mgmt` · `dual_run` · `decommission` · `cost_of_delay` |
| 3 | `line` | text |
| 4 | `year` | 0–5 |
| 5 | `amount` | number or marker |
| 6 | `currency` | ISO |
| 7 | `source` | text (estimate memo version, TCO file, contract) |
| 8 | `confidence` | H/M/L |
| 9 | `timing_rule` | text |

## File 3: `assumptions.csv`
| # | Column |
|---|---|
| 1 | `assumption_id` (`VC-A-nn`) |
| 2 | `statement` |
| 3 | `value` |
| 4 | `source` |
| 5 | `owner_to_confirm` |
| 6 | `sensitivity` (H/M/L) |
| 7 | `break_even_value` (computed; marker if inputs unbaselined) |

Mandatory rows: horizon; discounting (none / rate + source); currency; FY; decommission date; loaded cost per hour (if any soft benefit); adoption assumption; delivery cost confidence level (P50/P80).

## Derived (computed, not stored)
| Output | Rule |
|---|---|
| Benefit by year | Σ over `in_headline = Y` benefits: (target_base − baseline) × conversion × ramp(year) |
| Cost by year | Σ costs by year |
| Net by year | benefit − cost |
| Cumulative net; payback month | first period cumulative ≥ 0 |
| 3-yr / 5-yr net | Σ |
| NPV | only if discount rate sourced |
| Sensitivity | top-3 assumptions ±20% → 3-yr net; break-even |
| Marker propagation | any derived value depending on a marker is reported as `[TO BE BASELINED — owner: <role>]` |

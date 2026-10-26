# TCO / ROI Model — CSV Layout Specification

Two CSV files. Every `amount` cell carries a `source` cell; an empty source is invalid — write `[TO BE BASELINED — owner: <role>]` in `amount` instead.

## File 1: `tco-lines.csv` (one row per cost line per scenario per year)
| # | Column | Type | Allowed values / format |
|---|---|---|---|
| 1 | `scenario` | enum | `current` (stay) · `target` (migrate) |
| 2 | `category` | enum | `licence` · `infrastructure` · `run_team` · `support_contract` · `incident_cost` · `migration_one_time` · `dual_run` · `training` · `decommission` · `other` |
| 3 | `line` | text | Specific item (e.g., "Core licence — 4 vCores", "L2 support team — 3 FTE") |
| 4 | `year` | int | 0 (one-time, at start) … 5 |
| 5 | `amount` | number or marker | Currency amount or `[TO BE BASELINED — owner: <role>]` |
| 6 | `currency` | text | ISO code |
| 7 | `source` | text | Document + page/section, or the client role who stated it, or `estimate-memo vX` |
| 8 | `basis` | enum | `contract` · `invoice` · `budget` · `estimate` · `assumption` |
| 9 | `confidence` | enum | `H` · `M` · `L` |
| 10 | `timing_rule` | text | e.g., "starts after decommission date D", "ends at contract end 2027-06-30" |
| 11 | `notes` | text | — |

Rules:
- Licence and infrastructure savings in `target` appear only from the year after the decommission date; until then, `dual_run` lines carry both.
- `migration_one_time` amounts come from `effort-estimator` output (P80 unless stated) and cite the memo version.
- Vendor list prices are never used from memory; only client contracts, quotes, or marked.

## File 2: `tco-assumptions.csv`
| # | Column | Type |
|---|---|---|
| 1 | `assumption_id` | `TCO-A-nn` |
| 2 | `statement` | text |
| 3 | `value` | number/text or marker |
| 4 | `source` | text |
| 5 | `owner_to_confirm` | role |
| 6 | `sensitivity` | `H` / `M` / `L` (effect on NPV if ±20%) |
| 7 | `used_by_lines` | semicolon list of `line` values |

Mandatory assumption rows: decommission date; discount rate (if NPV used; else "undiscounted"); contract end dates; growth in interface count; run-team cost per FTE (client-provided); migration cost source and confidence level; inflation/uplift; currency.

## Derived outputs (computed, not stored as inputs)
| Output | Formula |
|---|---|
| Annual run-rate by scenario | Σ amounts by scenario, year (excluding one-time) |
| Cumulative cost by scenario | Running Σ across years incl. one-time |
| Net benefit by year | current − target |
| Payback | First year where cumulative net benefit ≥ 0 |
| 3-year / 5-year net | Σ net benefit through year 3 / 5 |
| NPV (optional) | Σ net benefit ÷ (1 + r)^year, r from assumptions |
| Sensitivity | Recompute 3-year net with the two highest-sensitivity assumptions at ±20% |

Any derived output computed from a line marked `[TO BE BASELINED]` is itself reported as `[TO BE BASELINED — owner: <role>]`, not as a number.

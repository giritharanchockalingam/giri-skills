# Readiness dimensions

Each dimension is scored only when its threshold is in the owner's requirements file. Otherwise it is `TBD` with the marker `[TO BE BASELINED — owner: Data owner]`. A TBD dimension is never treated as a pass.

| Dimension | Requirement key(s) | Observed value | Pass when | Fail owner |
|---|---|---|---|---|
| volume | `min_rows` | data rows (blank lines skipped) | rows ≥ min_rows | Data owner |
| completeness | `max_null_pct` | worst column null % | every column's null % ≤ max_null_pct | Data steward |
| schema | `required_columns` | count of required columns present | all present | Data engineer |
| uniqueness | `unique_key` | duplicate key rows = rows with a non-null key − distinct keys | 0 duplicates and 0 rows with any null key part | Data steward |
| duplicates | `max_duplicate_rows` | rows − distinct rows (cells trimmed) | ≤ max_duplicate_rows | Data steward |
| freshness | `date_column`, `max_age_days` + `as_of` input | age = as_of − newest parseable date (days) | age ≤ max_age_days | Data engineer |

## Verdict
- Any **fail** → **Not ready** (script exit 1).
- No fail, any **TBD** → **Ready-with-gaps** (exit 0) — usable for exploration, not for a go decision.
- All pass → **Ready** (exit 0).

## Rules
- **Null**: empty cell, or `NA`, `N/A`, `NULL`, `None`, `NaN`, `nil` (case-insensitive, trimmed).
- **Null %** = nulls ÷ rows × 100, rounded to 2 decimals.
- **Inferred type**: the narrowest of integer → float → boolean → date → datetime → string that *every* non-null value satisfies. A single stray value makes the column `string`; treat that as a finding.
- **Dates**: ISO 8601 only (`YYYY-MM-DD`, optionally `THH:MM[:SS][Z|±HH:MM]`). Unparseable values in `date_column` are counted in `unparseable_dates`; future-dated rows (after as_of) are counted in `future_dated_rows`.
- **Composite keys**: `unique_key` accepts `a;b`; a row is a duplicate when the full tuple repeats.

# Rules, denominators and limits

| Rule | Fires when | failing_rows | failing_rate denominator |
|---|---|---|---|
| missing_column | contract column absent from the data | all rows | all rows |
| extra_column | data column absent from the contract (always `warn`, owner TBD Data owner) | all rows | all rows |
| ragged_row | a row has more or fewer fields than the header (`error`) | ragged rows | all rows |
| type | non-null value does not parse as the contract type | failing values | non-null values |
| required | `required=yes` and any null | null rows | all rows |
| null_rate | null rows ÷ rows > `max_null_rate` | null rows | all rows |
| unique | `unique=yes` and repeated values | rows beyond the first occurrence | non-null values |
| min / max | value (or text length) outside the bound | failing values | non-null values |
| allowed | value not in the pipe-separated list (exact, case-sensitive) | failing values | non-null values |
| regex | value does not full-match the regex | failing values | non-null values |
| freshness | newest date in the freshness column older than as-of − max_age_days | all rows | all rows |

Type parsing: integer `^[+-]?\d+$`; number decimal or exponent, finite; boolean true/false/yes/no/y/n/t/f/1/0; date `YYYY-MM-DD` (real calendar date); datetime ISO 8601 `YYYY-MM-DD[T ]HH:MM[:SS[.f]]` with optional `Z` or offset (compared in UTC); email `local@domain.tld`. Values that fail the type rule are excluded from min/max (they are already reported).

Freshness is evaluated only when `freshness_column`, `as_of` and `max_age_days` are all supplied. A column with no as-of date or maximum age reads `not checked … [TO BE BASELINED — owner: Data owner]`; the script never uses today's date.

Sensitive data: violations carry at most 3 distinct example values, each cut to 40 characters; profile min/max are shown only for numeric and date-like columns. Run `pii-data-inventory` first if the extract may hold personal data, and treat `violations.csv` as no more public than the data.

Limits: one CSV extract per run; no cross-column, referential or distribution-drift rules; results describe the extract, not the full table.

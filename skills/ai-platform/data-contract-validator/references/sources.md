# Sources (checked 2026-10-18)

| Id | Source | Used for |
|---|---|---|
| S1 | Bitol, Open Data Contract Standard (ODCS), overview — https://bitol-io.github.io/open-data-contract-standard/latest/ (current version shown: v3.2.0) | Which standard the YAML subset follows |
| S2 | ODCS, Schema section — https://bitol-io.github.io/open-data-contract-standard/latest/schema/ | `logicalType` values (string, date, timestamp, time, number, integer, object, array, boolean, map, vector); `logicalTypeOptions` (string: format, minLength, maxLength, pattern; integer/number: minimum, maximum; date: format, minimum, maximum); `required`, `unique`; `enum` |
| S3 | ODCS, Data Quality section — https://bitol-io.github.io/open-data-contract-standard/latest/data-quality/ | Library metrics `nullValues`, `missingValues`, `invalidValues` (arguments `validValues` or `pattern`), `duplicateValues`, `rowCount`; operators `mustBe`, `mustBeLessOrEqualTo`, …; `unit: rows|percent` (rows is the default) |
| S4 | datacontract-cli documentation, "Define your Schema" — https://docs.datacontract.com/docs/schema.md | Cross-check: `primaryKey: true` implies not-null and unique; `logicalTypeOptions.enum` example |

Only field names and short paraphrases are recorded here; the standard's text is not reproduced. Re-check S2/S3 when ODCS publishes a new minor version.

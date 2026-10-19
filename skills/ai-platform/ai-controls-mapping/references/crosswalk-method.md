# Coverage and crosswalk method

## Coverage
| Item | Rule |
|---|---|
| Statuses | `implemented`, `partial`, `planned`, `not_applicable` (from the input). A subcategory absent from the input is `missing`. |
| Applicable | total − not_applicable |
| Coverage | (implemented + 0.5 × partial) ÷ applicable, rounded to 3 decimals. `n/a` when nothing is applicable. |
| Gate | Overall coverage < `min_coverage` → exit 1, with full outputs. |
| Gap | partial, planned or missing. A blank owner becomes `[TO BE BASELINED — owner: AI risk lead]`. |
| Flags | implemented or partial with no evidence cited; not_applicable with no justification. Flagged, not downgraded. |
| Input errors | Ids not in the 72-id catalogue are listed as `ERROR` rows in controls.csv, excluded from coverage, and fail the run (exit 1). A duplicate id or a bad status is invalid input (exit 2). |

## Crosswalk (skill's own mapping)
- **Scope:** links each `eu-ai-act-classifier` obligation id to 1-3 NIST AI RMF subcategories whose stated outcome would produce evidence for that obligation. A trailing `*` matches an id prefix (`TR-50-*`).
- **Conservative by design:** a mapping shows that evidence is *relevant*, not that the obligation is met. `supported` requires every mapped subcategory to be implemented (or not applicable). `partial` means some evidence exists. `none` means only planned or missing.
- **Not authoritative:** neither NIST nor the EU publishes a subcategory-level crosswalk to the final AI Act (sources.md S4). Counsel and the AI compliance lead own the final judgement.
- **Closed obligations** (`done`, `not_applicable`) are skipped. An obligation id with no crosswalk row is reported as `no crosswalk entry`.

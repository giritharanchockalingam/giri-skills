# ODCS v3 YAML subset (what `--contract *.yaml` understands)

The YAML contract is parsed with the repo's YAML subset parser (`scripts/skillmeta.py`) after two clean-ups: block-scalar bodies (`key: |`, `key: >`) are dropped and inline `# comments` outside quotes are removed. Anchors, aliases and tags exit 2. Field names follow ODCS v3 ([S2], [S3] in `sources.md`).

## Mapping
| ODCS | Contract rule |
|---|---|
| `schema:` with exactly one object | the dataset (several objects exit 2 — one dataset per run) |
| `properties[].name` | `column` |
| `logicalType` string / integer / number / boolean / date / timestamp | `type` string / integer / number / boolean / date / datetime |
| `logicalType` time, object, array, map, vector | exit 2 (not checkable in a flat CSV) |
| `logicalTypeOptions.format: email` on a string | `type: email` |
| `logicalTypeOptions.pattern` | `regex` (full match) |
| `logicalTypeOptions.minimum` / `maximum` (numbers, dates) | `min` / `max` |
| `logicalTypeOptions.minLength` / `maxLength` (strings) | `min` / `max` (character length) |
| `enum` (property or `logicalTypeOptions`) | `allowed` (string becomes `enum`) |
| `required: true` | `required: yes` |
| `unique: true` | `unique: yes` |
| `primaryKey: true` | `required: yes` and `unique: yes` |
| quality `invalidValues` + `arguments.validValues` + `mustBe: 0` | `allowed` |
| quality `invalidValues` + `arguments.pattern` + `mustBe: 0` | `regex` |
| quality `duplicateValues` + `mustBe: 0` | `unique: yes` |
| quality `nullValues` + `unit: percent` + `mustBeLessOrEqualTo: N` | `max_null_rate = N / 100` |
| quality `severity` | `severity` (error / warn; blank = error) |

## Not evaluated (listed in the report under "Contract terms not evaluated")
Any other quality metric or operator (e.g. `missingValues`, `rowCount`, `mustBeBetween`, `unit: rows` thresholds above 0, SQL or custom rules), `exclusiveMinimum`/`exclusiveMaximum`, `multipleOf`, `physicalType`. ODCS has no per-property owner, so every YAML rule's owner is `[TO BE BASELINED — owner: Data owner]`; use the CSV layout to name owners.

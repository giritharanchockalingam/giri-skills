# Lint Rules

Error findings block rendering and exit 1. Warnings are reported and must be reviewed.

| Code | Severity | Rule | Fix |
|---|---|---|---|
| E-SPEC-TYPE | error | spec is not a JSON object | wrap fields in `{}` |
| E-SPEC-FIELD | error | a required field is missing or has the wrong type | add it per `spec-format.md` |
| E-ID | error | id is not a lowercase slug | rename |
| E-VERSION | error | version is not semver | use `MAJOR.MINOR.PATCH` |
| E-ROLE / E-TASK | error | role or task is empty | write it |
| E-VAR-DECL | error | a variable lacks a name or a boolean `required` | complete the declaration |
| E-VAR-NAME | error | variable or placeholder is not an identifier | rename to `[A-Za-z_][A-Za-z0-9_]*` |
| E-VAR-DUP | error | a variable is declared twice | remove the duplicate |
| E-VAR-UNDECLARED | error | `{{name}}` in task with no declaration | declare it (with description) or remove it |
| E-VAR-UNUSED | error | declared variable never used in task | use it or remove the declaration |
| E-SCHEMA | error | the output schema is malformed (unknown type, bad `required`/`enum`) | correct the schema |
| E-EX-NONE | error | no examples, so no regression cases | add owner-approved examples |
| E-EX-SHAPE | error | example lacks `inputs` object or `output` | complete it |
| E-EX-MISSING-VAR | error | example omits a required variable | add the input |
| E-EX-SCHEMA | error | example output fails the schema (one finding per violation, with JSON path) | fix the example or the schema, deliberately |
| E-BUDGET | error | an example's rendered estimate exceeds `max_input_tokens` (or budget ≤ 0); the unfilled template's estimate is reported, not gated | shorten, move content to retrieval, or raise the budget with the owner |
| W-CONSTRAINTS | warning | no constraints declared | add testable rules |
| W-ROLE-VAR | warning | placeholders in role | move them into task |
| W-VAR-DESC | warning | variable without description | describe source and format |
| W-EX-UNKNOWN-VAR | warning | example input that is not a declared variable | remove or declare |
| W-SCHEMA | warning | schema keyword outside the subset, or `required` key without a property | accept knowingly or simplify |

## Why each rule exists
- **Variables both ways**: an undeclared placeholder reaches the model as literal `{{x}}`; an unused declaration means the caller sends data the model never sees.
- **Examples against the schema**: an example that violates the contract teaches the model to violate it and makes the regression case unpassable.
- **Budget**: the over-budget call is truncated or rejected in production; catching it at lint time is cheaper.

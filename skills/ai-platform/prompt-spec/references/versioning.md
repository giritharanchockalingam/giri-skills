# Versioning Prompts

Prompts are code: they change behaviour, so they are versioned, reviewed and regression-tested.

| Change | Bump | Why |
|---|---|---|
| Output schema: field removed/renamed, type or enum narrowed | MAJOR | callers parsing the output break |
| New required variable | MAJOR | callers must send new data |
| Role or constraint change; new optional variable; enum widened; new optional output field | MINOR | behaviour changes, contract still compatible |
| Wording fix in task, typo, example added | PATCH | no intended behaviour change |

## Traceability
- Each regression case id is `<id>@<version>#ex-NN`; an eval result therefore names the exact prompt version it ran against.
- `prompt.md` carries the first 12 hex characters of the spec's SHA-256; two renders with the same hash came from the same spec bytes.
- Keep the spec in the repo next to the code that calls it; release notes list the bump and the reason.

## Release gate (with llm-eval-harness)
1. Lint passes (this skill).
2. `prompt-tests.jsonl` cases run against the target model; every `json_valid`, `json_schema` and `equals` assertion is scored.
3. Pass rate is compared with the previous version's baseline; a drop beyond the owner's tolerance blocks the release. The tolerance is the owner's decision, recorded in the harness config.

# Prompt Spec Format

One JSON file per prompt. It is the source of truth: `prompt.md` and `prompt-tests.jsonl` are generated from it and never hand-edited.

| Field | Type | Rule |
|---|---|---|
| `id` | string | lowercase slug `[a-z0-9._-]`; stable for the life of the prompt |
| `version` | string | semver `MAJOR.MINOR.PATCH` (see `versioning.md`) |
| `role` | string | stable system instructions; no `{{variables}}` (they are not filled per request) |
| `task` | string | per-request user template; every placeholder is `{{name}}` |
| `variables` | list | `{name, description, required}`; `name` is an identifier; `required` is a boolean |
| `output_schema` | object | JSON Schema subset below; the model is told to answer with JSON matching it |
| `constraints` | list of strings | one testable rule each; rendered under "Constraints:" in the system prompt |
| `examples` | list | `{inputs: {name: value}, output: <JSON>}`; owner-approved; each becomes a regression case |
| `max_input_tokens` | integer | owner's input budget for one call; the skill never chooses it |

Other top-level keys (e.g. `_fixture`, `owner`, `notes`) are ignored by the linter.

## Rendering
- **System** = `role` + constraints + "Respond with JSON only, matching this schema:" + the schema (compact JSON).
- **User** = `task` with placeholders filled from an example's inputs; an optional variable that is not supplied renders as empty.
- Non-string input values are inserted as JSON.

## Supported JSON Schema subset
| Keyword | Behaviour |
|---|---|
| `type` | `object`, `array`, `string`, `number`, `integer`, `boolean`, `null`, or a list of these |
| `properties` | validated for keys present in the value |
| `required` | listed keys must be present |
| `enum` | value must equal one listed value |
| `items` | every array element validated against one schema |
| `description`, `title` | accepted, not validated |

Any other keyword (`minLength`, `pattern`, `additionalProperties`, `$ref`, …) produces a warning and is ignored: the validator never claims to check what it does not check.

## Token estimate
`ceil(characters / 4)` of the rendered system + user text. It is a rough heuristic for English text, labelled "estimate" everywhere it appears; use the target model's tokenizer for a release decision near the limit.

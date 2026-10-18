# Skills Factory — consumer API (v1)

Applications invoke **published** skill versions through `/api/v1`. Drafts, in-review, approved-but-unpublished, superseded and retired versions are never reachable here. The same validation, policy limits and audit apply as in the UI.

Base URL: your deployment, e.g. `https://<project>.vercel.app`. All responses are JSON. Trailing slashes are accepted.

## Authentication

Create a key in **Administration → API keys** (admin role). The key is shown once; only its SHA-256 is stored. Send it as a bearer token:

```
Authorization: Bearer sf_live_…
```

| Status | `error.code` | Meaning |
|---|---|---|
| 401 | `unauthenticated` | No bearer token |
| 401 | `invalid_key` | Not a factory key, unknown, or revoked |
| 503 | `not_configured` | Server is missing `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` |

A key is scoped to one workspace. Every request re-verifies the hash in the database (`sf_resolve_api_key`, `SECURITY DEFINER`; the anon role has no table access).

## Endpoints

### `GET /api/v1/skills` — discover published skills

```bash
curl -s https://<host>/api/v1/skills -H "Authorization: Bearer $SF_KEY"
```

```json
{ "skills": [ { "slug": "effort-estimator", "name": "effort-estimator", "purpose": "…", "intended_users": "…", "usage_guidance": "…",
                "version": 1, "version_id": "…", "published_at": "…", "manifest_hash": "…", "inputs": [ … ], "outputs": [ … ] } ] }
```

### `GET /api/v1/skills/{slug}` — read the contract

Returns the published version's full manifest (`inputs`, `outputs`, `run`, `limits`, `model_config`, `release_criteria`, `compat`, …). Manifests never contain secrets.

```bash
curl -s https://<host>/api/v1/skills/effort-estimator -H "Authorization: Bearer $SF_KEY"
```

404 `not_published` when the slug has no published version visible to the key.

### `POST /api/v1/skills/{slug}/run` — invoke the published version

Body: `{"inputs": {...}, "assumptions": {...}}`.

* `inputs` — `name → value` per the manifest's `inputs`. File-typed inputs (`csv`, `json`, `md`, `txt`, `file`, `sql`) take the file **content** as a string (a `json` input may also be sent as a JSON object). `flag` inputs take `true`/`false`. `path` inputs are placed under the run folder automatically. `dir` inputs cannot be sent over HTTP.
* `assumptions` — optional `name → value` for required inputs you deliberately leave out; the run proceeds and labels every use `[ASSUMED]`.
* Header `Idempotency-Key: <string>` (optional, ≤120 chars) — a repeat with the same key returns the first run (`"deduplicated": true`) instead of running again.

Validation happens **before** anything executes:

| Status | `error.code` | Meaning |
|---|---|---|
| 400 | `invalid_inputs` | `details` lists `{path, message}` problems (unknown input, bad JSON, schema violation, CSV without header, …) |
| 400 | `missing_inputs` | `details.missing` names required inputs without a value or assumption |
| 409 | `not_published` | No published version |
| 409 | `rejected` | Workspace policy rejected the run (reason in `message`) |
| 429 | `rejected` | Concurrency limit or monthly budget reached |

Execution is synchronous within the version's deadline (`limits.timeout_s`, ≤ 55 s). The output contract is validated **after** the run: a missing or schema-invalid declared output makes the run `failed`, never `succeeded`.

```bash
curl -s https://<host>/api/v1/skills/effort-estimator/run \
  -H "Authorization: Bearer $SF_KEY" -H "Content-Type: application/json" -H "Idempotency-Key: order-4711" \
  -d @- <<'JSON'
{ "inputs": { "wbs": "task,phase,...\n...", "rates": "role,location,...\n...", "client": "Acme" } }
JSON
```

Response (`200`, or `202` when the run hit its deadline and is recorded as `timeout`):

```json
{ "run_id": "…", "status": "succeeded | failed | needs_input | timeout",
  "skill": "effort-estimator", "version": 1, "version_id": "…", "manifest_hash": "…",
  "error": null,
  "provider": { "requested": "anthropic", "used": "anthropic", "available": true, "note": "…" },
  "model": "claude-sonnet-4-5-20250929",
  "usage": { "input_tokens": 1200, "output_tokens": 300, "calls": 1, "retries": 0, "source": "provider-reported" },
  "cost": { "usd": 0.0081, "is_estimate": true, "basis": "provider-reported tokens × price table …" },
  "duration_ms": 4120,
  "outputs": [ { "path": "estimate.json", "bytes": 2048, "sha256": "…", "content_text": "{…}" } ],
  "checks": [ { "check": "exists", "pass": true, "evidence": "…", "path": "…" } ],
  "steps":  [ { "step": "model-json", "kind": "script", "ok": true, "exit": 0, "duration_s": 0.4 } ],
  "needs_input": null,
  "contract": { "ok": true, "problems": [] },
  "status_url": "https://<host>/api/v1/runs/<run_id>" }
```

`status` semantics: `succeeded` = every step ran, every output check passed and the output contract holds · `failed` = a step, check or the contract failed (see `error`, `steps`, `checks`, `contract`) · `needs_input` = a required input was missing (`needs_input.missing`) · `timeout` = the deadline was hit; no further steps ran.

When the server has no `ANTHROPIC_API_KEY`, `provider.used` is `"none"` with a note, llm steps are recorded as skipped and their checks fail — the run is `failed`, not faked.

### `GET /api/v1/runs/{id}` — status and result

```bash
curl -s https://<host>/api/v1/runs/<run_id> -H "Authorization: Bearer $SF_KEY"
```

Returns the stored run (same fields as above, plus `inputs_ref` — names, sizes and content hashes of what was sent; raw inputs are not stored; logs are not exposed through the API).

## Manifest format

The manifest is the versioned contract stored on every `sf_skill_versions` row and returned by `GET /api/v1/skills/{slug}`. It is the same shape the repository's `SKILL.md` `metadata.agent` block uses, so repository skills import unchanged and authored skills are rendered back into a `SKILL.md` for the runner.

```jsonc
{
  "manifest_version": 1,
  "purpose": "…", "intended_users": "…", "usage_guidance": "…",
  "inputs":  [ { "name": "wbs", "type": "csv", "required": true, "from": "…", "default": null, "flag": null, "schema": null } ],
  "outputs": [ { "path": "{out}/estimate.json", "checks": ["exists", "json"], "schema": null } ],
  "run":     [ { "step": "model-json", "kind": "script", "cmd": "python3 scripts/estimate.py {wbs} [--rates {rates}] --json", "stdout": "{out}/estimate.json" },
               { "step": "memo", "kind": "llm", "template": "assets/memo.md", "context": ["{out}/estimate.md"], "out": "{out}/memo.md" } ],
  "instructions_md": "# …",
  "resources": ["scripts/estimate.py", "assets/memo.md"],
  "allowed_tools": ["script", "llm"],
  "connections": ["anthropic"],
  "model_config": { "provider": "none | anthropic", "model": "claude-sonnet-4-5", "temperature": 0.2, "max_tokens": 4000 },
  "limits": { "timeout_s": 50, "max_retries": 0, "max_tokens": 8000, "max_cost_usd": null },
  "release_criteria": { "min_eval_pass_rate": 0.8, "require_approval": true },
  "compat": { "runner_version": "run_skill.py@inproc-1", "runtime_version": "vercel-python-3.12" }
}
```

* Input `type`: `csv json md txt file sql` (content), `dir` (not over HTTP), `path` (an output folder), `string`, `args` (shell-split), `flag`.
* Output `checks` vocabulary (deterministic, from `scripts/check_output.py`): `exists`, `json`, `yaml`, `csv:[a,b]`, `csv_rows:<col>!empty`, `csv_rows:<col>~<regex>`, `sections:["A","B"]`, `contains:"text"`, `max_lines:N`, `no_unowned_tbd`, `numbers_trace_to:<file>`, `cites_source_ids:<file>`, `mermaid_parses`, `cmd:"…"`. An output may also carry a JSON `schema` (subset: type, properties, required, items, enum, min/max, minLength/maxLength, pattern, additionalProperties).
* `limits.timeout_s` ≤ 55 (serverless ceiling); `max_retries` 0–2 applies to provider 429/5xx/network errors only.
* Validation rules are implemented in `lib/factory/manifest.ts` (`validateManifest`) and `lib/factory/schema.ts`; `manifest_hash` = SHA-256 of the canonical JSON (sorted keys, no whitespace).

## Evaluation cases (for completeness)

Cases live per version: `{name, inputs, checks, expected, notes}`. `checks` use the same vocabulary plus run-level `exit:N`, `needs_input:<name>` and `exists:<file>`, or `{"file": "<output>", "check": "<spec>"}`. A case passes only when every check passes; the evaluation `pass_rate` is cases passed ÷ cases, recorded with the case-set hash so later edits make it visibly outdated.

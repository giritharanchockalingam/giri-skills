# Port.io integration

Skills Factory plugs into a [Port](https://port.io) portal three ways. All three use the same governed skills: only **published** versions, with the same input validation, policy limits, content pinning and audit as the API and MCP server.

| | What Port users get | Built on |
|---|---|---|
| **1. MCP connector** | Port's AI agents call your skills as tools | Port's **Custom Server** MCP connector → `/api/mcp` (no code) |
| **2. Run skill action** | A **Run skill** button on every AI Skill entity; progress, result link and SUCCESS / FAILURE shown in Port | Port self-service action (WEBHOOK) → `/api/port/actions` (signed) |
| **3. AI Skill catalog** | An **AI Skill** blueprint: version, eval pass rate, approval, library status, inputs, link back | Port REST API: blueprint + entity upsert (**Integrations → Push skills to Port**) |

**Status (20 Oct 2026, live Port org, EU region):** verified live: access token, blueprint creation, a repeat push treating "blueprint exists" correctly, entity upsert with merge (23 of 23 skills), the AI Skill catalog page, the **Run governed skill** workflow, and two workflow runs end to end: a deliberately bad input refused with a readable reason in Port's log (`inputs.workload: CSV needs a header line with at least two columns`), and LLM cost model on its sample files **succeeded** (Port run `wfr_mWmOhBQBIui9vWw6` → Skills Factory run `98e4b04a…`). **MCP connector** "Skills Factory" published with all 25 tools (23 skills + `find_skill`, `get_run`), authenticated through the Port secret `SF_API_KEY`; Port AI called `find_skill` and correctly chose `llm-cost-model` v2, noting that `ai-finops-chargeback` matched but isn't published.

Port tips found live: the connector header is an object field (pencil → JSON editor); tool calls from Port AI need per-call approval unless "Auto approve" is chosen.

New Port orgs use **workflows** rather than classic self-service actions. Use the workflow JSON on the Integrations page; the classic action JSON is kept for older orgs.

## Setup

1. **Port credentials.** In Port, open **Settings → Credentials** and copy the Client ID and Client Secret.
2. **A workspace key for Port.** In Skills Factory, go to **Administration → API keys → Create** and name it `port`. Revoke it to cut Port off at any time.
3. **Vercel environment** (sensitive):

```bash
cd ~/giri-skills/studio
vercel env add PORT_CLIENT_ID production --sensitive
vercel env add PORT_CLIENT_SECRET production --sensitive
vercel env add PORT_SF_API_KEY production --sensitive      # the sf_live_ key from step 2
vercel env add PORT_API_URL production                     # only for US accounts: https://api.us.port.io
```

Then redeploy **the latest `main`**: Vercel → giri-skills-studio → Deployments → the newest `main` deployment → **⋯ → Redeploy**. Don't run `vercel --prod` from a laptop: it deploys whatever that checkout holds, which can be older than `main`, and it would replace production with it.

4. **Catalog.** In Skills Factory, go to **Integrations → Port → Push skills to Port**. This creates the `aiSkill` blueprint and one entity per published skill. Push again after publishing; it is idempotent.
5. **Run governed skill workflow.** In Skills Factory, create a workspace API key named `port-workflow`. In Port, go to **Settings → Secrets** and add it as `SF_API_KEY`. Then in **Workflows → + Workflow**, name it, open the JSON view, paste the workflow JSON from the Integrations page, and click **Apply changes**. (Older orgs: use the classic action JSON under **Self-service → + Action → Edit JSON**.)
6. **MCP connector.** In Port, go to **Settings → Data sources → + Connector → MCP Servers → Custom Server**:
   - URL: `https://<your portal>/api/mcp`
   - Header: `Authorization: Bearer {{ .secrets["SF_API_KEY"] }}`, with a workspace key stored as the Port secret `SF_API_KEY`
   - Allowed tools: the skills Port's agents may call

## Publish sync (WP1, 2026-10-23 — spec §5.1, §6.1, §6.3)

Publishing or retiring a version writes a row to `sf_port_outbox` **inside the same transaction** (trigger `sf_port_enqueue_trg`, migration 0025). A worker (`lib/integrations/port/outbox.ts`, service role) upserts the skill's *current* state onto its `aiSkill` entity and records the result in `sf_port_links` (hash, version, state, time, last error). Port being down never blocks a release; a failed push backs off (2, 4, 8, 16, 32 min) and is dead-lettered after 5 attempts, listed under Integrations → Port → *Needs attention*. Nothing is marked processed until Port acknowledged it.

| Path | When | Auth |
|---|---|---|
| in-process kick | right after every publish / retire (and after **Push skills to Port**) | the acting user's session starts it; the worker itself uses the service role |
| `POST /api/port/sync` | catch-up: run it from a scheduler or by hand | `Authorization: Bearer $HEALTH_CHECK_TOKEN` (or `CRON_SECRET`) |
| `GET /api/port/reconcile?format=text` | factory vs Port, one line per difference (sync-pending / sync-failed / dead-lettered / hash-drift / status-drift / edited-in-port / missing-in-port / unknown-in-factory) | same |

**Entity properties.** The `aiSkill` blueprint now also carries the factory-owned `sf_*` properties (`sf_version`, `sf_content_hash`, `sf_status`, `sf_eval_verdict`, `sf_trigger_score`, `sf_lift`, `sf_eval_cases`, `sf_eval_model`, `sf_eval_at`, `sf_approval_valid`, `sf_factory_url`, `sf_mcp_tool`, `sf_owner`, `sf_synced_at`). They are overwritten on every sync and Port never recomputes them; an edit made in Port shows up in reconcile as *edited-in-port*. Null means the factory does not have the value — never 0. The first sync after this release **extends** the existing blueprint in place (PATCH adds the missing properties; nothing the tenant added is removed).

**Registry relation.** When the tenant has Port's Skills-registry `skill` blueprint and `PORT_REGISTRY_REPO` (plain env, `<owner>/<repo>`) names the repository Port scanned, each repo-sourced skill is related to its `SKILL.md` registry entity (`registry_file`). The registry stays Port's; the factory never writes into it (owner decision D7, docs/PORT-INTEGRATION-WP0.md).

**Retire.** `sf_status = retired`, `sf_mcp_tool = null`; the entity is kept (audit trail), never deleted.

**Tokens.** One token per server, refreshed single-flight at the earlier of Port's `expiresIn` and 2.5 h (Port keeps one active token per credential set).

## Scorecard `skill_quality` (WP2, spec §4.2)

Created on the `aiSkill` blueprint by the sync worker (and by `GET /api/port/scorecard`), rules test synced `sf_` properties only:

| Level | Rule |
|---|---|
| Bronze | `sf_status = published` and `sf_eval_verdict` not empty |
| Silver | Bronze and `sf_eval_verdict = healthy` and `sf_approval_valid = true` |
| Gold | **not created** — thresholds are owner decision D3 (docs/PORT-INTEGRATION-WP0.md); nothing is defaulted |

Readback (the contract test — levels are Port's own computation): `GET /api/port/scorecard?slugs=llm-cost-model,perf-review-runner,effort-estimator` with the operator bearer.

## Security

- The webhook only accepts requests signed by Port: HMAC-SHA256 of `timestamp.body` with the Port client secret. Requests older than 5 minutes are refused.
- The webhook runs skills under `PORT_SF_API_KEY`, never a user session. It is scoped to one workspace and audited like any API call. The Port run id is the idempotency key, so a retried webhook never runs a skill twice.
- Nothing from Port is trusted as a skill name or input until it passes the same validation as `/api/v1`.

## First live run: verify these

Port's docs leave these unspecified; the code takes the most likely reading:

| Item | Assumption in code | If it differs |
|---|---|---|
| Duplicate blueprint on push | ✅ verified live: treated as "exists" | — |
| Token lifetime | `expiresIn` (seconds) if present, else 50 min | — |
| Run log body | `{ message, terminationStatus, statusLabel }` | Adjust `runLog` |
| Run link | `PATCH /v1/actions/runs/{id}` with `{ link: [url] }` | Adjust `runUpdate` |
| `{{ .inputs.inputs }}` (object input) | Arrives as an object or a JSON string; both are accepted | — |
| Property types `markdown`, `array` | Accepted in blueprint schema | Change the type to `string` |

Code: `lib/integrations/port/` (client, map, signature, sync), `app/api/port/actions/route.ts`. Tests: `tests/port.test.ts`.

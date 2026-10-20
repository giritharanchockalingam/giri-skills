# Port.io integration

Skills Factory plugs into a [Port](https://port.io) portal three ways. All three use the same governed skills: only **published** versions, with the same input validation, policy limits, content pinning and audit as the API and MCP server.

| | What Port users get | Built on |
|---|---|---|
| **1. MCP connector** | Port's AI agents call your skills as tools | Port's **Custom Server** MCP connector → `/api/mcp` (no code) |
| **2. Run skill action** | A **Run skill** button on every AI Skill entity; progress, result link and SUCCESS / FAILURE shown in Port | Port self-service action (WEBHOOK) → `/api/port/actions` (signed) |
| **3. AI Skill catalog** | An **AI Skill** blueprint: version, eval pass rate, approval, library status, inputs, link back | Port REST API: blueprint + entity upsert (**Integrations → Push skills to Port**) |

**Status:** built to Port's published API and docs, unit-tested against those request and response shapes. **It has not yet run against a live Port organisation.** The checklist below covers the first live run.

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
5. **Run skill action.** On the Port card, open **Run skill action**, copy the JSON, then in Port go to **Self-service → + Action → Edit JSON**, paste and save.
6. **MCP connector.** In Port, go to **Settings → Data sources → + Connector → MCP Servers → Custom Server**:
   - URL: `https://<your portal>/api/mcp`
   - Header: `Authorization: Bearer {{ .secrets["SF_API_KEY"] }}`, with a workspace key stored as the Port secret `SF_API_KEY`
   - Allowed tools: the skills Port's agents may call

## Security

- The webhook only accepts requests signed by Port: HMAC-SHA256 of `timestamp.body` with the Port client secret. Requests older than 5 minutes are refused.
- The webhook runs skills under `PORT_SF_API_KEY`, never a user session. It is scoped to one workspace and audited like any API call. The Port run id is the idempotency key, so a retried webhook never runs a skill twice.
- Nothing from Port is trusted as a skill name or input until it passes the same validation as `/api/v1`.

## First live run: verify these

Port's docs leave these unspecified; the code takes the most likely reading:

| Item | Assumption in code | If it differs |
|---|---|---|
| Duplicate blueprint on push | `POST /v1/blueprints` returns **409**, treated as "exists" | Adjust `ensureBlueprint` |
| Token lifetime | `expiresIn` (seconds) if present, else 50 min | — |
| Run log body | `{ message, terminationStatus, statusLabel }` | Adjust `runLog` |
| Run link | `PATCH /v1/actions/runs/{id}` with `{ link: [url] }` | Adjust `runUpdate` |
| `{{ .inputs.inputs }}` (object input) | Arrives as an object or a JSON string; both are accepted | — |
| Property types `markdown`, `array` | Accepted in blueprint schema | Change the type to `string` |

Code: `lib/integrations/port/` (client, map, signature, sync), `app/api/port/actions/route.ts`. Tests: `tests/port.test.ts`.

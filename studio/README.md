# giri-skills studio — Skills Factory

Next.js app over the `giri-skills` repo with two halves:

1. **Skills Factory** (new, server-rendered, Supabase-backed): create or import skills, version their contract (manifest), test them on a server runtime, run evaluations, approve and publish immutable versions, run them from the UI or the consumer API, and audit everything. Roles: consumer · author · reviewer · admin.
2. **Repository views** (unchanged, build-time data): the 40 repository skills, their eval scorecard, findings and the 50 vendored upstream skills.

Docs: `docs/API.md` (consumer API + manifest format), `docs/VERIFY.md` (verification checklist), `docs/BASELINE.md` (what existed before the factory).

## Routes

| Area | Route | What |
|---|---|---|
| Overview | `/overview` | Pending reviews, versions ready to publish, failed runs (7 days), measured counts with definitions; workspace creation for a first user |
| Skills | `/` | Workspace skills catalog (search, status/source filters), **New skill**, **Import from repository** |
| | `/skills/new` | Create a skill (name, purpose, users, guidance) → draft v1 |
| | `/skills/<slug>` | Summary: what/when, status + version, owner, inputs/outputs/steps, evidence, needs (tools/connections), one primary next action |
| | `/skills/<slug>/authoring` | Skill details, manifest editor (validated live, hashed on save), resource files (authored skills) |
| | `/skills/<slug>/test` | **Test skill**: real inputs → server runtime → persisted run; link to the browser runner |
| | `/skills/<slug>/evaluations` | Cases (CRUD), **Run evaluation**, history with per-case results, release gate |
| | `/skills/<slug>/release` | Gates (evaluation, approval validity/staleness), request/withdraw review, approve/reject, reopen, **Publish version**, retire, new draft |
| | `/skills/<slug>/activity` | Runs of the selected version |
| | `/repo/`, `/repo/<domain>/<name>/` | Repository catalog and skill pages (scorecard stats, agent block, **Run it** in the browser, SKILL.md, eval cases) |
| | `/upstream/`, `/upstream/<name>/` | Vendored upstream skills |
| Deliver | `/deliver`, `/deliver/<id>` | Delivery pipelines (`docs/DELIVERY-PIPELINES.md`): start a run (pipeline, repository, ref, request, executor), watch stages, gate verdicts and evidence hashes, approve the stage a run waits on, download `run.json`. API: `POST /api/delivery-runs`, `GET/POST /api/delivery-runs/<id>[/stage|/approve]`; MCP tools `deliver`, `delivery_status` |
| Evaluations | `/evaluations` | Readiness across workspace versions; links to `/evals/` (repo scorecard) and `/findings/` |
| Activity | `/activity`, `/runs/<id>` | Run list (status/source filters) and run detail: steps, checks, output contract, outputs (view/download), logs, provider/model/usage/cost (estimate flag), inputs reference |
| Administration | `/admin` | Members + roles, API keys (shown once), connections + runtime check, policies (tools, providers, budget, concurrency), audit log, account/sign-out |
| Auth | `/login` | Supabase email + password, email link, sign-up |
| API | `/api/v1/*` | Consumer API — see `docs/API.md` |
| Runtime | `/api/py/run` | Vercel Python function executing `scripts/run_skill.py` (shared-secret protected; called by the server only) |

## Setup

Environment variables (Vercel → Project → Settings → Environment Variables, or `.env.local` for `next dev`):

| Variable | Where | Required | Purpose |
|---|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | server + browser | yes | Supabase project URL, e.g. `https://ysesfztvcexufoogjgth.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | server + browser | yes | Supabase publishable (anon) key; RLS protects data |
| `SF_RUNTIME_SECRET` | server (Next + Python function) | yes for runs | Shared secret the Next server sends to `/api/py/run`; generate with `openssl rand -hex 32`. Without it runs refuse with "runtime not configured" |
| `ANTHROPIC_API_KEY` | server (Python function) | optional | Enables llm steps. Absent → llm steps are skipped and reported, never faked |
| `SF_RUNTIME_URL` | server | optional | Override the runtime base URL (defaults to the Vercel deployment URL; needed under `vercel dev`: `http://localhost:3000`) |
| `VERCEL_AUTOMATION_BYPASS_SECRET` | server | optional | Lets the server call the Python function on protected preview deployments |
| `DELIVERY_GITHUB_TOKEN` | server | optional | Token with Actions: write on the library repo; **Deliver** dispatches `.github/workflows/delivery.yml` with it. Unset → GitHub Actions runs stay queued with the notice "no executor configured — run `scripts/deliver.py` from an IDE and post evidence" |
| `DELIVERY_GITHUB_REPO`, `DELIVERY_GITHUB_REF` | server | optional | Repository (`owner/name`, default `giritharanchockalingam/giri-skills`) and branch (default `main`) that hold `delivery.yml` |

Database: apply `supabase/migrations/0001_sf_schema.sql` then `0002_sf_functions.sql` in the Supabase SQL editor (or `supabase db push`). Every object is prefixed `sf_`; nothing else in the project is touched; re-running is safe. Auth is the project's existing Supabase Auth; the first user to create a workspace becomes its admin and adds members by email.

## Run locally

```bash
cd studio
npm install
cp .env.example .env.local        # fill in the values above
npm run dev                       # ingest, then next dev on http://localhost:3000 (UI + API; no Python runtime)
vercel dev                        # alternative: also serves api/py/run.py; set SF_RUNTIME_URL=http://localhost:3000
```

## Tests

```bash
cd studio
npm run typecheck                 # tsc --noEmit
npm run test:unit                 # node --test: manifest, schema, hash, release state, roles, import of all 40 repo skills
npm run test:py                   # pytest: the Python runtime (api/py/run.py) offline — needs api/py/bundle.json (npm run ingest)
PGHOST=/tmp PGPORT=54329 PGUSER=postgres npm run test:sql   # migrations + RLS/RPC behaviour on a local PostgreSQL (tests/sql/run.sh)
npm test                          # typecheck + unit + py
```

## Build and deploy

```bash
cd studio
npm run build                     # ingest (data/, public/runtime/, api/py/bundle.json), then next build (server mode)
npm run start                     # next start
```

Vercel: **Root Directory = `studio`**, Framework Preset = Next.js. `vercel.json` configures the Python function (`api/py/*.py`: 60 s, 1024 MB, excludes `node_modules`, `.next`, `data`, …). `api/py/bundle.json` (the runtime bundle) is committed so the function has it regardless of build order. Push to the connected branch; set the env vars above; apply the migrations once.

## Run view (in-browser runner)

Every repository skill page (`/repo/<domain>/<name>/`) has a **Run it** card that executes the real `scripts/run_skill.py` — the same runner, the same skill scripts, the same `check_output.py` checks — inside the browser. Nothing is mocked: what the card shows is read back from the `run.json` the runner wrote.

How it works:

- **Pyodide** (CPython 3.12 compiled to WebAssembly, pinned `v0.27.7` from `https://cdn.jsdelivr.net/pyodide/v0.27.7/full/`, a CDN script, not an npm dependency) is loaded lazily in a Web Worker (`public/run-worker.js`) the first time the card is opened (≈10 MB, cached by the browser after that). The worker fetches `public/runtime/bundle.json`, writes every file into Pyodide's virtual FS under `/repo`, sets `RUN_SKILL_INPROC=1`, puts `/repo/scripts` on `sys.path` and calls `run_skill.main()` with a normal argv. `lib/runner.ts` is the typed client; `components/RunPanel.tsx` is the UI.
- **In-process mode.** Pyodide has no `subprocess`, so the runner has an in-process path (`--inproc` or `RUN_SKILL_INPROC=1`): script steps and `cmd:` checks run via `runpy.run_path(..., run_name="__main__")` with the same argv, cwd, captured stdout/stderr, `SystemExit` → exit-code rules, `stdout:` redirection and `expect_exit` as the subprocess path (`check_output.run_command`). Everything else (inputs, assumptions, `needs_input.json`, llm steps, checks, `run.json`) is the same code. `tests/test_run_skill_inproc.py` runs every wired skill's `--demo` once per mode and asserts every output file is byte-identical (only `duration_s`, the out-dir path and git commit hashes are normalised).
- **Inputs.** The form is generated from `metadata.agent.inputs` (required first). File inputs take an upload or pasted text (written to `/repo/_inputs/<run>/<name>.<ext>`), or the skill's happy-path fixture via *Use example fixture* (labelled as such). `path` inputs (output targets like `project-bootstrap`'s `target`) default to `{out}/<name>`. `dir` inputs cannot take your own folder in the browser; the fixture folder is offered when the demo case has one. Every input has an *Assume instead* field (`--assume name=value`, labelled `[ASSUMED]` in the outputs).
- **LLM steps and the key.** With no key the runner is called with `--provider none`: llm steps are **skipped** with `skipped_reason: "no provider key (LLM step not run)"` in `run.json`, their output files are absent, and the checks on them fail — the page shows exactly that. With a key, `--provider jsbridge` routes `provider.complete()` to a JS callback (`behavioral_evals.JS_LLM_CALLBACK`) that POSTs to `https://api.anthropic.com/v1/messages` (`x-api-key`, `anthropic-version: 2023-06-01`, `anthropic-dangerous-direct-browser-access: true`) with a synchronous XHR from the worker. The key is held in a React state variable, passed to the worker for one run and dropped; it is never written to the FS, `run.json`, logs, localStorage or the URL. The input is `type=password`.
- **Results.** Overall banner (OK / FAILED / NEEDS INPUT naming the missing inputs), per-step table (kind, exit, duration, skipped reason), per-check table (file, check, pass/failed, evidence — failed rows in red), output files with view (rendered Markdown via `lib/markdown.mjs` or raw) and download, `run.json` download, and the captured `logs/` of every step.
- **Bundle.** `ingest` also writes `public/runtime/`: `scripts/{run_skill,check_output,skillmeta,behavioral_evals}.py`, `shared/*.md`, and for each wired skill `SKILL.md`, `scripts/`, `assets/`, `references/`, `evals/fixtures/`, `evals/evals.json` under `repo/…` (≈1.6 MB, 451 files), plus `manifest.json` (file list with sizes) and `bundle.json` (one fetch). Anything the repo `.gitignore` keeps local (the real master résumé, rate card, story bank) is never copied. `public/runtime/` is generated and git-ignored.
- Pyodide runs single-threaded, so no COOP/COEP headers are needed. For local testing where the CDN is unreachable, `?pyodide=/pyodide/` loads the runtime from a same-origin path (e.g. the `pyodide` npm package copied into `out/pyodide/`); other origins are ignored.

## Refresh data after a new eval run

```bash
cd studio
npm run ingest                                   # default: ../evals/results/full-openai
RESULTS_DIR=evals/results/pilot-openai npm run ingest   # another results dir (relative to repo root, or absolute)
AGENT_RESULTS_DIR=evals/results/agent-dry npm run ingest # agent run results (default shown); set both to mix runs
git add data/                                    # commit the regenerated JSON
```

`ingest` reads (and writes `public/runtime/` for the Run view, printing the bundle size):

- `skills/<domain>/<name>/SKILL.md` (frontmatter + body → safe pre-rendered HTML), `evals/evals.json`, and the file names under `scripts/`, `references/`, `assets/`
- `<RESULTS_DIR>/scorecard.md` (table + the provider/model/runs/date/spend header lines), `trigger.csv`, `quality.csv`
- `<AGENT_RESULTS_DIR>/agent.csv` (skill, case_id, check, pass, evidence → `data/agent.json`) and the `agent pass` / `agent verdict` columns of `<AGENT_RESULTS_DIR>/scorecard.md`, merged per skill into `data/scorecard.json` as `agentPass` (0–1 or null) and `agentVerdict` (`Works` / `Partial` / `Broken` / null). The trigger/quality columns of that file are ignored. Each skill's `metadata.agent` block (inputs, run steps, outputs) lands in `data/skills.json` as `agent`, or null when the skill is not wired.
- `docs/EVAL-FINDINGS.md` (caveats, verdict counts, ranked proposals)
- `catalog/top-50.json` (rank, repo, path, category, license, evidence, why), `vendor/pins.json` (repo, path, sha, license, fetched per skill) and `vendor/<name>/SKILL.md` (frontmatter `description` — plain, quoted, folded or literal YAML scalars all handled — plus body → safe HTML; file count of the vendored tree, minus our `UPSTREAM.md`) → `data/upstream.json`. `licenseKind` is `source-available` when the pin's license text contains "Anthropic source-available", else `oss`; `origin` is `vendor` for anthropics/vercel-labs/supabase/stripe/cloudflare/microsoft/google/getsentry/langchain-ai/shadcn repos, else `community`. `url` is the pinned GitHub tree (`https://github.com/<repo>/tree/<sha>/<path>`).

It prints the row counts it found; `data/meta.json` carries the same counts plus the run header.


## Stack

Next.js 15 (App Router, server mode, `trailingSlash`), React 19, TypeScript, Tailwind v4 via `@tailwindcss/postcss`, `@supabase/supabase-js` + `@supabase/ssr` (auth + data; RLS enforced in the database, roles re-checked in every server action and route handler). The Python runtime is stdlib-only. Dark mode follows `prefers-color-scheme`.

```
studio/
├── app/                 routes (see table); actions.ts = server actions; api/ = route handlers (UI runs, eval runs, v1 consumer API, runtime health)
├── api/py/run.py        Vercel Python function: materialises the bundle into /tmp, runs run_skill.py in-process under a deadline with a scrubbed env
├── api/py/bundle.json   generated by ingest (committed): scripts/, shared/, every wired skill's SKILL.md/scripts/assets/references/fixtures
├── components/          factory/ (forms, editors, tables, pills) + the repository dashboard components
├── lib/factory/         manifest (contract + validation), schema (input/output validation), hash, roles, release (gates/next action), import, db (types + context), runtime (bridge), apikey, http
├── lib/supabase/        server/browser clients, env
├── middleware.ts        session refresh + route protection
├── supabase/migrations/ 0001_sf_schema.sql (tables, triggers, RLS), 0002_sf_functions.sql (release-state view, lifecycle + API RPCs)
├── tests/               factory.test.ts (node --test), test_factory_runtime.py (pytest), sql/ (migration behaviour tests)
├── docs/                API.md, VERIFY.md, BASELINE.md
├── lib/data.ts, scripts/ingest.mjs, public/run-worker.js, public/runtime/   repository views + in-browser runner (unchanged)
└── data/                generated JSON for the repository views (committed)
```

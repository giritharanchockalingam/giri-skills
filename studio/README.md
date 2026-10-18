# giri-skills studio

Static Next.js dashboard over the `giri-skills` repo: the 40 skills, their eval cases, the behavioral eval scorecard (`evals/results/<run>/`), the ranked proposals in `docs/EVAL-FINDINGS.md`, and the 50 vendored upstream skills (`catalog/top-50.json` + `vendor/`).

Views:

| Route | What |
|---|---|
| `/` | Skills catalog — filter by domain/verdict, search name + description, click a row for detail |
| `/skills/<domain>/<name>/` | Skill detail — stat strip, "Runs as an agent" card (how to run, declared inputs/steps/outputs, agent eval checks), **"Run it"** (runs the skill in the browser, see below), rendered SKILL.md, file inventory, eval cases with per-run trigger + quality (PASS/FAIL + judge evidence) |
| `/evals/` | Eval dashboard — verdict distribution, per-domain breakdown, sortable/filterable scorecard with drill-down (misrouted prompts, most-failed expected items, agent run checks); the "Runs" column is the deterministic agent verdict |
| `/findings/` | Caveats, verdict counts, 25 ranked proposals with paste-ready description blocks (Copy button) and body directions; anchor `#<n>` per proposal |
| `/upstream/` | The 50 vendored upstream skills — search name/description/repo, filter by category and license (open source vs Anthropic source-available), ranked by installs; row → detail |
| `/upstream/<name>/` | Upstream skill detail — stat strip (rank, category, license, pinned sha, files), Source card (GitHub link at the pinned commit, repo, path, fetched date, license note), rendered SKILL.md |

No runtime fetching: `scripts/ingest.mjs` reads the repo at build time and writes `data/*.json`, which is the UI's only data source. `data/` is committed so the site builds on Vercel without the eval CSVs. The one exception is the Run view, which fetches the generated `public/runtime/` bundle and the Pyodide runtime when opened.

## Run view (in-browser runner)

Every wired skill page has a **Run it** card that executes the real `scripts/run_skill.py` — the same runner, the same skill scripts, the same `check_output.py` checks — inside the browser. Nothing is mocked: what the card shows is read back from the `run.json` the runner wrote.

How it works:

- **Pyodide** (CPython 3.12 compiled to WebAssembly, pinned `v0.27.7` from `https://cdn.jsdelivr.net/pyodide/v0.27.7/full/`, a CDN script, not an npm dependency) is loaded lazily in a Web Worker (`public/run-worker.js`) the first time the card is opened (≈10 MB, cached by the browser after that). The worker fetches `public/runtime/bundle.json`, writes every file into Pyodide's virtual FS under `/repo`, sets `RUN_SKILL_INPROC=1`, puts `/repo/scripts` on `sys.path` and calls `run_skill.main()` with a normal argv. `lib/runner.ts` is the typed client; `components/RunPanel.tsx` is the UI.
- **In-process mode.** Pyodide has no `subprocess`, so the runner has an in-process path (`--inproc` or `RUN_SKILL_INPROC=1`): script steps and `cmd:` checks run via `runpy.run_path(..., run_name="__main__")` with the same argv, cwd, captured stdout/stderr, `SystemExit` → exit-code rules, `stdout:` redirection and `expect_exit` as the subprocess path (`check_output.run_command`). Everything else (inputs, assumptions, `needs_input.json`, llm steps, checks, `run.json`) is the same code. `tests/test_run_skill_inproc.py` runs every wired skill's `--demo` once per mode and asserts every output file is byte-identical (only `duration_s`, the out-dir path and git commit hashes are normalised).
- **Inputs.** The form is generated from `metadata.agent.inputs` (required first). File inputs take an upload or pasted text (written to `/repo/_inputs/<run>/<name>.<ext>`), or the skill's happy-path fixture via *Use example fixture* (labelled as such). `path` inputs (output targets like `project-bootstrap`'s `target`) default to `{out}/<name>`. `dir` inputs cannot take your own folder in the browser; the fixture folder is offered when the demo case has one. Every input has an *Assume instead* field (`--assume name=value`, labelled `[ASSUMED]` in the outputs).
- **LLM steps and the key.** With no key the runner is called with `--provider none`: llm steps are **skipped** with `skipped_reason: "no provider key (LLM step not run)"` in `run.json`, their output files are absent, and the checks on them fail — the page shows exactly that. With a key, `--provider jsbridge` routes `provider.complete()` to a JS callback (`behavioral_evals.JS_LLM_CALLBACK`) that POSTs to `https://api.anthropic.com/v1/messages` (`x-api-key`, `anthropic-version: 2023-06-01`, `anthropic-dangerous-direct-browser-access: true`) with a synchronous XHR from the worker. The key is held in a React state variable, passed to the worker for one run and dropped; it is never written to the FS, `run.json`, logs, localStorage or the URL. The input is `type=password`.
- **Results.** Overall banner (OK / FAILED / NEEDS INPUT naming the missing inputs), per-step table (kind, exit, duration, skipped reason), per-check table (file, check, pass/failed, evidence — failed rows in red), output files with view (rendered Markdown via `lib/markdown.mjs` or raw) and download, `run.json` download, and the captured `logs/` of every step.
- **Bundle.** `ingest` also writes `public/runtime/`: `scripts/{run_skill,check_output,skillmeta,behavioral_evals}.py`, `shared/*.md`, and for each wired skill `SKILL.md`, `scripts/`, `assets/`, `references/`, `evals/fixtures/`, `evals/evals.json` under `repo/…` (≈1.6 MB, 451 files), plus `manifest.json` (file list with sizes) and `bundle.json` (one fetch). Anything the repo `.gitignore` keeps local (the real master résumé, rate card, story bank) is never copied. `public/runtime/` is generated and git-ignored.
- Static export is unchanged; Pyodide runs single-threaded, so no COOP/COEP headers are needed. For local testing where the CDN is unreachable, `?pyodide=/pyodide/` loads the runtime from a same-origin path (e.g. the `pyodide` npm package copied into `out/pyodide/`); other origins are ignored.

## Run locally

```bash
cd studio
npm install
npm run dev        # runs ingest first, then next dev on http://localhost:3000
```

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

## Build

```bash
cd studio
npm run build      # runs ingest, then next build → static site in out/
npm run start      # zero-dependency static server for out/ on http://localhost:4173
```

## Deploy to Vercel

Project settings: **Root Directory = `studio`**, Framework Preset = Next.js (static export is picked up from `next.config.ts`; no server functions). Build command `npm run build`, output directory `out`.

```bash
npm i -g vercel
cd studio
vercel login
vercel link                                  # create/link the project; answer the prompts
vercel                                       # preview deploy
vercel --prod                                # production deploy
```

If the project was linked from the repo root instead of `studio/`, set the root directory once:

```bash
vercel project ls
# Dashboard → Project → Settings → General → Root Directory → studio
```

Git-connected deploys work the same way: push to the connected branch; Vercel runs `npm run build` inside `studio/` (ingest needs the repo present, which it is in a Git deploy; the committed `data/` also makes the build independent of the git-ignored `evals/results/*/raw/`).

## Stack

Next.js 15 (App Router, `output: 'export'`, `trailingSlash`), React 19, TypeScript, Tailwind v4 via `@tailwindcss/postcss`. No other dependencies — markdown rendering, CSV parsing, and the verdict bar are hand-rolled in `scripts/ingest.mjs` and plain CSS. Dark mode follows `prefers-color-scheme`.

```
studio/
├── app/            routes: / , /evals/ , /findings/ , /skills/[domain]/[name]/ , /upstream/ , /upstream/[name]/
├── components/     client components (tables, filters, drill-downs, copy button, RunPanel)
├── lib/data.ts     typed accessors over data/*.json
├── lib/runner.ts   browser client for the Pyodide worker (runSkill, loadRuntime)
├── lib/markdown.mjs shared Markdown → safe HTML (ingest at build time, RunPanel in the browser)
├── public/run-worker.js  Web Worker: Pyodide + run_skill.py in-process, LLM bridge
├── public/runtime/ generated runtime bundle (git-ignored; written by ingest)
├── scripts/        ingest.mjs (repo → JSON + runtime bundle), serve.mjs (static server for out/)
└── data/           generated JSON (committed)
```

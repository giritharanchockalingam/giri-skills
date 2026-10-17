# giri-skills studio

Static Next.js dashboard over the `giri-skills` repo: the 40 skills, their eval cases, the behavioral eval scorecard (`evals/results/<run>/`), and the ranked proposals in `docs/EVAL-FINDINGS.md`.

Views:

| Route | What |
|---|---|
| `/` | Skills catalog — filter by domain/verdict, search name + description, click a row for detail |
| `/skills/<domain>/<name>/` | Skill detail — stat strip, rendered SKILL.md, file inventory, eval cases with per-run trigger + quality (PASS/FAIL + judge evidence) |
| `/evals/` | Eval dashboard — verdict distribution, per-domain breakdown, sortable/filterable scorecard with drill-down (misrouted prompts, most-failed expected items) |
| `/findings/` | Caveats, verdict counts, 25 ranked proposals with paste-ready description blocks (Copy button) and body directions; anchor `#<n>` per proposal |

No runtime fetching: `scripts/ingest.mjs` reads the repo at build time and writes `data/*.json`, which is the UI's only data source. `data/` is committed so the site builds on Vercel without the eval CSVs.

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
git add data/                                    # commit the regenerated JSON
```

`ingest` reads:

- `skills/<domain>/<name>/SKILL.md` (frontmatter + body → safe pre-rendered HTML), `evals/evals.json`, and the file names under `scripts/`, `references/`, `assets/`
- `<RESULTS_DIR>/scorecard.md` (table + the provider/model/runs/date/spend header lines), `trigger.csv`, `quality.csv`
- `docs/EVAL-FINDINGS.md` (caveats, verdict counts, ranked proposals)

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
├── app/            routes: / , /evals/ , /findings/ , /skills/[domain]/[name]/
├── components/     client components (tables, filters, drill-downs, copy button)
├── lib/data.ts     typed accessors over data/*.json
├── scripts/        ingest.mjs (repo → JSON), serve.mjs (static server for out/)
└── data/           generated JSON (committed)
```

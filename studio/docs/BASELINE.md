# Baseline before the factory build (brief §1)

Inspected: `studio/` (Next.js 15 static export), `scripts/run_skill.py`, `scripts/check_output.py`, `scripts/skillmeta.py`, `scripts/behavioral_evals.py`, `data/*.json`, `public/run-worker.js`, `docs/AGENT-REBUILD-PLAN.md`. Date: 2026-10-17, branch `main` at `2030373`.

## What existed, honestly classified

| Capability | State | Evidence |
|---|---|---|
| Skill catalog (40 repo skills), eval scorecard, findings, upstream library | **Working, read-only, build-time data** | `scripts/ingest.mjs` → `data/*.json`; no runtime fetching; static export |
| Running a skill (`run_skill.py`, in-process, Pyodide in the browser) | **Working, real execution, nothing persisted** | `public/run-worker.js`; results read from `run.json`; 451-file runtime bundle; `tests/test_run_skill_inproc.py` proves CLI parity |
| LLM steps in the browser | **Working only with a key pasted into the page** (sent browser → api.anthropic.com) | `RunPanel.tsx`; no server, no usage recorded |
| Deterministic output checks | **Working** (`check_output.py` vocabulary) | used by the runner and agent evals |
| Authentication / users / roles | **Missing** | no auth code; the site was public static HTML |
| Persistence (skills, versions, runs, evaluations, approvals) | **Missing** | no database; `data/` is generated JSON |
| Skill contract / manifest / versions / immutability | **Partial — format only** | `metadata.agent` in SKILL.md declared inputs/run/outputs; no versioning, no hash, no lifecycle |
| Authoring in the product | **Missing** (edit the repo files) | — |
| Evaluations tied to a version | **Partial** | `evals/evals.json` agent cases run by `behavioral_evals.py --agent` on the CLI; results are CSV snapshots ingested at build time |
| Approval / publishing / release gates | **Missing** | — |
| Consumer API | **Missing** | — |
| Audit, policies, API keys, connections, budgets, concurrency | **Missing** | — |
| Timeouts / retries | **Partial** | subprocess timeout 900 s on the CLI; none in-browser; provider retry 3× fixed in `AnthropicLLM` |
| Fabricated values / hardcoded success | **None found** | the dashboard shows measured eval results; the Run view shows the runner's own `run.json`; no placeholder handlers |
| Mobile layout | **Working** for the dashboard (card lists under 768px) | `globals.css` |

## Trace of the critical paths (before)

* **Authentication**: none. **Authorization**: none. **Tenancy**: none.
* **Persistence**: none at runtime; `data/*.json` committed from the eval CSVs.
* **Model calls**: only via the browser bridge (`--provider jsbridge`) with a user-pasted key, or on the CLI with `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` and the `anthropic`/`openai` packages. Usage not captured.
* **Tool execution**: `script` steps = `python3 scripts/x.py` in-process (runpy) or subprocess; `cmd:` checks likewise.
* **Evaluation**: CLI only; results static.
* **Publishing**: not a concept; "published" meant "committed to the repo".

## Shortest complete path chosen

Import a repository skill → it becomes a draft v1 with a validated manifest and its agent cases → Test it server-side (persisted run with provider/usage/cost) → Run evaluation (per-case runs, pass rate pinned to the case-set hash) → Request review → a reviewer approves the exact manifest hash → Publish (server-gated) → consumers run it from the UI, applications from `/api/v1` → every run recorded → author creates an improved draft while the published version keeps serving. All of this is implemented on top of the existing runner rather than replacing it; the browser runner remains as "Run in browser (no server)".

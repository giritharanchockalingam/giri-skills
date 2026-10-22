---
name: perf-review-runner
description: Use when a Next.js (App Router) + React + TypeScript + Supabase repo needs a static performance review before a traffic spike, launch or scale-up — "perf review before Black Friday", "will this page fall over under load", "find the N+1s", "why is this list page slow", "check our Supabase queries for select(*) and missing limits". Produces findings.csv (rule, file, line, snippet, severity, status) and report.md (Summary, Findings, Rules) from ten deterministic rules PF1–PF10: N+1 queries in loops, await in loops, select("*"), unbounded list reads, fetching in useEffect, sort/filter over props on every render, raw <img>, heavy client libraries imported in pages, cache "no-store" on every fetch, synchronous file reads in route handlers; high findings fail the gate, a baseline marks known debt. Not for stack conventions and layering (use nextjs-enterprise-conventions), measuring latency or errors in production (use observability-setup), or fixing what it finds (use safe-fix).
license: MIT
metadata:
  domain: build
  adlc_stage: build
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: target, type: dir, required: true, from: "Next.js repo root (app/, components/, lib/, server/)"}
      - {name: baseline, type: csv, required: false, from: "findings.csv from an earlier run — the recorded performance debt; known findings are listed but only new high-severity ones fail the gate"}
    run:
      - {step: review, kind: script, cmd: "python3 -I scripts/perf_review.py --target {target} [--baseline {baseline}] --findings {out}/findings.csv --report {out}/report.md"}
    outputs:
      - {path: "{out}/findings.csv", checks: [exists, csv:[rule,file,line,snippet,severity,status]]}
      - {path: "{out}/report.md", checks: [exists, sections:["Summary","Findings","Rules"], contains:"Gate:"]}
    modes:
      new: {case: agent-happy-path, bring: "a repo before its first big traffic day"}
      existing: {case: agent-mode-existing, bring: "your repo and the perf debt recorded last time"}
---

# perf-review-runner

The review a senior performance engineer does on the source before a traffic spike: ten checkable patterns that make a Next.js + Supabase app slow under load, each reported as `file:line` with a severity and a fix. Static only — nothing runs, nothing is measured.

## In a conversation: review the code now
**Never**
- Never report a PASS, a finding count or a "no N+1s" verdict for code that is not in the conversation. Review only pasted or attached source; for the rest, lay out the checklist and ask for the files.
- Never invent a latency, a query count or a "p95" — this review measures nothing. Numbers come from `observability-setup` dashboards, not from here.
- Never rate `select("*")`, an unbounded list read or an N+1 as medium because "the table is small today": they are **high** and fail the gate; the baseline is the only way to carry them as known debt.
- Never flag `useMemo`-wrapped sort/filter (PF6), a `for await` loop (PF2), a `.single()`/`.range()`/`.limit()` chain (PF4), a `head: true` count (PF3/PF4) or a heavy import in a non-page component (PF8): those are the clean forms.

**Procedure (from `scripts/perf_review.py`; work file by file through the supplied code)**
1. Classify each file: client (`"use client"`) or server; `app/**/page|layout` (page), `app/**/route.ts` (handler), other.
2. Loops and callbacks: a Supabase `.from(`/`.rpc(` or `fetch(` inside a `for`/`while` body or a `.map`/`.forEach`/`.flatMap` callback → **PF1 high**. Any other `await` inside a `for`/`while` body (not `for await`) → **PF2 medium**.
3. Every Supabase chain `.from(…).select(…)…`: a select list containing `*` → **PF3 high**; a read (no insert/update/delete/upsert, no `head: true`) with none of `.limit(`/`.range(`/`.single(`/`.maybeSingle(`/`.eq("id", …)` → **PF4 high**.
4. Client files: a `useEffect` whose callback calls `fetch`/`.from`/`.rpc` → **PF5 medium**; in a PascalCase component body, `.sort(`/`.filter(` on a destructured prop or `props.x` outside `useMemo`/`useCallback`/`useEffect` → **PF6 medium**.
5. `.tsx`/`.jsx`: `<img` → **PF7 medium**. Pages: a static `import … from` one of the heavy client libraries (recharts, chart.js, three, monaco, mapbox-gl, leaflet, pdfjs, xlsx, quill, tiptap, ag-grid, moment, lodash, …) → **PF8 medium**; a server page where every `fetch` passes `cache: "no-store"` → **PF9 medium** per fetch.
6. Route handlers: `readFileSync`/`readdirSync` inside an exported `GET|POST|…` body → **PF10 medium** (module-scope reads are fine).
7. Sort by file, line, rule. Gate: FAIL if any high finding is new; PASS otherwise. With a baseline, match on rule + file + snippet (lines may move): matched → `known`, else `new`; unmatched baseline rows → resolved.

**Reply layout**: the Summary table (rule, name, severity, count), then **Findings** (rule, `file:line`, severity, status, snippet, fix from `references/perf-rules.md`), then the gate line `Gate: PASS` / `Gate: FAIL (high-severity findings)`, then the limits line (static, nothing measured).
- Name the run: `python3 -I scripts/perf_review.py --target <repo> [--baseline <findings.csv>] --findings findings.csv --report report.md`.
- **The request names a repo, branch or file but its code is not in the conversation**: write the review skeleton — Summary table with the ten rules and counts `[TO BE BASELINED — owner: author, from the repo]`, the per-rule checklist above, and the gate line unfilled. End with one line asking for the repo path (and the earlier `findings.csv` if debt was recorded). Never guess findings.
- **Asked to downgrade or "sign off" with highs open**: decline in one line; offer the defensible paths — fix the high rows now (named columns, `.range`, `.in()`/embedded select), or record them as a baseline so only new highs gate.

## Starting points
- **New** — a repo is reviewed against all ten rules; any high finding (N+1, `select("*")`, unbounded read) fails the gate.
- **Existing** — add `baseline` (the `findings.csv` of an earlier run): each finding is marked known or new, the gate fails only on new high findings, known debt stays listed and baseline items no longer found are reported as resolved.

## When to use
- Before a launch, campaign, term start or any expected traffic multiple; before scaling the Supabase plan "just in case".
- "Why is this page slow", "find the N+1s", "check our queries", "are we bundling the chart library into every page".
- In CI as a required check: exit 1 on new high findings.
- NOT for: stack conventions, layering and where code lives (`nextjs-enterprise-conventions`), measuring latency, errors or query time in production (`observability-setup`), schema and indexes (`supabase-schema-rls`), applying the fixes (`safe-fix`).

## Inputs required
| Input | Required | Source | If missing |
|---|---|---|---|
| `target` | yes | Next.js repo root (`app/`, `components/`, `lib/`, `server/`) | runner exits 2 and writes `needs_input.json` |
| `baseline` | no | `findings.csv` from an earlier run (recorded debt) | every finding is `new`; any high finding fails the gate |

## Procedure
1. **Scan** (`scripts/perf_review.py`): every `.ts/.tsx/.js/.jsx/.mjs` under `target`, skipping `node_modules`, `.next`, `out`, `dist`, `build`, `coverage`, tests.
2. **Detect** PF1–PF10 per file as in the conversation procedure; rules, rationale and fixes in `references/perf-rules.md`.
3. **Baseline** (optional): mark known/new, list resolved.
4. **Write** `findings.csv` and `report.md`; print one line per finding and the summary line.
5. **Gate**: exit 1 when any new high-severity finding remains; 0 otherwise.

## Output
| Artifact | Form |
|---|---|
| `findings.csv` | `rule,file,line,snippet,severity,status` — sorted by file, line, rule |
| `report.md` | Summary (per-rule counts), Findings table, Baseline (when given), Rules with fix hints |

## Self-check
- [ ] Every finding has rule, `file:line`, severity and a snippet copied from the source
- [ ] PF1/PF3/PF4 are high; PF2/PF5–PF10 are medium; nothing else is invented
- [ ] A clean repo yields zero findings and `Gate: PASS`; the same input twice yields byte-identical outputs
- [ ] With a baseline, known debt is listed but does not gate; resolved rows are named
- [ ] The report states that nothing was executed or measured

## References
- `references/perf-rules.md` — PF1–PF10: id, what is matched, rationale, fix, known false positives and limits
- `scripts/perf_review.py` — scanner, baseline matcher, report writer and gate (argparse; stdlib)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/perf-review-runner --input <name>=<value> … --out <dir>` (see `--explain build/perf-review-runner`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. The review step exits 1 on any new high-severity finding, so a repo with an N+1, `select("*")` or unbounded list read fails the run by design; fix the findings in code (or record them in a baseline as known debt), then re-run.

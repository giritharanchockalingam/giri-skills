---
name: tech-debt-audit-runner
description: Use when joining or inheriting an unfamiliar TypeScript or JavaScript Next.js codebase and the question is where the architecture and maintainability debt is — "audit this repo for tech debt", "what should we refactor first", "map this codebase before we touch it", "is this safe to build on". Produces findings.csv, report.md and refactor-plan.md (Summary, Architecture map inferred from imports, Priorities with effort/risk/owner, Sequencing) from eight static rules — duplicate function bodies, god files, circular imports, layering violations, dead exports, TODO/FIXME/HACK counts, `any` density, lib/ modules without tests — each with file:line and severity; a baseline findings.csv marks known debt and the gate fails only on new high findings (cycles, layering, files above 800 lines). Not for reviewing one diff or PR (use code-review-runner) or fixing a reported bug (use safe-fix).
license: MIT
metadata:
  domain: build
  adlc_stage: improve
  version: 0.2.1
  author: giri-skills
  agent:
    inputs:
      - {name: target, type: dir, required: true, from: "repo root of the TypeScript or JavaScript Next.js codebase (app/, components/, lib/, server/, tests/; .js/.jsx audited like .ts/.tsx)"}
      - {name: baseline, type: csv, required: false, from: "findings.csv from an earlier audit — the recorded debt; known findings are listed but only new high-severity ones fail the gate"}
      - {name: owners, type: csv, required: false, from: "owners csv (layout: assets/owners-template.csv): path_prefix,owner for the plan's Owner column; unmatched items read [TO BE BASELINED — owner: tech lead]"}
    run:
      - {step: audit, kind: script, cmd: "python3 -I scripts/audit_debt.py --target {target} [--baseline {baseline}] [--owners {owners}] --findings {out}/findings.csv --report {out}/report.md --plan {out}/refactor-plan.md"}
    outputs:
      - {path: "{out}/findings.csv", checks: [exists, csv:[rule,file,line,snippet,severity,status], cmd:"python3 -I scripts/audit_debt.py --verify {path}"]}
      - {path: "{out}/report.md", checks: [exists, sections:["Summary","Findings","Rules"], contains:"Gate:"]}
      - {path: "{out}/refactor-plan.md", checks: [exists, sections:["Summary","Architecture map","Priorities","Sequencing"], no_unowned_tbd, contains:"Phase 1"]}
    modes:
      existing: {case: agent-mode-existing, bring: "the repo you inherited and, if you have it, last audit's findings"}
---

# tech-debt-audit-runner

## In a conversation: audit the codebase now
**Never**
- Never report a finding for code you have not seen: no file:line in the conversation or on disk means no finding. Fabricated findings are worse than none — they send a team refactoring the wrong file.
- Never fail the gate on medium or low debt: the gate is **exit 1 only on a new high finding** (TD3 circular import, TD4 layering violation, TD2 god file above 800 lines). A god file of 401–800 lines, duplicates, dead exports, `any` hot spots, missing tests and TODOs are reported, prioritised and sequenced — they do not block.
- Never invent an owner, an effort estimate for the codebase, or a TODO's age: owners come from the owners csv or read `[TO BE BASELINED — owner: tech lead]`; effort S/M/L is the per-rule default and says so; TODO age is "unknown (no history read)".
- Never mark recorded debt as new or new debt as known: with a baseline, line-level findings match on rule + file + snippet, file-level ones (TD2, TD6, TD7, TD8) on rule + file; everything else is new; baseline rows not found again are resolved.

**Procedure (from `scripts/audit_debt.py`; work it by hand on the files you are given)**
1. Inventory: list the `.ts/.tsx/.js/.jsx/.mjs` files — a JavaScript repo (no `tsconfig.json`) is audited exactly like a TypeScript one — and set aside test files (`tests/`, `__tests__/`, `*.test.*`, `*.spec.*`) and `evals/` as importers only (they keep symbols alive; they are never audited).
2. Import graph: for every file, the relative (`./`, `../`) and `@/` imports it resolves to, with the symbols imported (`*` for namespace / `export *` / dynamic imports).
3. Rules, each with file:line, severity and a one-line snippet — TD1 duplicate-logic (same normalised body ≥ 6 lines in two files; medium), TD2 god-file (> 400 lines or > 12 exports; high above 800 lines), TD3 circular-import (a cycle; high), TD4 layering-violation (`app/` importing a sibling route folder; `lib/` importing `app/` or `components/`; high), TD5 dead-export (exported, never imported; excluded: `index` re-exports, root `middleware`/`instrumentation`/`*.config.*`, and the exports Next.js consumes from `app/**` special files — `page layout template loading error global-error not-found default route manifest robots sitemap opengraph-image twitter-image icon apple-icon` — full table in `references/debt-rules.md` § TD5 exclusion list; medium), TD6 todo-comment (count per file; low), TD7 any-density (> 5 `any` in a file; medium), TD8 missing-tests (`lib/` module with no `tests/**<stem>*` or `<stem>.test|spec.*`; medium). Thresholds and fix hints: `references/debt-rules.md`.
4. Baseline, if given: mark each finding known/new, list resolved rows.
5. Architecture map: per top-level folder — files, folders it imports, folders that import it, and the inferred responsibility (entry surface / intermediate layer / foundation, plus the Next.js folder meaning).
6. Plan: Priorities ordered severity → new before known → rule, each row finding → file:line → effort (TD1 S, TD2 L, TD3 M, TD4 S, TD5 S, TD6 S, TD7 M, TD8 M) → risk (= severity) → status → owner; Sequencing in four phases — restore the dependency direction (TD3, TD4), split the god files (TD2), one implementation under test (TD1, TD8), trim the surface (TD5, TD7, TD6).

**Reply layout**: the gate line first (`Gate: PASS` / `Gate: FAIL (new high-severity findings)` with counts: N high, N medium, N low; with a baseline also N new, N known, N resolved), then the findings table (rule, file:line, severity, status, snippet), then the three `refactor-plan.md` sections — **Architecture map**, **Priorities**, **Sequencing** — and the **Rules** list with the thresholds used. Name the run: `python3 -I scripts/audit_debt.py --target <repo> [--baseline findings.csv] [--owners owners.csv] --findings findings.csv --report report.md --plan refactor-plan.md`.
- **The request pastes a few files or an import list, not the whole repo**: audit exactly those files against every rule, say which rules could not be judged (TD5 and TD8 need the whole repo to know what imports a symbol or where tests live; TD3/TD4 only within the pasted set), and mark those `[TO BE BASELINED — owner: tech lead, from the full repo]`.
- **The request names a repo, a baseline or an owners file that is not in the conversation**: write the audit skeleton now — the eight rules with their thresholds as the checklist, the three plan sections with their headings, `Gate: [TO BE BASELINED — owner: tech lead, from the audit run]` — and end with one line asking for the repo path (and the earlier `findings.csv` if they have recorded debt). Never print a gate verdict or a findings table for a repo you have not read.
- **Asked to "just sign off" or to drop the cycle so the gate passes**: decline in one line — a new cycle or layering violation fails the gate regardless of deadline; the defensible path is to record existing debt in a baseline (known debt does not gate) and fix the new high items, or break the cycle (extract the shared piece, `import type`, invert the edge) and re-run.
- **Asked for the plan with owners and sprint estimates filled in**: owners only from the owners csv or the conversation, otherwise `[TO BE BASELINED — owner: tech lead]`; effort stays the per-rule S/M/L default labelled as such; no dates, no story points.

## Starting points
- **Existing** — the repo you inherited is read as it is: import graph, eight rules, architecture map, prioritised and sequenced plan. Add `baseline` (an earlier `findings.csv`) and the gate fails only on new high findings, known debt stays listed, resolved items are reported; add `owners` to fill the Owner column.
- Only for existing: a tech-debt audit always starts from code that already exists; there is nothing to audit from scratch.

## When to use
- First week on an inherited or acquired TypeScript or JavaScript Next.js codebase; before a modernisation estimate; before committing to build on a legacy module.
- A recurring health check: run with last quarter's `findings.csv` as the baseline and track new vs resolved.
- In CI as a ratchet: the gate fails only when a change adds a cycle, a layering violation or a file above 800 lines.
- NOT for: one diff or PR (`code-review-runner`), a reported bug with a repro (`safe-fix`), stack conventions on new code (`nextjs-enterprise-conventions`), vulnerabilities (`security-review`).

## Inputs required
| Input | Required | Source | If missing |
|---|---|---|---|
| `target` | yes | repo root directory | ask once for the path; do not audit an imagined repo |
| `baseline` | no | `findings.csv` from an earlier run | every finding is `new`; the gate fails on any high finding |
| `owners` | no | `path_prefix,owner` csv (`assets/owners-template.csv`) | Owner column reads `[TO BE BASELINED — owner: tech lead]` |

## Procedure
1. **Inventory and graph** (`scripts/audit_debt.py`): source files minus skipped folders; test files as importers only; import edges with symbol sets.
2. **Rules** TD1–TD8 (`references/debt-rules.md`), each finding with rule, file, line, snippet, severity.
3. **Baseline**: known / new / resolved per the matching keys above.
4. **Write** `findings.csv`, `report.md` (Summary, Findings, Baseline when given, Rules) and `refactor-plan.md` (Summary, Architecture map, Priorities, Sequencing).
5. **Gate**: exit 1 only on a new high finding; outputs are always written.
6. Walk the plan with the team: confirm each Phase 1 item against the code, assign the `[TO BE BASELINED]` owners, replace the default effort with real estimates, then re-run with the new `findings.csv` as the baseline.

## Output
- `findings.csv` — `rule,file,line,snippet,severity,status`, sorted by file, line, rule.
- `report.md` — Summary (count per rule), Findings, Baseline (with `baseline`), Rules.
- `refactor-plan.md` — Summary, Architecture map (folder → files → imports from → imported by → inferred responsibility), Priorities (ordered: finding → file:line → effort → risk → status → owner), Sequencing (four phases).

## Self-check
- [ ] Every finding has rule, file:line, severity and a snippet; no finding for a file that was not read
- [ ] Gate verdict matches the rule: new high only (TD3, TD4, TD2 > 800 lines)
- [ ] With a baseline: known / new / resolved counts in the Summary line add up
- [ ] Every Priorities row has an owner — a named role from the owners csv or the `[TO BE BASELINED — owner: tech lead]` marker
- [ ] Architecture map lists every top-level folder once with its import direction
- [ ] Limits stated: static only, no history (TODO age unknown), `@/` and relative imports only, effort is a per-rule default

## References
- `references/debt-rules.md` — rule ids, rationale, how each is checked, fix hints, false positives, limits
- `assets/owners-template.csv` — owners csv layout
- `scripts/audit_debt.py` — the audit (argparse; stdlib; deterministic); `--verify findings.csv` re-checks an output

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/tech-debt-audit-runner --input <name>=<value> … --out <dir>` (see `--explain build/tech-debt-audit-runner`). Report the `run.json` results; do not hand-write the deliverables the script produces. The audit step exits 1 on any new high-severity finding, so a repo with a new cycle, layering violation or 800+ line file fails the run by design; break the cycle or record the debt in a baseline, then re-run.

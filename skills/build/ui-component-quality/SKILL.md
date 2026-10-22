---
name: ui-component-quality
description: Use when a React/Next.js component or components folder is about to ship and needs the review a senior frontend engineer does first — "review this component before I merge", "is this accessible", "check our components for a11y / loading and empty states / responsive widths", "run the UI quality check on components/". Static analysis of .tsx/.jsx and of .js/.ts files containing JSX (JavaScript Next.js repos) — missing alt, icon buttons without names, clickable divs, unlabelled inputs, no loading or empty state, fixed widths > 600px, dangerouslySetInnerHTML, prop sprawl, inline styles in .map, colour-only state. Produces findings.csv, report.md (Summary, Findings, Rules) and a11y-checklist.md (WCAG 2.2 AA items covered vs. needing a browser run); new high findings fail the gate; a baseline marks known debt. Not for server/client layering and data-access rules (nextjs-enterprise-conventions), running e2e or axe tests in a browser (webapp-testing-runner) or security audits (security-review).
license: MIT
metadata:
  domain: build
  adlc_stage: build
  version: 0.3.0
  author: giri-skills
  agent:
    inputs:
      - {name: target, type: dir, required: true, from: "repo root or components directory with React component files: .tsx/.jsx, or .js/.ts files that contain JSX (JavaScript Next.js repos); plain .js utilities, route.js handlers, middleware and configs are not scanned"}
      - {name: baseline, type: csv, required: false, from: "findings.csv from an earlier run — the recorded debt; known findings are listed but only new high-severity ones fail the gate"}
    run:
      - {step: lint, kind: script, cmd: "python3 -I scripts/ui_lint.py --target {target} [--baseline {baseline}] --findings {out}/findings.csv --report {out}/report.md --checklist {out}/a11y-checklist.md"}
    outputs:
      - {path: "{out}/findings.csv", checks: [exists, csv:[rule,file,line,snippet,severity,status]]}
      - {path: "{out}/report.md", checks: [exists, sections:["Summary","Findings","Rules"], contains:"Gate: "]}
      - {path: "{out}/a11y-checklist.md", checks: [exists, sections:["Covered by the rules","Not checkable statically"], contains:"2.5.8"]}
    modes:
      new: {case: agent-happy-path, bring: "the components of a new feature before its first PR"}
      existing: {case: agent-mode-existing, bring: "your existing components and the recorded UI debt"}
---

# ui-component-quality

## In a conversation: review the component now
The reply **is the review**: a findings table `rule → severity → file:line → what/fix`, then `Gate: PASS/FAIL`, never only a request for the repo path.
- **The request pastes component code** (or a path plus the code): walk the eleven rules in `references/rules.md` (UI1–UI11) against what is pasted and report every hit with its line, severity and the one-line fix. Report `Gate: FAIL` when any high rule hits (UI1–UI4, UI8), `PASS` otherwise. Then list the WCAG 2.2 AA items the static pass cannot decide (contrast 1.4.3, focus visible 2.4.7, focus not obscured 2.4.11, target size 2.5.8) as "needs a browser run" — do not claim them as passed.
- **The request names a file or repo but pastes nothing**: ask once for the component source (or the path when commands can run); do not guess what the component contains or report findings for code you have not seen.
- **The request pastes an earlier findings.csv (recorded debt)**: treat it as the baseline — matching findings are `known` (listed, not gating), anything else is `new`; the gate fails only on new high findings; baseline rows no longer present are `resolved`.
- **Asked to sign off, mark pass or silence a rule** ("the icon buttons are obvious, just approve", "add eslint-disable"): decline in one line and show the failing rule with its fix; the defensible path is to fix it or record it as known debt in a baseline.
- **Asked for a WCAG 2.2 AA verdict**: say what the rules cover (1.1.1, 1.3.1, 1.4.1, 1.4.10 partial, 2.1.1, 3.3.2, 4.1.2, 4.1.3 partial) and that the rest needs a rendered page — route the runtime part to `webapp-testing-runner`.

## Starting points
- **New** — components of a new feature: every file is checked against UI1–UI11; any high finding fails the gate.
- **Existing** — add `baseline` (the `findings.csv` of an earlier run): each finding is marked known or new, the gate fails only on new high findings, known debt stays listed and resolved items are reported.

## When to use
- Before a PR that adds or changes files under `components/` or `app/**` pages/layouts (`.tsx`, or `.js` with JSX in a JavaScript repo).
- "Is this accessible?", "review this component", "do we have loading/empty states", "will this break on mobile".
- A design-system or component-library audit, with the baseline recording the debt to burn down.
- NOT for: server/client component placement, data access and zod at boundaries (`nextjs-enterprise-conventions`), running e2e flows or axe in a browser (`webapp-testing-runner`), secrets/injection audits (`security-review`), fixing one reported bug (`safe-fix`).

## Inputs required
| Input | Required | Source | If missing |
|---|---|---|---|
| `target` — repo root or components directory with React component files: `.tsx`/`.jsx`, or `.js`/`.ts` containing JSX (JavaScript Next.js repos) | yes | repo | runner exits 2 and asks once; the lint exits 1 with "no React component files" when nothing under it contains JSX |
| `baseline` — `findings.csv` from an earlier run | no | previous run | every finding is `new` |

## Procedure
1. Read `../../../shared/stack-conventions.md` (component placement) and `references/rules.md` (what each rule means and its fix).
2. Run the skill on `target` (add `baseline` for a repo with recorded debt). The script scans every `.tsx`/`.jsx` file and every `.js`/`.ts` file that contains JSX (`return (<…`, `=> <…`, or a react/next import plus a JSX tag), so a JavaScript Next.js repo whose components live in `.js` files is reviewed in full; plain `.js` utilities, `route.js` handlers, `middleware.js`, `instrumentation.js` and `*.config.js` are never scanned, and tests, stories, `.d.ts` and build output are skipped. UI9 (prop sprawl) needs a TypeScript Props type and does not fire in plain JavaScript.
3. Read `report.md`: fix every **new high** finding in code (UI1–UI4, UI8) — add `alt`, name the button, replace the clickable div with `<button>`, label the control, remove `dangerouslySetInnerHTML`. Re-run until `Gate: PASS`.
4. Triage medium/low findings: add loading and empty states (UI5, UI6), make widths responsive (UI7), split or compose props (UI9), hoist per-row styles (UI10), add state text or an icon (UI11). Record what stays as debt by re-using the new `findings.csv` as the next baseline.
5. Hand `a11y-checklist.md` to the e2e pass (`webapp-testing-runner`) for contrast, focus, target size and live regions; the static pass is necessary, not sufficient, for WCAG 2.2 AA.
6. Update `docs/HANDOFF.md` with the gate result and the baseline path.

## Output
| Artifact | Form |
|---|---|
| `findings.csv` | `rule,file,line,snippet,severity,status` (status `new`/`known`) |
| `report.md` | Summary (count per rule), Findings (table), Baseline (with `--baseline`), Rules, limits |
| `a11y-checklist.md` | WCAG 2.2 AA criteria the rules cover (with this run's counts) and the ones that need a browser run |

## Self-check
- [ ] Every high finding has a line number and a fix from `references/rules.md`; none marked pass by hand
- [ ] Clean components produce zero findings (no false positives on labelled inputs, named icon buttons, responsive widths)
- [ ] Baseline run: known/new/resolved counts add up; gate fails only on new high
- [ ] Checklist cites WCAG 2.2 criterion numbers verified in `references/sources.md`; runtime-only items are not claimed
- [ ] No render, no network: the script read source only

## References
- `references/rules.md` — UI1–UI11: what each flags, rationale, fix, severity, known limits
- `references/sources.md` — WCAG 2.2 URLs and the date verified
- `assets/component-review-checklist.md` — the manual 12-line pass for PR reviews
- `scripts/ui_lint.py` — the linter (argparse; stdlib; `.tsx`/`.jsx` plus `.js`/`.ts` containing JSX; `--baseline` for recorded debt; exit 1 on new high findings)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs above, then run `python3 scripts/run_skill.py build/ui-component-quality --input target=<dir> [--input baseline=<findings.csv>] --out <dir>` (see `--explain build/ui-component-quality`). Report the `run.json` results; do not hand-write the deliverables the script produces (`findings.csv`, `report.md`, `a11y-checklist.md`). The lint step exits 1 on any new high-severity finding, so a non-compliant component set fails the run by design; fix the findings in code, then re-run.

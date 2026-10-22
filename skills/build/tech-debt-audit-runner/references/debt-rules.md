# Debt rules — what the audit flags, why, and how to fix it

`scripts/audit_debt.py` is static analysis only: it reads source files, never runs the app, never reads git history, never touches the network. Every rule below is checkable by hand with the method in the "How it is checked" column; thresholds are constants at the top of the script, echoed in the report.

## Scope
- Files: `.ts .tsx .js .jsx .mjs` under the target, skipping `node_modules .next out dist build coverage .git` and `*.d.ts`.
- Test files (`tests/ test/ __tests__/ spec/` folders, `*.test.* *.spec.*`) join the import graph — an import from a test counts as a use for TD5 and as coverage for TD8 — but are not audited for TD1, TD2, TD6, TD7.
- Import graph: relative imports (`./`, `../`) and the `@/` alias (repo root). Package imports are ignored. `import X`, `import { a as b }`, `import * as ns`, `import type`, `export { a } from`, `export * from`, `import("…")` and `require("…")` are all parsed.

## Rules
| Rule | Severity | How it is checked | Fix hint |
|---|---|---|---|
| TD1 duplicate-logic | medium | Each `function name(…) {` / `const name = (…) => {` body is comment-stripped, whitespace-normalised, blank and brace-only lines dropped; bodies of ≥ 6 lines are sha256-hashed and compared across files. One finding per extra copy, on the later file in path order; the snippet names the original. | Keep the copy in `lib/` (or the lowest layer that both callers may import), delete the other, make the survivor's test cover both call sites. |
| TD2 god-file | medium; **high** above 800 lines | Line count > 400 or exported symbols > 12. Exports counted: `export function/class/const/let/var/type/interface/enum`, `export default`, `export { a, b }`. | Split by responsibility behind the existing exports (an `index.ts` re-export keeps callers unchanged); one move per PR; characterisation test first. |
| TD3 circular-import | high | Tarjan strongly-connected components over the import graph of audited files. One finding per cycle, on the alphabetically first file, at its import line; the snippet lists the cycle. | Extract the shared piece (type, constant, helper) into a third module both import, or invert one edge via dependency injection / a callback parameter. Type-only cycles: use `import type`. |
| TD4 layering-violation | high | A file under `lib/` importing a module under `app/` or `components/`; a file under `app/` importing a module under `app/` that is neither in its own folder subtree, nor in an ancestor folder, nor in a private (`_`-prefixed, non-route) folder — i.e. a sibling route folder. | Move the shared helper to `lib/` (pure) or `server/` (server-side) and import it from both routes; `lib/` must never know about UI or routes. |
| TD5 dead-export | medium | An exported symbol that no other file imports by name (a `*`/namespace import or `export *` of the module counts as using everything). Excluded: `index.*` files, root config/`middleware`/`instrumentation` files, everything in `app/**/route.*`, and the framework exports of `app/**/page|layout|loading|error|not-found|template|default.*` (`default`, `metadata`, `generateMetadata`, `generateStaticParams`, `dynamic`, `revalidate`, `runtime`, …). | Delete it, or un-export it if it is only used inside the file. If it is a public package surface, say so in a comment and record it as known debt in the baseline. |
| TD6 todo-comment | low | `TODO`, `FIXME` or `HACK` at the start of a `//`, `/*`, `*` or `#` comment. One finding per file with the count; the age is unknown because no history is read. | Turn each into a ticket (`TODO(ABC-123)`) or delete it; `code-review-runner` CR-TODO then keeps new owner-less ones out. |
| TD7 any-density | medium | Count of the `any` keyword in comment- and string-stripped text of a `.ts/.tsx` file; > 5 flags the file. | Type the boundaries first (`unknown` + a zod/type guard at the entry point), then let inference remove the rest; keep `any` only with an `// eslint-disable-next-line` and a reason. |
| TD8 missing-tests | medium | For each `lib/**/*.ts(x)` (not `index`): no file under `tests/ test/ __tests__/ spec/` whose name contains the module stem, and no `<stem>.test|spec.*` sibling in the same folder. | Add a unit test file named after the module; for data-access modules, test against a fake client. Do this before any TD1/TD2 refactor that touches the module. |

## Severity and the gate
- `high` = TD3, TD4, TD2 above 800 lines. The script exits 1 only when a **new** high finding exists; medium and low findings never gate.
- With `--baseline findings.csv` (an earlier run), a finding is `known` when it matches a baseline row: line-level rules (TD1, TD3, TD4, TD5) on rule + file + snippet, file-level rules (TD2, TD6, TD7, TD8) on rule + file — so a god file that grew by ten lines is still the same recorded debt. Baseline rows not found again are listed as resolved.

## Known false positives → what to do
- TD1 on generated code or intentionally parallel adapters: record them in the baseline; the rule is a judgement prompt, not a verdict.
- TD4 for a Next.js `app/` tree that shares a private `_components/` or `_lib/` folder: `_`-prefixed folders are not routes, so `app/_components/nav` imported from `app/(app)/x/page.tsx` does not fire; ancestor folders (`app/providers.tsx`) do not fire either; only sibling route folders do.
- TD5 for symbols imported through a path alias other than `@/` (e.g. `~/`): the graph does not resolve them, so they look unused. Add the alias to `resolve_import` or record the findings as known.
- TD7 in a file that wraps an untyped third-party SDK: type the wrapper's public surface and accept the internal `any` as known debt.
- TD8 for `lib/` modules that are pure types or constants: there is nothing to test; record as known.

## Limits
- No type information: re-exports through computed names, `module.exports`, barrel files in `node_modules` and path aliases other than `@/` are not followed.
- Duplicate detection is per function body, not per block; methods inside classes are not compared.
- The architecture map's "responsibility" is inferred from import direction and folder name only; it is a starting hypothesis to confirm with the team.
- Effort S/M/L in the plan is a per-rule default (TD1 S, TD2 L, TD3 M, TD4 S, TD5 S, TD6 S, TD7 M, TD8 M), not an estimate of your codebase; replace it in the plan once each item is looked at.

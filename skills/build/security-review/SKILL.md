---
name: security-review
description: Use pre-merge or pre-release to review a diff, PR or feature for security defects in the Next.js + Supabase + Vercel stack. Produces a reasoning-based review (threat model per change: authz, injection, secrets, RLS bypass, SSRF, IDOR, mass assignment, server-action pitfalls) with severity-rated findings and fixes applied in code, not a generic checklist. Wraps the sentry security-review skill when installed. Not for schema authoring (use supabase-schema-rls) or bug fixing without a security angle (use safe-fix).
license: MIT
metadata:
  domain: build
  adlc_stage: govern
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: diff, type: file, required: true, from: "unified diff of the change (`git diff main...HEAD > change.patch`)"}
      - {name: target, type: dir, required: false, from: "repo root to scan in full as well (callers, policies)"}
    run:
      - {step: scan, kind: script, cmd: "python3 -I scripts/scan.py --diff {diff} [--target {target}] --findings {out}/findings.csv --report {out}/review.md"}
      - {step: review, kind: llm, template: assets/review-report.md, context: ["{out}/findings.csv", "{out}/review.md", "references/review-method.md", "references/severity-rubric.md"], out: "{out}/security-review.md"}
    outputs:
      - {path: "{out}/findings.csv", checks: [exists, csv:[id,category,severity,file,line,evidence,recommendation], cmd:"python3 -I scripts/scan.py --gate {path}"]}
      - {path: "{out}/review.md", checks: [exists, sections:["Findings","Surfaces scanned","Method"]]}
      - {path: "{out}/security-review.md", checks: [exists, sections:["Findings","Threat model","Verification"]]}
---

# security-review

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/security-review --input <name>=<value> … --out <dir>` (see `--explain build/security-review`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. The scan always writes its findings and the review step reasons on them; the gate check then fails the run (exit 1) when any critical/high finding remains, so a risky diff is reported, never waved through.

## When to use
- "Review this before merge", "is this safe", PR touching auth, tenancy, server actions, route handlers, migrations, env, file upload, external calls.
- Release gate: every tag.
- NOT for: writing policies (`supabase-schema-rls`), general code quality (`nextjs-enterprise-conventions`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Diff / PR / file list | yes | user / `git diff main...HEAD` |
| Trust model: roles, tenancy, public endpoints | yes | `docs/SPEC.md`, RBAC matrix — ask once if absent |
| Repo access for reading callers and policies | yes | repo |

If a required input is missing, ask for it once; do not guess.

## Procedure
1. Read `../../../shared/stack-conventions.md` (Auth, Secrets, Multi-tenant rows), `../../../shared/token-efficiency.md`, and `../../../shared/quality-bar.md`.
2. **Scope.** List changed files grouped by surface: server actions, route handlers, middleware, migrations/policies, client components, env/CI, external calls. Note what each surface trusts. *(gate: plan)*
3. **Threat model per change.** If the upstream skill `security-review` is installed (see VENDORED.md), invoke it for this step with the stack context from `references/stack-specifics.md`; otherwise follow `references/review-method.md`: for each change ask who can reach it, what they control, what it touches, what the worst outcome is, which control stops it, and whether that control is actually in the diff or only assumed.
4. **Trace, don't pattern-match.** For every finding, follow the data from entry point to sink and cite file:line at each hop. A finding without a trace is a question, not a finding.
5. **Rate** each finding with `references/severity-rubric.md` (Critical/High/Medium/Low/Info) using reachability × impact. Post the findings table; agree fixes with the user before changing code. *(gate: plan→approve)*
6. **Fix in code** — minimal diffs, following `safe-fix` rules; add a regression test per Critical/High (negative case that fails before the fix). *(gate: build→test)*
7. **Verify.** Re-run the trace for each fixed finding, run `rls_lint.py`, full unit suite, lint. Confirm no new surface was opened by the fix. *(gate: test→verify)*
8. Report with `assets/review-report.md`; update `docs/HANDOFF.md`.

## Output
| Artifact | Form |
|---|---|
| Findings table | severity, title, trace (entry → sink), impact, fix, test |
| Fixes | minimal diffs |
| Regression tests | `tests/**` |
| Report | `docs/security/<date>-<scope>.md` from `assets/review-report.md` |

## Self-check
- [ ] Every finding has an entry→sink trace with file:line
- [ ] Every server action and route handler in scope: input parsed, authz checked, tenant from session
- [ ] RLS: new/changed tables have policies; `with check` on writes; no `user_metadata` claims
- [ ] No secret in client bundle, logs, or repo; `NEXT_PUBLIC_` audit done
- [ ] External calls: allow-listed hosts, timeouts, no user-controlled URLs (SSRF)
- [ ] Critical/High have a failing-then-passing regression test
- [ ] Fix diffs touched only the vulnerable path (no collateral)

## References
- `references/review-method.md` — threat-model questions per change type, trace discipline (fallback for sentry)
- `references/stack-specifics.md` — Next.js server actions, Supabase RLS/service-role, Vercel env pitfalls
- `references/severity-rubric.md` — rating rules and SLA
- `assets/review-report.md` — report template
- `scripts/scan.py` — diff/repo scanner for SEC1–SEC6 (auth, injection, secrets, SSRF, XSS, RLS bypass) → findings.csv; `--gate` fails on critical/high

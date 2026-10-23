---
name: security-review
description: Use pre-merge or pre-release to security-review a diff, PR or feature in the Next.js + Supabase + Vercel stack — "security review this diff" (even one that only renames a CSS class or edits a README), "review this PR before merge", "is our app secure?", a diff with a server action, route handler, zod validation, query helper, auth, tenancy, the admin/service-role client or an RLS bypass, or a diff reviewed with the repository code around it. Produces a traced review (surface inventory, threat model per change: authz, injection, secrets, RLS bypass, SSRF, IDOR, mass assignment, server-action pitfalls) with severity-rated findings, fixes in code and a gate that fails on critical/high. Wraps the sentry security-review skill when installed. Do not use for a generic lint-style first pass with no security question (code-review-runner), a bug with a repro and no security angle (safe-fix) or schema authoring (supabase-schema-rls).
license: MIT
metadata:
  domain: build
  adlc_stage: govern
  version: 0.2.0
  author: giri-skills
  fits:
    stacks: [any]
    request_kinds: [feature, fix, hardening, migration, greenfield]
  agent:
    inputs:
      - {name: diff, type: file, required: true, from: "unified diff of the change (`git diff main...HEAD > change.patch`)"}
      - {name: target, type: dir, required: false, from: "repo root to scan in full as well (callers, policies)"}
      - {name: draft_only, type: flag, required: false, flag: "--draft-only", from: "true to skip the model review step: security-review.md is written from the scan, labelled as a draft"}
    run:
      - {step: scan, kind: script, cmd: "python3 -I scripts/scan.py --diff {diff} [--target {target}] --findings {out}/findings.csv --report {out}/review.md --final {out}/security-review.md {draft_only}"}
      - {step: review, kind: llm, template: assets/review-report.md, context: ["{out}/findings.csv", "{out}/review.md", "references/review-method.md", "references/severity-rubric.md"], out: "{out}/security-review.md", skip_if_present: [draft_only]}
    outputs:
      - {path: "{out}/findings.csv", checks: [exists, csv:[id,category,severity,file,line,evidence,recommendation], cmd:"python3 -I scripts/scan.py --gate {path}"]}
      - {path: "{out}/review.md", checks: [exists, sections:["Findings","Surfaces scanned","Method"]]}
      - {path: "{out}/security-review.md", checks: [exists, sections:["Findings","Threat model","Verification"]]}
    modes:
      new: {case: agent-mode-new, bring: "the diff of a new feature"}
      existing: {case: agent-mode-existing, bring: "the diff and the existing repo it lands in"}
---

# security-review

## In a conversation: review now
- **The change is described or pasted** (a PR summary, a diff, a route handler, "takes tenantId from the query string and uses the admin client"): write the review **in this reply**. Start with the **surface inventory** (changed files grouped by surface: route handlers, server actions, middleware, policies, client components, env, external calls, and what each trusts), then the **findings table, worst first**: severity (reachability × impact, e.g. Critical = R2 × I3), title, trace entry → sink with file:line at each hop (`route.ts:12 → services/x.ts:30 → admin client → invoices`), impact, fix, test. For each Critical/High add a short exploit sketch and the fix in code: tenant from the session, the cookie-bound (RLS) client instead of the admin client, an authz guard, plus a negative regression test that fails before the fix. State "Report written from `assets/review-report.md` → `docs/security/<date>-<scope>.md`" and lay the reply out on its sections: Findings (worst first) · Threat model record · Surfaces reviewed · Verification · Out of scope / parked.
- **The diff lands in an existing repo and the user wants the surrounding code checked**: review the diff and, in the same table, the callers, handlers and components it touches — name each file reviewed so the threat-model record shows full coverage; existing issues (e.g. `dangerouslySetInnerHTML` on content from the database) are rated like new ones and marked "existing".
- **Nothing security-relevant changed** (CSS, README, copy): line 1 "No security-relevant surface changed." then the surface inventory table that proves it (`| File | Surface | Trusts | Security-relevant? |`, every surface category listed as "none"). Do not invent generic findings (rate limiting, headers) the change does not touch.
- **No diff, PR or scope at all** ("is our app secure?", "review my change"): ask once for the diff or PR and the trust model (roles, tenancy, public endpoints). Do not produce a generic checklist.
- **A diff file is attached**: name the command and outputs first — `python3 -I scripts/scan.py --diff change.patch [--target <repo>] --findings findings.csv --report review.md --final security-review.md` — then the result: findings by severity (or "no critical/high findings"), the gate line (`scan.py --gate findings.csv`: "gate passes (exit 0)" or "gate fails (exit 1): critical/high remains"), and the review filled from the findings (surfaces scanned, threat model, verification). A clean diff (validated server action, parameterised query) is not padded with findings.
- **Asked to approve with a known secret or bypass left in** ("the token is fine to keep in code"): the finding stays Critical/High and the review is not approved; give the fix (move the secret to server env, rotate it).

## Starting points
- **New** — the diff of a new feature is scanned on its added lines; the model step writes the traced review, or with `draft_only` the review record is written from the scan alone, labelled as a draft.
- **Existing** — add `target` (the repo the change lands in): the existing code is scanned in full as well, so callers, handlers and components around the change are covered, and each file appears in the threat-model record.

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

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/security-review --input <name>=<value> … --out <dir>` (see `--explain build/security-review`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. The scan always writes its findings and the review step reasons on them; the gate check then fails the run (exit 1) when any critical/high finding remains, so a risky diff is reported, never waved through.

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
- `scripts/scan.py` — diff/repo scanner for SEC1–SEC6 (auth, injection, secrets, SSRF, XSS, RLS bypass) → findings.csv; `--gate` fails on critical/high; a service-role call in a handler marked `// rls-lint: allow — <reason>` on its line (the marker supabase-schema-rls's rls_lint.py honours; the observability kit's read-only deep health check) is an accepted exception, not a finding

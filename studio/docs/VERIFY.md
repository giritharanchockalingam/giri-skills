# Deployment verification checklist

What was verified offline in this build, and the exact browser/API steps to verify against the live deployment (Supabase project + Vercel). Tick each row; record the result.

## Already verified offline (this build)

| Check | How | Result |
|---|---|---|
| Migrations apply, twice (idempotent) | `tests/sql/run.sh` on local PostgreSQL 16 with a Supabase stand-in (`auth.users`, `auth.uid()`, anon/authenticated roles) | pass — 13 `sf_` tables, `public.profiles` untouched |
| RLS per role, immutability trigger, lifecycle transitions, stale approval, eval gate (outdated set, below threshold), publish/supersede/retire, API-key RPCs, idempotency, concurrency, budget, cross-tenant isolation | `tests/sql/test_sf.sql` (10 sections) | pass |
| Manifest validation, canonical hash determinism, input validation (required/unknown/schema/csv/flag/dir/fixture), output contract, API-key hashing, release-state logic, role matrix, import of all 40 repo skills | `npm run test:unit` (node --test, 9 tests) | pass |
| Python runtime: repo skill end-to-end without a model (llm step skipped and reported), needs_input, fixtures + case checks, traversal rejected, authored skill rendered to SKILL.md and run, round-trip through `skillmeta`, deadline enforced (1 s), environment scrubbed, provider usage + cost estimate from a mocked reply, bounded retries, handler auth (503 without secret, 401 wrong secret) | `npm run test:py` (pytest, 12 tests) | pass |
| `next build` (zero type errors), middleware redirects, API 401 JSON, honest setup state on `/login` without Supabase env | `npm run build`, `next start`, curl | pass |

## Needs deployment verification

Prerequisites: migrations `0001`, `0002` applied; env vars set (README → Setup); three test accounts (admin/author, reviewer, consumer).

### A. Sign-in and workspace
1. Open `/` signed out → redirected to `/login`. Sign up admin account → `/overview` shows **Create your workspace** → create → Overview with zero counts and honest empty states (no numbers invented).
2. Reload `/overview` → workspace persists (cookie `sf_ws` + membership row).
3. Administration → add reviewer and consumer by email with roles → roster shows emails (via `sf_member_directory`).

### B. Create / import and persistence
4. Skills → **Import from repository** → select `effort-estimator` → import → catalog shows it as Draft, source repository. Reload → still there.
5. Skill summary: purpose, inputs (wbs, rates, client, iterations), outputs with checks, steps (2 script + 1 llm), Evidence "not run", Needs → `anthropic` configured / not configured (matches whether `ANTHROPIC_API_KEY` is set). Primary action = **Test skill**.
6. Authoring → change `limits.timeout_s` to 40 → Save draft → message shows the new hash prefix; reload → persisted. Try invalid JSON in Inputs → Save disabled with listed problems.

### C. Test skill (server runtime)
7. Test → paste a CSV without header into `wbs` → **Test skill** → 400 `invalid_inputs` shown inline (no run created).
8. Leave `wbs` empty → 400 `missing_inputs` named.
9. Paste the fixture `skills/presales/effort-estimator/evals/fixtures/wbs.csv` and `rates.csv`, client `Acme` → run → redirected to `/runs/<id>`: steps `model-json`, `model-report` ok; `memo` skipped "no provider key" when the key is absent (status **Failed**, checks on the memo fail) or ran with provider `anthropic`, model string from the provider, usage tokens `provider-reported`, cost marked **estimate** when the key is present. Outputs `estimate.json`, `estimate.md` viewable/downloadable; logs present. Activity lists the run; reload persists.
10. Administration → Connections → **Check runtime** → reachable, Python version, bundle files, key presence. If `SF_RUNTIME_SECRET` is unset, Test view shows "runtime not configured" and runs refuse (never a fake success).
11. Timeout: Authoring → set `timeout_s` to 1 → Test → run status **Timed out**, error "deadline of 1s exceeded"; later steps absent. Restore 40.
12. Cancellation: only a `queued` run can be cancelled (UI says so); a running run completes.

### D. Evaluation
13. Evaluations (skill view) → imported cases listed (`agent-happy-path`, `agent-missing-wbs`, …) → **Run evaluation** → progress per case → history row with pass rate, per-case links to runs. With no key the happy-path case fails its memo check (honest); set `min_eval_pass_rate` accordingly or configure the key.
14. Edit a case → history row shows "outdated: cases changed since"; Release view's evaluation gate says to run again.

### E. Review, approval staleness, publish
15. Release → **Request review** (author) → Overview (reviewer account) lists it under Pending reviews → reviewer **Approve** with a note → status Approved; approval pinned to the hash. Reviewer who authored the version (non-admin) is refused.
16. Staleness: as author, Release on the Approved version → **Reopen for editing** → status Draft, Evidence still shows approval **valid** (hash unchanged). Authoring → change any field → Save → Release now shows approval **Stale** with both hashes, Publish disabled; SQL `select sf_publish_version('<id>')` returns "approval is stale". Request review → reviewer approves → valid again. Rejection path: reviewer **Reject** → Draft, history shows Rejected with the note.
17. Eval gate blocks publish: set `min_eval_pass_rate` 1.0 on a draft whose latest evaluation is < 100% → Publish disabled; calling `select sf_publish_version('<id>')` in SQL returns "evaluation gate not met". With a passing evaluation and valid approval → **Publish version** succeeds; previous published version → Superseded; skill shows Published vN; the published version's Authoring is read-only; Test as consumer account works; consumer cannot run a draft (403 message).
18. Published immutability: SQL `update sf_skill_versions set manifest='{}' where status='published'` → error from `sf_versions_guard`.

### F. Consumer API
19. Administration → API keys → create → key shown once; copy. `GET /api/v1/skills` lists only published skills; `GET /api/v1/skills/<slug>` returns the manifest; `POST …/run` with the fixture CSVs returns the run with `contract.ok`; same `Idempotency-Key` twice → `deduplicated: true`; `GET /api/v1/runs/<id>` returns it; wrong key → 401; after **Revoke** → 401. Draft-only skill → 409 `not_published`. Invalid input → 400 with `details`.
20. Policy: set max concurrency 1 and send two runs concurrently → second gets 429; set monthly budget below current estimated spend → 429 with the message; set allowed providers to `none` only → run fails with "policy does not allow provider".

### G. Authorization failures (UI)
21. Consumer account: Skills shows catalog without New/Import; `/skills/new` says authors only; Release view shows no lifecycle buttons; Test is allowed only on published versions; `/admin` shows account + audit only.
22. Reviewer account: cannot save manifests (form disabled, server returns role error if forced via devtools).

### H. Audit
23. Administration → Audit log shows workspace.create, membership.upsert, skill.import, version.update, run.create/finish, eval.start/finish, version.request_review/approve/publish, api_key.create/revoke, policy.update in order.

### I. Responsive / accessibility
24. Widths 1440, 1280, 768, 390, 360: no horizontal page overflow on Overview, Skills, skill Summary/Authoring/Test/Evaluations/Release, run detail, Administration (tables become card lists under 768px; wide tables scroll inside their card; top nav scrolls horizontally on phones with "Admin" short label). Drawers (Import) are full-screen sheets on mobile; Esc closes; focus returns.
25. Keyboard: tab through nav, catalog rows (Enter opens), forms; visible focus ring (flame outline); every action gives inline status text (role=status).
26. Long names: create a skill with a 150-character name and a 10,000-character instructions body → header wraps, no overflow; manifest hash shown truncated.

### J. Screenshots to capture
Overview (desktop + 390), Skills catalog, skill Summary, Test with result run page, Evaluations with history, Release with gates, Administration keys/policies, API curl output.

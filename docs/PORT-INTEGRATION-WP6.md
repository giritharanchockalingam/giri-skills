# Skills Factory × Port — WP6: the "PR Review Gate" proof slice (spec §7)

## Shipped

| Requirement (§7) | How |
|---|---|
| Run evidence linked to the PR | `sf_skill_run` gains relation `pull_request → githubPullRequest` (Ocean's id `<repo>-pr-<n>`, verified on the tenant) and `sf_is_head_review` |
| "Reviewed" only for the PR's **head commit** | Port aggregation `sf_passing_head_reviews` on `githubPullRequest` = count of related runs with `sf_status = succeeded`, `sf_skill_slug = code-review-runner`, `sf_is_head_review = true`. The factory sets `sf_is_head_review = false` on a PR's earlier runs when (a) a newer run is recorded for a different head, or (b) GitHub sends `pull_request` opened / synchronize / reopened with a new head (the factory's existing GitHub App webhook) |
| Port scorecard rule `has_passing_review_run` | Scorecard `pr_review_gate` (Not reviewed → Reviewed) on **`githubPullRequest`**: `sf_passing_head_reviews > 0`. Deviation from the spec's "on the repository": the head commit is a property of a PR, not of a repository; a repository can have several open PRs at once |
| Result posted to the PR | GitHub check run "Skills Factory: code-review-runner" on the reviewed commit (success / failure, factory run as details link, Port run entity in the summary) through the factory's GitHub App (`checks: write`) |
| Triggered by | Port workflows leave the user's e-mail empty in the body; the factory resolves the workflow run's `createdBy` through Port's users API. Unresolvable → left empty, never guessed |
| Optional links refused by Port | Dropped one at a time (user, then PR) and named in a note; the run entity is never lost |

Code: `studio/lib/integrations/port/{map,repoRun,scorecard,client}.ts`, `studio/app/api/port/actions/route.ts`, `studio/lib/automations/process.ts`. Tests: `studio/tests/port-gate.test.ts` (+ updated `port.test.ts`).

## Acceptance (spec §7 success criteria) — live

1. A fresh feature PR in giri-skills; from Port, **Run governed skill on a PR** with `code-review-runner` → run entity linked to repo, PR and skill; GitHub check on the head commit; PR's `pr_review_gate` = **Reviewed**.
2. Push a new commit to the PR → gate drops to **Not reviewed** (head moved). Re-run → **Reviewed** again.
3. Trace in Port: repository → run entity → skill entity → eval evidence (`sf_factory_url`) in ≤ 3 clicks.
4. Forced duplicate → one factory run (WP3, re-checked on this PR).
5. Skill scorecard Silver (WP2).
6. Fresh-eyes test: a person who did not build this, given only the Port page, says what the skill is, whether it is trusted, and how to run it. **Owner to name the person.**

## Live acceptance — PR #165, 2026-10-24 (UTC), run from Port in the owner's browser

| # | §7 criterion | Evidence | Result |
|---|---|---|---|
| 1 | Run from Port on a fresh feature PR | PR #165 (reconcile default workspace, real fix). Port run `wfr_kZSEAaTRv5llrMhm` → factory run `e1a1d006-d126-4d49-8ae9-9a75aab6f887`, succeeded 6/6, head `07807024`. Run entity related to **giri-skills**, **giri-skills-pr-165**, **Code review**, **Triggered by: giritharan.c@acldigital.com** | ✅ |
| 1b | Result posted to the PR | GitHub check "Skills Factory: code-review-runner — v2 succeeded (6/6 checks)", success, on `07807024`, details → factory run | ✅ |
| 1c | Gate = Reviewed | 04:14 — `sf_passing_head_reviews = 1`, `pr_review_gate` **Reviewed** | ✅ |
| 2 | New commit drops the gate | Commit `b4aea15` pushed 04:14; factory webhook marked run `e1a1d006` off-head within ~30 s; 04:40 — aggregation 0, **Not reviewed** | ✅ |
| 2b | Re-run restores it | Port run `wfr_QoUAA7l247H4XgoA` → factory run `b947ff8d-59a0-4b56-907b-a4ad75757381`, succeeded 6/6 on `b4aea15`; 05:08 — aggregation 1, **Reviewed** (old run off-head, new run on-head) | ✅ |
| 3 | Trace ≤ 3 clicks from the repo page | Repository page widget "Governed skill runs on this repository" → run (1) → **Code review** skill (2) → **Release page** evidence link (3) | ✅ |
| 4 | Port run ↔ factory run, no duplicate on retry | WP3 (forced replay → same run, `deduplicated: true`, 1 row) | ✅ (WP3) |
| 5 | Skill scorecard Silver (Gold per D3) | code-review-runner **Gold** after D3 (trigger 1.00, lift +0.31, 6 cases, approval valid); tenant: Gold 21 · Silver 22 · Bronze 23 | ✅ |
| 6 | Fresh-eyes test | **Owner-run, not independent.** First read: what ✅, trust ❌, how-to-run ❌ → fixed in code (Start-here summary, #166). Second read: 3/3 from the page alone | ⚠️ owner-run |

### Found live and fixed in code (not in data)

| PR | Finding |
|---|---|
| #166 | Skill page did not explain trust or how to run → `sf_summary` "Start here" tab (first tab) on every AI Skill |
| #167 | D3: Gold = Silver + trigger ≥ 0.90 + lift ≥ 0.30 + ≥ 6 cases |
| #168 | Every AI Skill read "Library status: blocked" — the sync ignored frozen snapshots; now 1 current · 65 library_updated, matching the factory's own pages |
| #169 | A full push left rows pending (one 50-row pass) → kick drains in passes within 40 s; outbox 0/0/0 |

Port UI changes made in the owner's tenant (configuration, not data): Skill-runs table on the repository page; all properties shown and saved on AI Skill and Skill run detail cards; Governed AI Skills table columns switched to verdict / trigger / lift / approval valid / skill quality / release page; Start here tab first.

### Observed Port behaviour

Aggregation properties recalculated at 04:14, 04:40 and 05:08 — about every 26 minutes on this tenant, not the documented 15. The gate therefore lags the factory by up to ~30 minutes; the factory's own state (run on/off head, GitHub check) is immediate.

### Not done / carried

- Retire test — skipped by owner decision (unit-tested only).
- Independent fresh-eyes read — owner-run only.
- PR #165 left open for the owner to merge.

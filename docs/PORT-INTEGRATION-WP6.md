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

Live output: _to be appended_.

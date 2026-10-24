# Skills Factory × Port — WP4: run on a repository PR + run evidence

Spec §4.3, §5.3 (`run_sf_skill_on_repo`), §7 steps 2–3.

| Piece | Where |
|---|---|
| `sf_skill_run` blueprint (one new custom blueprint): run id, skill + version + content hash, factory status word, checks, start/duration, factory link, Port run id, PR number, head commit, PR URL; relations `skill → aiSkill`, `target → githubRepository`, `triggered_by → _user` | `studio/lib/integrations/port/map.ts` |
| Workflow **Run governed skill on a PR** (`run_sf_skill_on_repo`): inputs repository, PR number, skill, optional other inputs | same file; copy from Integrations → Port |
| Receiver: resolves the repository entity's GitHub URL → the factory's GitHub App installation for it (catalog) → PR diff + head commit; fills the skill's `diff` input only if the published version declares one | `studio/lib/integrations/port/repoRun.ts`, `studio/app/api/port/actions/route.ts` |
| Evidence: one `sf_skill_run` entity per Port-started run (both workflows), id `run_<factory run id>`, written after the reply (Port waits ≤ 10 s); a replay writes nothing new; a non-Port user is retried without `triggered_by` and noted | same |
| Tests | `studio/tests/port.test.ts` (run entity, repo workflow/body) |

Plan note: Port Free plan limits are not published. If creating `sf_skill_run` is refused, the error is reported as-is.

## Acceptance (spec WP4) — live

From Port, on the `giri-skills` repository entity, run **Run governed skill on a PR** with skill `code-review-runner` on an open PR → a `sf_skill_run` entity exists related to both `code-review-runner` and `giri-skills`, carrying the PR's head commit.

Live output: _to be appended_.

# Governed skills in Claude Code

Claude Code is where the factory's skills run. Your Claude subscription pays for the work; Vercel's free plan only
serves the catalog, approvals and evidence. The factory decides **what** may run. Claude Code runs it.

| Step | Where | What happens |
|---|---|---|
| Publish | Factory portal | A version passes eval and approval. Its files are frozen (`sf_version_snapshots`). |
| Package | GitHub Actions (`build-plugin`) | `scripts/build_plugin.py` pulls every published version's frozen files and checks them against the factory's hash, then opens a PR that updates `plugins/skills-factory/`. |
| Ship | You merge the PR | `governed.lock.json` records each skill's version and approved hash. |
| Use | Claude Code | Before a skill loads, the plugin's hook hashes its files. Changed or unlisted means blocked. Intact means it loads, and the use is reported. |
| Evidence | Factory → skill → Activity | "Used in Claude Code": loaded or blocked, approved files or changed, current version or older. |

## Install (each person, once)

In Claude Code:

```text
/plugin marketplace add giritharanchockalingam/giri-skills
/plugin install skills-factory@giri-skills
```

Or from a terminal:

```bash
claude plugin marketplace add giritharanchockalingam/giri-skills
claude plugin install skills-factory@giri-skills
```

When it is enabled, Claude Code asks for a **Skills Factory API key** (optional, stored in secure storage). With a key,
each use is reported to the factory. Without one, skills still load and are still checked.

Skills are named `skills-factory:<slug>`, e.g. "use skills-factory:code-review-runner on change.patch".

Update after a plugin PR merges: `/plugin` → skills-factory → update.

## One-time setup (owner)

1. Apply migration `studio/supabase/migrations/0026_sf_skill_uses.sql` (table `sf_skill_uses`, RPCs
   `sf_api_skill_snapshot` and `sf_record_use`).
2. Repository secret `SF_API_KEY`: a factory API key of the publishing workspace. Set it with `read -rs K && printf %s "$K" | gh secret set SF_API_KEY --repo giritharanchockalingam/giri-skills`.
3. Settings → Actions → General → "Allow GitHub Actions to create and approve pull requests".
4. Run the workflow once:

```bash
gh workflow run build-plugin.yml --repo giritharanchockalingam/giri-skills
gh run watch --repo giritharanchockalingam/giri-skills $(gh run list --repo giritharanchockalingam/giri-skills --workflow build-plugin.yml --limit 1 --json databaseId -q '.[0].databaseId')
```

It runs every day at 11:17 UTC as well, and it opens a PR only when something changed.

## Guarantees and limits

- **Only published versions.** The builder asks the factory's API, which returns only the published, frozen version
  of each skill that the key may run (role access applies).
- **Byte for byte, one rewrite.** A skill's files reference the repo's `shared/` and `vendor/` as `../../../…`. In the
  plugin a skill sits one level shallower, so the builder rewrites those prefixes to `../../…` and bundles exactly the
  referenced folders. The lock keeps both hashes: the factory's (as approved) and the installed one.
- **Fail closed.** The hook blocks a skill whose files changed after approval, a skill the lock does not list, and every skill when the lock itself is missing.
- **What is recorded is the load, not the result.** Claude Code runs the skill. The factory records which approved
  version loaded and whether its files were intact. Output checks with recorded evidence are still the job of the
  portal runner and `scripts/run_skill.py`.
- Proven in Claude Code 2.1.310: `tool_input.skill` arrives as `skills-factory:<slug>`. A governed
  code-review-runner returned `Verdict: **BLOCK**` on a diff with a hard-coded key. After one line was added to its
  SKILL.md, it was refused with the "changed after it was approved" message.

## Local check

```bash
python3 -m pytest -q tests/test_build_plugin.py
python3 scripts/build_plugin.py --check        # needs SF_API_KEY; exit 1 = the plugin is behind the factory
```

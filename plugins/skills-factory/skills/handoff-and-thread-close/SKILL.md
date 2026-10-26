---
name: handoff-and-thread-close
description: Use at the end of a working thread, before switching topics, or when context is getting long — "wrap up", "hand off", "close this thread", "update HANDOFF". Produces an updated docs/HANDOFF.md (state, done, changed files from git, open items with owners, the exact next-thread prompt), a verification record, and a changed-files list so the next thread starts cold with zero re-explanation. Not for release notes (use ci-cd-vercel-github) or PR descriptions alone.
license: MIT
metadata:
  domain: build
  adlc_stage: improve
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: target, type: path, required: true, from: "git repository root of the project"}
      - {name: state, type: string, required: true, from: "one honest line: green|red|partial — what is true now"}
      - {name: since, type: string, required: false, from: "ref or YYYY-MM-DD; default: last commit touching docs/HANDOFF.md"}
      - {name: project, type: string, required: false, from: "project name for the header (default: repo dir name)"}
      - {name: seed, type: dir, required: false, from: "evals/demos only: commit-folder layout to build a throwaway repo at target (evals/fixtures/repo-files)"}
    run:
      - {step: seed, kind: script, cmd: "python3 -I scripts/make_fixture_repo.py --from {seed} --target {target}", skip_if_missing: [seed]}
      - {step: handoff, kind: script, cmd: "python3 -I scripts/handoff.py --target {target} --state {state} [--since {since}] [--project {project}] --template assets/HANDOFF.md --out {out}/HANDOFF.md"}
    outputs:
      - {path: "{out}/HANDOFF.md", checks: [exists, sections:["State","Done this thread","Changed files","Open items","Next thread starts with"], max_lines:80]}
    modes:
      new: {case: agent-mode-new, bring: "a repo that has no handoff note yet"}
      existing: {case: agent-happy-path, bring: "your repo and its current handoff note"}
---

# handoff-and-thread-close

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/handoff-and-thread-close --input <name>=<value> … --out <dir>` (see `--explain build/handoff-and-thread-close`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. Every changed file comes from `git diff --name-status`; copy the result to `docs/HANDOFF.md` (or pass `--write-to-repo` to the script) and commit it so the next run knows where this thread ended.

## Starting points
- **New** — a repo with no `docs/HANDOFF.md` gets its first one from the whole git history: commits, changed files with their why, a next-thread prompt.
- **Existing** — the current `docs/HANDOFF.md` is read: only commits since it was last updated are summarised, and its open items are carried forward.

## When to use
- End of a thread; topic change (rule: one topic per thread); context window filling; before a long pause.
- After any build skill finishes its verify gate.
- NOT for: writing the PR itself (the PR template covers that), changelogs.

## Inputs required
| Input | Required | Source |
|---|---|---|
| Repo with `docs/HANDOFF.md` (create from `assets/HANDOFF.md` if missing) | yes | repo |
| Git state (`git status`, `git diff --stat`, recent commits) | yes | repo |
| What was attempted and what remains (from the thread) | yes | thread |
| Verification results (commands run and outcomes) | yes | thread — if not run, run them now |

If a required input is missing, ask for it once; do not guess.

## Procedure
1. Read `../../shared/token-efficiency.md` (HANDOFF contract, rules 5 and 7) and `references/handoff-method.md`.
2. **Collect facts from git, not memory.** `git status --short`, `git diff --stat main...HEAD` (or since last HANDOFF commit), `git log --oneline -10`. Every changed file in the handoff comes from this list.
3. **Verify or declare.** Run lint / typecheck / unit / build if not run in this thread. Record results. If something is red, the state line says so first. *(gate: verify)*
4. **Write HANDOFF.md** per `assets/HANDOFF.md`: State (one line, honest), Done this thread, Changed files (path — why), Open items (owner), Decisions made (with ADR links if any), Next thread starts with (an exact prompt that names the files to read and the first action).
5. **Prune.** Remove items from previous threads that are done; keep the file ≤ 80 lines. Older history lives in git.
6. **Changed-files list** in chat (≤ 15 lines) for commit/PR; flag any file changed that is outside the thread's topic (should it be reverted or split?).
7. **Thread summary** in chat: ≤ 50 words, bottom line first.
8. Offer the commit command (`git add <files> && git commit -m "<type>: <msg>"`) — do not run it unless asked.

## Output
| Artifact | Path / form |
|---|---|
| HANDOFF | `docs/HANDOFF.md` |
| Changed files | chat list |
| Next-thread prompt | inside HANDOFF; also pasted in chat as a code block |
| Commit command | chat |

## Self-check
- [ ] Every changed file came from `git status/diff`, not recollection
- [ ] State line is true (green/red/partial) and first
- [ ] Each open item has an owner
- [ ] Next-thread prompt is copy-paste ready and names files to read first
- [ ] HANDOFF ≤ 80 lines; stale items removed
- [ ] Off-topic changes flagged
- [ ] No secrets, no personal details, no chat transcript pasted

## References
- `references/handoff-method.md` — what goes in, what stays out, prompt-writing rules
- `assets/HANDOFF.md` — the contract template
- `assets/next-thread-prompt.md` — prompt patterns per situation
- `scripts/handoff.py` — fills HANDOFF.md from git (commits, changed files, carried open items); `scripts/make_fixture_repo.py` builds the eval repo

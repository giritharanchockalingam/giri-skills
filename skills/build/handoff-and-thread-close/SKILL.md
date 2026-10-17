---
name: handoff-and-thread-close
description: Use at the end of a working thread, before switching topics, or when context is getting long — "wrap up", "hand off", "close this thread", "update HANDOFF". Produces an updated docs/HANDOFF.md (state, done, changed files from git, open items with owners, the exact next-thread prompt), a verification record, and a changed-files list so the next thread starts cold with zero re-explanation. Not for release notes (use ci-cd-vercel-github) or PR descriptions alone.
license: MIT
metadata:
  domain: build
  version: 0.1.0
  author: giri-skills
---

# handoff-and-thread-close

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
1. Read `../../../shared/token-efficiency.md` (HANDOFF contract, rules 5 and 7) and `references/handoff-method.md`.
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

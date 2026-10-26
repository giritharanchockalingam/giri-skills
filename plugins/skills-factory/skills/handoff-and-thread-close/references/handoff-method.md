# Handoff Method

Purpose: the next thread (a cold context) resumes in one read with zero re-explanation. Recurring context lives in repo docs, not chat.

## What goes in
| Section | Content | Source |
|---|---|---|
| State | one line: `green — feature X built and verified, PR open` / `red — unit suite failing in Y` / `partial — T1–T3 done, T4 in progress` | verification run |
| Done this thread | bullets, past tense, outcome not activity ("invoices table + RLS + 6 tests", not "worked on invoices") | thread |
| Changed files | `path — why`, from git | `git status`, `git diff --stat` |
| Open items (owner) | each with an owner and, if known, a date; questions needing a human decision marked `[TO BE BASELINED — owner: ___]` | thread |
| Decisions | one line each; link ADR when one exists | thread |
| Verification | table: check → command → result | thread |
| Next thread starts with | exact prompt (see below) | you |

## What stays out
- Chat transcript, reasoning, dead ends (one line under "tried and rejected" if it saves the next thread time).
- Secrets, env values, personal details.
- Anything already in SPEC.md, CLAUDE.md or an ADR — link instead.
- History older than the previous thread (git has it).

## Next-thread prompt rules
| Rule | Example |
|---|---|
| Names the files to read first | "Read docs/HANDOFF.md, docs/plans/2026-04-01-invoice-export.md" |
| Names the skill to use | "Use spec-to-plan" / "Use safe-fix" |
| Names the first concrete action | "Start at task T4: implement export service" |
| States the gate | "Post the plan and wait for go" / "Repro first" |
| One topic | if two topics remain, write two prompts and say which is first |
| ≤ 8 lines | fits a paste |

## Off-topic drift check
Compare changed files with the thread's topic. Any file outside it: either revert (`git checkout -- path`) or call it out as "split into separate PR: …" in open items. Never silently bundle.

## When the thread ends red
State line first: `red — <what fails>`. Then: repro command, what was tried, hypothesis, and a next prompt that begins with "Use safe-fix. Repro: `<command>`".

## Size discipline
HANDOFF.md ≤ 80 lines. If longer, move detail to the plan file or an ADR and link.

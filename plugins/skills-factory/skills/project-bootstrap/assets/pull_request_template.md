## What
One sentence. Link: SPEC section / ticket.

## Why
One sentence.

## Plan reference
- [ ] Plan approved (link to thread/HANDOFF entry) or "trivial change"

## Checklist
- [ ] Tests added/updated: unit ☐ integration ☐ e2e ☐ — and the full unit suite passes locally
- [ ] Migration included? If yes: `-- rollback:` block present, `rls_lint.py` clean, RLS enabled on new tables
- [ ] New env vars documented in `.env.example` and set in Vercel (Preview + Production)
- [ ] No secrets, no `console.log`, no `any` added
- [ ] Changed files limited to this topic (no drive-by refactors)
- [ ] `docs/HANDOFF.md` updated
- [ ] Rollback plan stated below

## Rollback
How to revert if this breaks prod (redeploy previous tag / revert migration NNNN / disable flag X).

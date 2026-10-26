# Rollback Runbook

## Decision table
| Symptom after release | First action | Then |
|---|---|---|
| 5xx spike / health down, no migration in release | **Code rollback** (≤ 2 min) | investigate on preview |
| Same, release had an **additive** migration | Code rollback (old code ignores new columns/tables) | leave schema; fix forward |
| Same, release had a **destructive/contract** migration | Do NOT roll back code blindly (old code expects dropped columns) | fix forward or run revert migration first, then code rollback |
| Feature misbehaves, flag-gated | flip flag off | fix forward |
| Data corrupted by new code | stop writes (flag/maintenance), code rollback | restore from PITR to a side DB, repair via migration — never hand-edit prod rows |

## Code rollback (Vercel)
```bash
# Option A — instant: promote previous production deployment
vercel rollback --token=$VERCEL_TOKEN                 # interactive pick, or:
vercel rollback <previous-deployment-url> --token=$VERCEL_TOKEN

# Option B — rebuild previous tag through the pipeline (slower, auditable)
git tag v1.4.1 v1.3.0^{} -m "rollback to v1.3.0"      # new tag pointing at old commit
git push origin v1.4.1                                 # prod.yml runs; migrations are no-ops
```
Then: confirm `/api/health/deep` ok; post in channel; open incident note; HANDOFF entry.

## Migration rollback (Supabase)
1. Open the migration file; copy the `-- rollback:` block.
2. Create a new forward migration: `supabase migration new revert_<name>` with that SQL.
3. Test on staging: `supabase db push` (linked to staging).
4. Apply to prod via a tag release (`prod.yml`) or, in an emergency, `supabase db push` linked to prod from a trusted machine — record who/when.
5. Never delete the original migration file; never `supabase migration repair` to hide history unless the migration never ran.

## Pre-release checklist (makes rollback possible)
- [ ] Previous production deployment still exists (not deleted)
- [ ] Release notes list migrations and their type (additive / contract)
- [ ] Contract migrations are in a separate, later release from the code that stops using the old shape
- [ ] Feature flags default off for new risky paths
- [ ] PITR enabled on prod Supabase (Pro)
- [ ] Someone is watching alerts for 30 min post-release

## Drill
Quarterly: roll back staging to the previous deployment and apply a revert migration; time it; update this runbook.

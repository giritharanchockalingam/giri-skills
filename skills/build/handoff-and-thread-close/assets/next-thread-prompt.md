# Next-Thread Prompt Patterns

## Continue a plan
```
Read docs/HANDOFF.md, CLAUDE.md and docs/plans/<file>.md.
Use spec-to-plan (execute phase). Tasks T1–T3 are done and verified. Start at T4: <name>.
Build → run T4 tests → run full unit suite → mark T4 done in the plan file. Then T5. Stop after T5 and update HANDOFF.
```

## Start a new feature
```
Read docs/HANDOFF.md, CLAUDE.md and docs/SPEC.md §<n>.
Use spec-to-plan for "<feature>". Post the plan (file table, tasks, risks, rollback) and wait for go. No code before go.
```

## Fix a red state
```
Read docs/HANDOFF.md and CLAUDE.md.
Use safe-fix. Symptom: <one line>. Repro: `<command>` (fails on <sha>).
Reproduce first, isolate with evidence, minimal diff, regression test, full suite. Do not touch files outside the failing path.
```

## Schema change
```
Read docs/HANDOFF.md, CLAUDE.md, and the last 3 files in supabase/migrations.
Use supabase-schema-rls to add <entity>: <columns>; access: <rules per role>. Post the plan table and wait for go.
```

## Release
```
Read docs/HANDOFF.md and docs/runbooks/rollback.md.
Use ci-cd-vercel-github. Release v<x.y.z>: confirm main is green, list migrations in this release and their type, then give me the tag commands. Do not tag without my go.
```

## Review before merge
```
Read docs/HANDOFF.md. Use security-review on `git diff main...HEAD`. Trust model: roles <…>, tenancy <…>. Findings table first, fixes after my go.
```

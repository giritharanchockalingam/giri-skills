# Conventions lint — studio

**3 finding(s) in 165 file(s): 0 high, 3 medium.** Gate: PASS.

## Summary

| Rule | Name | Severity | Count |
|---|---|---|---|
| NX1 | supabase-in-component | high | 0 |
| NX2 | console-log | medium | 3 |
| NX3 | action-without-zod | high | 0 |
| NX4 | service-role-exposed | high | 0 |
| NX5 | raw-sql-outside-lib-db | high | 0 |

## Findings

| Rule | File:line | Severity | Status | Snippet |
|---|---|---|---|---|
| NX2 | `scripts/ingest.mjs:548` | medium | new | `console.log(`ingest: runtime bundle: ${runtimeFiles.length} files, ${(runtimeBytes / 1024).toFixed(0)} KB -> public/runt` |
| NX2 | `scripts/ingest.mjs:549` | medium | new | `console.log(`ingest: skills=${skills.length} scorecard=${scorecard.length} trigger=${trigger.length} quality=${quality.l` |
| NX2 | `scripts/serve.mjs:30` | medium | new | `}).listen(port, () => console.log(`serving ${root} on http://localhost:${port}`));` |

## Rules

- **NX1 supabase-in-component** (high) — No Supabase call outside lib/db or server/services (stack-conventions: Data access)
- **NX2 console-log** (medium) — Structured logging via lib/logger only; no console.log in committed code
- **NX3 action-without-zod** (high) — Every server action parses its input with zod before work
- **NX4 service-role-exposed** (high) — Service-role key only in server-side code; never near the client
- **NX5 raw-sql-outside-lib-db** (high) — Raw SQL lives in lib/db only

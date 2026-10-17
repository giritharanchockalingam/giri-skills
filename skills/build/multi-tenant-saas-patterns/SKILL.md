---
name: multi-tenant-saas-patterns
description: Use when designing or changing tenant isolation, roles/permissions, plans and feature flags, billing entitlements, or audit logging in a multi-tenant SaaS on Supabase + Next.js. Produces the tenant model (tables, claims, invitation flow), an RBAC matrix (CSV + enforcement points), plan/feature-flag model with entitlement checks, and an audit-log design, each with migration and code touchpoints. Design-level; hand off to supabase-schema-rls for SQL and security-review for verification. Not for single-tenant apps.
license: MIT
metadata:
  domain: build
  version: 0.1.0
  author: giri-skills
---

# multi-tenant-saas-patterns

## When to use
- "Add organisations/workspaces", "who can do what", "plans and limits", "feature flags per customer", "audit trail", "invite users", "switch tenant".
- Before the first migration of a multi-tenant app; before adding billing.
- NOT for: writing the SQL (`supabase-schema-rls` does that from this design), security verification (`security-review`), single-tenant apps.

## Inputs required
| Input | Required | Source |
|---|---|---|
| Tenant concept (org / workspace / account) and whether users belong to many | yes | user — ask once |
| Roles needed and the actions that matter (≤ 20 actions) | yes | `docs/SPEC.md` / user |
| Plans / tiers and the limits/features that differ | yes if billing | user |
| Compliance needs for audit (retention, immutability, export) | no | user; default 1 year, append-only |
| Existing schema | yes if present | repo |

If a required input is missing, ask for it once; do not guess.

## Procedure
1. Read `../../../shared/stack-conventions.md` (Multi-tenant, Auth rows) and `../../../shared/quality-bar.md`.
2. **Plan.** Decide the four models with the user using `references/tenant-model.md` decision table: tenancy shape, membership, claims, invitation. Post a one-page design summary; wait for "go". *(gate: plan→approve)*
3. **Tenant model.** Produce the table list (tenants, tenant_members, invitations), JWT claim strategy (`app_metadata.tenant_id`, `role`; refresh on switch), tenant-switch flow, and the `requireUser()` contract.
4. **RBAC matrix.** Fill `assets/rbac-matrix.csv` (role × action → allow/deny/own) following `references/rbac.md`; define enforcement points: RLS (data), `requireRole()` (actions), UI (hide only). Each action maps to a policy and a service check.
5. **Plans and feature flags.** From `references/plans-and-flags.md`: `plans`, `tenant_subscriptions`, `tenant_features` (overrides), `entitlements` resolution order, limit checks in services (not UI), flag naming `feature.<name>`.
6. **Audit log.** From `references/audit-log.md`: `audit_log` table (append-only, RLS read by admin, no update/delete), `app.audit_row()` trigger, application-level events for non-row actions, retention and export.
7. **Hand off to build.** Produce the migration task list for `supabase-schema-rls` and the service/action list for `nextjs-enterprise-conventions`; include negative tests for `test-strategy-tdd`. *(gate: build via those skills → test)*
8. **Verify.** Walk the checklist: every tenant table has `tenant_id` + RLS; every RBAC action has an enforcement point; every limit is checked in a service; every sensitive action is audited. *(gate: verify)*
9. Record decisions as ADRs (`project-bootstrap/assets/adr-template.md`); update `docs/HANDOFF.md`.

## Output
| Artifact | Path |
|---|---|
| Design doc | `docs/tenancy.md` (tenant model, claims, flows) |
| RBAC matrix | `docs/rbac-matrix.csv` (from `assets/rbac-matrix.csv`) |
| Plans/flags design | `docs/tenancy.md` §Plans |
| Audit design | `docs/tenancy.md` §Audit |
| ADRs | `docs/adr/NNNN-tenancy.md`, `NNNN-rbac.md` |
| Build task list | for `supabase-schema-rls` / `nextjs-enterprise-conventions` |

## Self-check
- [ ] Tenant id comes only from the JWT (`app_metadata`), never from client input
- [ ] Role change or tenant switch forces a token refresh; stale-claim window stated
- [ ] RBAC matrix: every action has RLS + service enforcement; UI is hide-only
- [ ] Limits enforced in services with a `Result` error code (`PLAN_LIMIT_REACHED`)
- [ ] Audit log append-only; actor, tenant, entity, action, before/after, requestId
- [ ] Cross-tenant unique constraints scoped by `tenant_id`
- [ ] Deleting a tenant: cascade plan + export + retention stated

## References
- `references/tenant-model.md` — tenancy shapes, membership, claims, invitation and switch flows, deletion
- `references/rbac.md` — role design, matrix method, enforcement points, testing
- `references/plans-and-flags.md` — plans, entitlements, overrides, flag lifecycle
- `references/audit-log.md` — schema, trigger, app events, retention, access
- `assets/rbac-matrix.csv` — starter matrix
- `assets/tenancy-schema.sql` — reference DDL for the core tables (hand to supabase-schema-rls)

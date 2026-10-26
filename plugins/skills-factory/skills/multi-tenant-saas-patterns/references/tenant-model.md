# Tenant Model

## Decision table
| Question | Options | Default | Consequence |
|---|---|---|---|
| Isolation | shared schema + RLS (`tenant_id` column) · schema-per-tenant · DB-per-tenant | shared + RLS | one codebase, one migration path; isolation enforced by policy + tests |
| Users ↔ tenants | one tenant per user · many (membership table) | many | `tenant_members` join; active tenant in JWT; switch flow |
| Tenant identity | `tenants.id` uuid + `slug` | both | slug in URLs (`/t/<slug>/…`) or subdomain later |
| Where the active tenant lives | JWT `app_metadata.tenant_id` · cookie · URL | JWT (source of truth) + URL for routing | RLS reads JWT; URL must match JWT or redirect |
| Roles | fixed set (`owner, admin, member, viewer`) · custom per tenant | fixed set | custom roles = permissions table; defer |
| Personal space | personal tenant auto-created per user · none | auto-create | every user always has a tenant; simplifies RLS |

## Core tables (DDL in `assets/tenancy-schema.sql`)
| Table | Purpose | Key columns |
|---|---|---|
| `tenants` | the organisation | `id, slug unique, name, plan_id, status (active|suspended|deleting), created_at` |
| `tenant_members` | membership + role | `tenant_id, user_id, role, status (active|invited|removed), invited_by, created_at`; PK `(tenant_id, user_id)` |
| `invitations` | pending invites by email | `id, tenant_id, email, role, token_hash, expires_at, accepted_at, invited_by`; unique `(tenant_id, email)` |
| `profiles` | app-level user data | `user_id PK → auth.users, display_name, default_tenant_id` |

Every other business table: `tenant_id uuid not null references tenants(id) on delete cascade default app.tenant_id()`.

## Claims
| Claim | Set by | Read by |
|---|---|---|
| `app_metadata.tenant_id` | server (Auth Hook `custom_access_token` or admin API on switch) | `app.tenant_id()` in RLS; `requireUser()` |
| `app_metadata.role` | same, from `tenant_members.role` for that tenant | `app.has_role()` |
| `app_metadata.tenant_ids` (optional) | same | fast "which tenants can I switch to" without a query |

Custom Access Token Hook (Postgres function) is preferred: claims are computed from `tenant_members` at every token issue, so role changes propagate within the access-token lifetime (default 1 h; set 15 min for admin-sensitive apps). Document the stale-claim window.

## Flows
### Sign-up
1. User signs up → trigger `on auth.users insert` creates `profiles` row and a personal tenant + owner membership (`security definer`, pinned `search_path`).
2. Hook issues token with personal tenant claims.

### Invite
1. Admin creates `invitations` row (token = random 32 bytes; store `sha256` hash only; 7-day expiry) → email with link `/invite/<token>`.
2. Invitee signs in/up → server action `acceptInvite(token)`: hash, look up, check expiry/email match, insert `tenant_members`, mark accepted, trigger token refresh (`supabase.auth.refreshSession()`).
3. Rate-limit invite creation; audit both steps.

### Switch tenant
1. `switchTenant(tenantId)` server action: verify membership (query as the user — RLS on `tenant_members`), update `profiles.default_tenant_id`, call admin API to set `app_metadata.tenant_id/role`, then force refresh so the new JWT carries the claims.
2. Middleware: if URL tenant slug ≠ JWT tenant → redirect to `/t/<jwt-tenant>`.

### Remove member / change role
1. Admin action → update `tenant_members`; audit.
2. Affected user's current token stays valid until expiry → for immediate effect, also maintain a `tenant_members.status` check in RLS helper (`app.is_active_member()`), or shorten token lifetime. State which you chose.

### Delete tenant
1. Owner requests → `status = 'deleting'`, members lose access immediately (helper checks status).
2. Export job writes archive to private storage; retention per policy.
3. After grace period, hard delete cascades (`on delete cascade` everywhere) — verify with a staging drill.

## Routing conventions
- `app/(app)/t/[slug]/…` for tenant pages; layout resolves slug → verifies against JWT.
- Never accept `tenantId` in forms, query strings or bodies for data access; only for the switch action, where it is validated against membership.

## Testing
- Personas per role in two tenants (seed).
- Negative tests: read/write across tenants; removed member; expired invite; slug/JWT mismatch redirect.

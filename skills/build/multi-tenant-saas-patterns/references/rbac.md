# RBAC

## Role set (fixed, ordinal)
| Role | Intent | Typical holder |
|---|---|---|
| `owner` | billing, delete tenant, transfer ownership; everything below | founder / account owner |
| `admin` | manage members, settings, all data | team lead |
| `member` | create/edit own and shared work | staff |
| `viewer` | read-only | auditor, client guest |

Add roles only when an action set cannot be expressed by the ordinal ladder. Custom per-tenant roles → permissions table (`role_permissions(tenant_id, role, action)`) — defer until required.

## Matrix method (`assets/rbac-matrix.csv`)
Columns: `action, resource, viewer, member, admin, owner, enforcement_rls, enforcement_service, ui, audited`.
Cell values: `allow`, `own` (only rows they created), `deny`.
Rules:
- Every action row has an RLS policy name **and** a service check — UI is hide-only, never the control.
- `own` requires a `created_by`/`user_id` column and a policy with both tenant and owner predicates.
- Mark `audited = yes` for every write to tenant data, membership, billing, settings.

## Enforcement points
| Layer | Mechanism | Covers |
|---|---|---|
| Database | RLS policies using `app.tenant_id()`, `app.has_role()`, `auth.uid()` | every read/write, including PostgREST, Realtime, direct clients |
| Server | `requireRole('admin')` at the top of actions/routes; service-level checks for business rules (`own`, status transitions) | intent-level authz; clearer errors (`AUTH_FORBIDDEN` vs silent empty) |
| UI | `can(user, 'invoice.delete')` helper → hide/disable | UX only |
| Jobs / edge functions | explicit tenant + role passed in payload, validated; service role used only after validation | background paths |

`can()` is a pure function over the same matrix (generated from the CSV at build time: `scripts/gen-rbac.ts` → `lib/rbac.ts`) so UI and server agree. Server still calls `requireRole`/service checks; `can()` is not a substitute at the boundary.

## Ownership transfer and last-owner rule
- A tenant always has ≥ 1 owner: deny role change/removal that would leave zero (service check + DB constraint via trigger).
- Transfer = promote new owner, then demote old; audited as one event.

## Testing matrix
For each action: one test per role (allow or deny) at the service layer with mocked DB, plus one integration test per RLS policy (positive + negative). Generate the test table from the CSV to avoid drift.

## Common errors
| Error | Fix |
|---|---|
| Role stored only in JWT, not in a table | `tenant_members.role` is the source; JWT is a cache |
| Admin check in layout only | `requireRole` in every action |
| `viewer` can hit a server action because the button is hidden | same |
| Role names compared as strings in many places | ordinal helper (`roleAtLeast`) in `lib/rbac.ts` and `app.has_role()` in SQL, nowhere else |

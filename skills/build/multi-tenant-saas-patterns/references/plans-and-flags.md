# Plans, Entitlements, Feature Flags

## Model
| Table | Purpose | Key columns |
|---|---|---|
| `plans` | catalogue | `id (free|pro|enterprise), name, limits jsonb, features text[], price_monthly_cents, active` |
| `tenant_subscriptions` | which plan a tenant is on | `tenant_id PK, plan_id, status (trialing|active|past_due|canceled), provider, provider_customer_id, provider_subscription_id, current_period_end, trial_ends_at` |
| `tenant_features` | per-tenant overrides | `tenant_id, feature, enabled, expires_at, reason, set_by`; PK `(tenant_id, feature)` |
| `usage_counters` | enforce limits | `tenant_id, metric, period_start, value`; PK `(tenant_id, metric, period_start)` |

Plan `limits` example: `{"seats": 5, "projects": 10, "storage_mb": 1024, "api_calls_per_day": 10000}`. Plan `features`: `["exports", "sso", "audit_export"]`.

## Entitlement resolution (`server/services/entitlements.ts`)
```
isEnabled(tenant, feature):
  1. tenant_features override (not expired)      → use it
  2. subscription.status in (active, trialing)   → feature ∈ plan.features
  3. past_due                                    → plan features, but write actions limited (grace policy)
  4. canceled / none                             → free plan features
limit(tenant, metric):  override > plan.limits[metric] > default
```
Cache per request (memoise in `AsyncLocalStorage`); never in the JWT (changes too often).

## Enforcement
| Where | Rule |
|---|---|
| Services | `const ent = await entitlements.for(user.tenantId); if (!ent.isEnabled('exports')) return fail('FEATURE_NOT_AVAILABLE', …)` |
| Limits | check-and-increment in one statement (`update usage_counters … where value < limit returning *`) or a Postgres function — avoids races |
| UI | show upgrade prompts using the same `ent` object passed as props |
| RLS | not for entitlements (business rule, not isolation) — except hard caps enforced by trigger if abuse risk is high |

Error codes: `FEATURE_NOT_AVAILABLE` (403), `PLAN_LIMIT_REACHED` (409 with `{ metric, limit, current }`).

## Feature flags (release control, separate from entitlements)
| Aspect | Rule |
|---|---|
| Naming | `feature.<area>_<name>` (e.g. `feature.invoice_export`) |
| Source | env `FEATURE_FLAGS` (global kill switch) + `tenant_features` (per-tenant rollout) |
| Default | off in production; on in preview |
| Lifecycle | create with the PR → roll out per tenant → 100% → remove flag and dead code within 2 releases (ticket created at creation) |
| Check | `flags.isOn('feature.x', tenantId)` in services and RSC; never in client bundles for secret features |
| Audit | flag changes written to `audit_log` |

## Billing provider integration (Stripe-shaped)
- Webhook route verifies signature, is idempotent (`provider_event_id` unique), updates `tenant_subscriptions` only; never trusts client-reported plan.
- Checkout/portal sessions created server-side with `tenant_id` in metadata.
- Reconciliation job daily: provider → `tenant_subscriptions` diff → fix + alert.

## Tests
- Entitlement resolution: table-driven unit tests for each (override, status, plan) combination.
- Limit race: integration test with two concurrent increments at the cap → exactly one succeeds.
- Webhook: contract tests with recorded payloads; replay same event twice → one effect.

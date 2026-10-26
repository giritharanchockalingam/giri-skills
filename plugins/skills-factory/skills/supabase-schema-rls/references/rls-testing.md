# RLS Integration Testing

Run against the local Supabase stack (`supabase start`), using the anon key with a signed JWT per persona. Every policy gets one positive and one negative test.

## Personas (from seed.sql)
| Persona | tenant_id | role | user id |
|---|---|---|---|
| A-owner | tenant A | owner | …000a1 |
| A-member | tenant A | member | …000a2 |
| A-viewer | tenant A | viewer | …000a3 |
| B-admin | tenant B | admin | …000b1 |
| anon | — | — | — |

## Harness (`tests/integration/rls/_client.ts`)
```ts
import { createClient } from "@supabase/supabase-js";
import { SignJWT } from "jose";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
const secret = new TextEncoder().encode(process.env.SUPABASE_JWT_SECRET!); // local default from `supabase status`

export async function asUser(p: { sub: string; tenant_id: string; role: string }) {
  const token = await new SignJWT({
    sub: p.sub, role: "authenticated", aud: "authenticated",
    app_metadata: { tenant_id: p.tenant_id, role: p.role },
  }).setProtectedHeader({ alg: "HS256" }).setIssuedAt().setExpirationTime("10m").sign(secret);
  return createClient(url, anon, { global: { headers: { Authorization: `Bearer ${token}` } } });
}
export const asAnon = () => createClient(url, anon);
```

## Test shape (`tests/integration/rls/invoices.test.ts`)
```ts
import { describe, it, expect } from "vitest";
import { asUser, asAnon } from "./_client";
import { seed } from "../../fixtures/seed-ids";

describe("invoices RLS", () => {
  it("A-member sees only tenant A rows", async () => {
    const db = await asUser(seed.aMember);
    const { data, error } = await db.from("invoices").select("tenant_id");
    expect(error).toBeNull();
    expect(new Set(data!.map(r => r.tenant_id))).toEqual(new Set([seed.tenantA]));
  });
  it("B-admin cannot read tenant A row by id", async () => {
    const db = await asUser(seed.bAdmin);
    const { data } = await db.from("invoices").select("id").eq("id", seed.invoiceA1);
    expect(data).toEqual([]);                         // RLS filters, no error
  });
  it("A-viewer cannot insert", async () => {
    const db = await asUser(seed.aViewer);
    const { error } = await db.from("invoices").insert({ number: "X-1", amount_cents: 100 });
    expect(error?.code).toBe("42501");                // new row violates row-level security policy
  });
  it("A-member cannot move a row to tenant B via update", async () => {
    const db = await asUser(seed.aMember);
    const { error } = await db.from("invoices").update({ tenant_id: seed.tenantB }).eq("id", seed.invoiceA1);
    expect(error?.code).toBe("42501");
  });
  it("anon sees nothing", async () => {
    const { data } = await asAnon().from("invoices").select("id");
    expect(data).toEqual([]);
  });
});
```

## Rules
| Rule | Why |
|---|---|
| Negative test asserts empty result for select, `42501` for writes | RLS filters reads silently and rejects writes loudly |
| Test `with check` by attempting to change `tenant_id`/`user_id` | catches the most common escalation |
| Test the lowest role that should be denied, not just anon | role boundaries are where mistakes live |
| Reset DB per test file (`supabase db reset` in `globalSetup`, or transaction rollback) | isolation |
| Run in CI `ci.yml` with `supabase start` service (or skip with a required local job) | policies regress silently otherwise |

## Vitest config
`tests/integration/**` runs with `environment: node`, `testTimeout: 20000`, sequential (`fileParallelism: false`) because they share one DB.

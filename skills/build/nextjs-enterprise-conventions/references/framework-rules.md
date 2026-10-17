# Next.js App Router Framework Rules (fallback for vercel-react-best-practices / vercel-composition-patterns)

Target: Next.js 15+ App Router, React 19, TypeScript strict.

## 1. Server vs client components
| Rule | Detail |
|---|---|
| Server by default | Every file under `app/` and `components/` is a server component unless it needs state, effects, browser APIs, or event handlers. |
| `"use client"` is a boundary, not a flag | Put it on the smallest leaf that needs interactivity. Pass server data down as props (serializable only). |
| Reason comment | First line after the directive: `// client: needs useState for dialog open` |
| No server-only imports in client files | `server-only` package in `lib/db/*`, `server/**`, `lib/supabase/server.ts`; `client-only` in browser helpers. |
| No secrets in client | Only `NEXT_PUBLIC_*` env in client files; `lib/env.ts` exports `serverEnv` and `publicEnv` separately. |
| Children pattern | Wrap client providers around server children; do not convert a whole subtree to client to use context. |
| Props are serializable | No functions, class instances, Dates (send ISO strings) across the boundary except server actions passed by reference. |

## 2. Data fetching and caching
| Rule | Detail |
|---|---|
| Fetch in server components or services, never in `useEffect` | RSC fetches run on the server with no waterfall to the client. |
| Parallelize | `Promise.all` for independent fetches; `preload` pattern for data needed by children. |
| Explicit caching | Next 15: `fetch` is uncached by default. Opt in with `{ next: { revalidate, tags } }` or `"use cache"`. Document the choice per fetch. |
| Supabase reads are dynamic | They use cookies → the route is dynamic. Do not fight it; cache derived public data with `unstable_cache` / `"use cache"` + tags. |
| Tag invalidation | Mutations call `revalidateTag('<entity>:<tenantId>')`; never blanket `revalidatePath('/')`. |
| Streaming | Wrap slow sections in `<Suspense fallback>`; `loading.tsx` per route segment. |
| No request-time work in layouts that every page pays for | Auth check in `middleware.ts` (cheap cookie check) + per-page `requireUser()`; heavy data in the page. |

## 3. Server actions
| Rule | Detail |
|---|---|
| Location | `server/actions/<domain>.ts`, file starts with `"use server"`. |
| Shape | `export async function createInvoice(prev: ActionState, formData: FormData): Promise<ActionState>` for forms; typed object input for programmatic calls. |
| Order inside | 1 parse (zod) → 2 auth + tenant (`requireUser()`) → 3 rate-limit if public → 4 service call → 5 map `Result` → 6 `revalidateTag` → 7 return serializable state. |
| Never trust `formData` ids | Tenant/user ids come from the session, not the form. Entity ids are re-checked by RLS and the service. |
| No throws for expected failures | Return `{ ok:false, error:{ code, message, fieldErrors } }`. Throw only for programmer errors (caught by `error.tsx`). |
| Actions are public endpoints | Treat like a route handler: authz on every one, even if the UI hides the button. |
| Idempotency | Mutations that can be retried accept an `idempotencyKey` and the service dedupes. |
| `redirect()` after success | Outside try/catch (it throws internally). |

## 4. Route handlers (`app/api/**/route.ts`)
- Only for external callers (webhooks, integrations, health). UI mutations use server actions.
- Verify signatures on webhooks before parsing; respond 2xx fast and enqueue heavy work.
- `export const runtime = 'nodejs'` unless edge is deliberate (Supabase service role needs node).
- Return `NextResponse.json(apiError(...), { status })` using the shared error shape.

## 5. Routing and layout
| Rule | Detail |
|---|---|
| Route groups | `app/(marketing)`, `app/(auth)`, `app/(app)` — `(app)/layout.tsx` enforces session. |
| Files per segment | `page.tsx`, `loading.tsx`, `error.tsx` (client), `not-found.tsx` where it matters. |
| Params | Next 15: `params` and `searchParams` are Promises — `const { id } = await params`. Validate with zod. |
| Metadata | `generateMetadata` for dynamic pages; static `metadata` export otherwise. |
| Middleware | Session refresh + redirect only. No DB calls, no business logic. |

## 6. React rules
| Rule | Detail |
|---|---|
| Hooks | No conditional hooks; custom hooks in `components/features/<domain>/hooks/`. |
| State | Server state lives on the server; client state is UI-only. Avoid duplicating server data in `useState`. |
| Forms | `useActionState` + server action; progressive enhancement (works without JS). `useFormStatus` for pending UI. |
| Lists | Stable `key` from id, never index. |
| Effects | Only for syncing with external systems. Derive, don't effect. |
| Memo | Measure first; React Compiler (if enabled) covers most cases. |
| a11y | Semantic elements, labels for inputs, focus management on dialogs, `aria-live` for async status. |

## 7. Performance
- `next/image` with explicit sizes; `next/font` for fonts; dynamic `import()` for heavy client libs.
- Bundle check: `ANALYZE=true npm run build` on PRs that add client deps > 20 kB.
- No barrel files (`index.ts` re-exporting everything) in `components/` — they defeat tree-shaking.

## 8. TypeScript
- `strict: true`, `noUncheckedIndexedAccess: true`. No `any`; `unknown` + narrowing.
- DB types from `lib/db/types.ts` (generated). Domain types in `server/services/<domain>/types.ts`. Never leak `Database['public']['Tables'][...]` rows to components — map to domain DTOs.

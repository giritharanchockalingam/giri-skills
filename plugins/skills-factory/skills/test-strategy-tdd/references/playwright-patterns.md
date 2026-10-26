# Playwright Patterns (fallback for anthropics:webapp-testing)

## Setup
- `playwright.config.ts` from `assets/`; `BASE_URL` env (local `http://localhost:3000`, CI = preview URL).
- Vercel preview protection: send header `x-vercel-protection-bypass: ${VERCEL_AUTOMATION_BYPASS_SECRET}` via `extraHTTPHeaders`.
- Auth once per role via `auth.setup.ts` → `storageState` files in `tests/e2e/.auth/<role>.json` (gitignored). Projects depend on `setup`.
- Test accounts: seeded in `supabase/seed.sql` for local; created by a CI seed step for preview DB (never prod). Credentials via `E2E_USER_EMAIL/PASSWORD` secrets.

## Selectors
| Prefer | Avoid |
|---|---|
| `getByRole('button', { name: 'Create invoice' })` | CSS classes, nth-child |
| `getByLabel('Invoice number')` | placeholder text |
| `getByTestId('invoice-row')` only for lists without accessible names | XPath |

Accessible selectors double as an a11y check.

## Test shape
```ts
test.describe('invoices', () => {
  test.use({ storageState: 'tests/e2e/.auth/member.json' });

  test('member creates an invoice and sees it in the list', async ({ page }) => {
    await page.goto('/invoices/new');
    await page.getByLabel('Invoice number').fill('INV-E2E-1');
    await page.getByLabel('Amount').fill('120.00');
    await page.getByRole('button', { name: 'Create invoice' }).click();
    await expect(page).toHaveURL(/\/invoices$/);
    await expect(page.getByRole('row', { name: /INV-E2E-1/ })).toBeVisible();
  });
});

test.describe('invoices — viewer', () => {
  test.use({ storageState: 'tests/e2e/.auth/viewer.json' });
  test('viewer cannot reach the create page', async ({ page }) => {
    await page.goto('/invoices/new');
    await expect(page.getByRole('heading', { name: /not allowed/i })).toBeVisible();
  });
});
```

## Flake control
| Rule | Detail |
|---|---|
| Web-first assertions only (`expect(locator).toBeVisible()`) | auto-wait; never `waitForTimeout` |
| Unique data per run | suffix with `test.info().workerIndex` + timestamp; cleanup in `afterEach` via API or service |
| No shared mutable state across tests | each test creates what it needs |
| Retries: 2 in CI, 0 locally | surfaces real flake locally |
| Trace on first retry; video off | debuggable, cheap |
| Network: block third-party analytics (`page.route('**/analytics/**', r => r.abort())`) | speed and determinism |
| Keep ≤ 25 e2e tests per app at v1; move breadth to integration | runtime budget ≤ 10 min |

## Checks worth adding to every critical path test
- `await expect(page).toHaveNoConsoleErrors()` pattern: collect `page.on('console')` errors and assert empty.
- Axe: `@axe-core/playwright` `new AxeBuilder({ page }).analyze()` → no `serious`/`critical` violations.

## Running
| Task | Command |
|---|---|
| Local, headed, one spec | `npx playwright test tests/e2e/invoices.spec.ts --headed` |
| CI | `npm run test:e2e` (uses `BASE_URL`) |
| Debug | `npx playwright test --debug` or `--ui` |
| Report | `npx playwright show-report` |

// tests/e2e/auth.setup.ts — sign in once per role; persist storageState.
import { test as setup, expect } from "@playwright/test";

const roles = [
  { name: "member", email: process.env.E2E_USER_EMAIL!, password: process.env.E2E_USER_PASSWORD! },
  { name: "viewer", email: process.env.E2E_VIEWER_EMAIL!, password: process.env.E2E_VIEWER_PASSWORD! },
];

for (const r of roles) {
  setup(`authenticate ${r.name}`, async ({ page }) => {
    await page.goto("/sign-in");
    await page.getByLabel("Email").fill(r.email);
    await page.getByLabel("Password").fill(r.password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByRole("navigation")).toBeVisible();
    await page.context().storageState({ path: `tests/e2e/.auth/${r.name}.json` });
  });
}

// fictional fixture — the team's existing Playwright suite for the webapp-testing-runner evals; no real app
import { test, expect } from "@playwright/test";

test("sign in with email and password", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("pat@example.test");
  await page.getByLabel("Password").fill("fixture-only-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/dashboard/);
});

test("sign out returns to the login page", async ({ page }) => {
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/login/);
});

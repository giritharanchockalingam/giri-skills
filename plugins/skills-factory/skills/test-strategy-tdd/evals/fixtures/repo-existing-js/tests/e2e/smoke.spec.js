// FICTIONAL example e2e already in the repo.
import { test, expect } from "@playwright/test";

test("portal loads", async ({ page }) => {
  await page.goto("/portal");
  await expect(page.getByRole("heading", { name: "Your portal" })).toBeVisible();
});

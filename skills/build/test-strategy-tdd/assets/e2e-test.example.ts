// tests/e2e/invoices.spec.ts
import { test, expect } from "@playwright/test";

test.describe("invoices — member", () => {
  test.use({ storageState: "tests/e2e/.auth/member.json" });

  test("creates an invoice and sees it listed", async ({ page }, testInfo) => {
    const number = `INV-E2E-${testInfo.workerIndex}-${Date.now()}`;
    await page.goto("/invoices/new");
    await page.getByLabel("Invoice number").fill(number);
    await page.getByLabel("Amount").fill("120.00");
    await page.getByRole("button", { name: "Create invoice" }).click();
    await expect(page).toHaveURL(/\/invoices$/);
    await expect(page.getByRole("row", { name: new RegExp(number) })).toBeVisible();
  });

  test("shows field errors for an empty number", async ({ page }) => {
    await page.goto("/invoices/new");
    await page.getByRole("button", { name: "Create invoice" }).click();
    await expect(page.getByText(/number is required/i)).toBeVisible();
  });
});

test.describe("invoices — viewer", () => {
  test.use({ storageState: "tests/e2e/.auth/viewer.json" });

  test("cannot open the create page", async ({ page }) => {
    await page.goto("/invoices/new");
    await expect(page.getByRole("heading", { name: /not allowed|forbidden/i })).toBeVisible();
  });
});

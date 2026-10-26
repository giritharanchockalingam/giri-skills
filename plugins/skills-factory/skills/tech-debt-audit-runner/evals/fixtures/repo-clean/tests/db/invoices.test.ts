// Fictional fixture (tech-debt-audit-runner evals): tests for lib/db/invoices.
import { listInvoiceRows } from "@/lib/db/invoices";

describe("invoices", () => {
  it("returns an empty list for an unknown tenant", async () => {
    expect(await listInvoiceRows("nobody")).toEqual([]);
  });
});

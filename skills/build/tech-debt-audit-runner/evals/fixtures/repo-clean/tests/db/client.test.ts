// Fictional fixture (tech-debt-audit-runner evals): tests for lib/db/client.
import { getClient } from "@/lib/db/client";

describe("client", () => {
  it("builds a query for a table", () => {
    expect(getClient().from("invoices")).toBeDefined();
  });
});

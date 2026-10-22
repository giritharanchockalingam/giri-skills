// Fictional fixture (tech-debt-audit-runner evals): tests for lib/format.
import { formatDate, formatMoney } from "@/lib/format";

describe("format", () => {
  it("formats cents as currency", () => {
    expect(formatMoney(123456, "USD")).toBe("$1,234.56");
  });
  it("formats ISO dates", () => {
    expect(formatDate("2026-03-01T10:00:00Z")).toBe("2026-03-01");
  });
});

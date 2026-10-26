import { describe, expect, it } from "vitest";
import { formatDate, siteUrl } from "../../lib/format";

describe("format", () => {
  it("dates", () => expect(formatDate("2026-01-01T00:00:00Z")).toBe("2026-01-01"));
  it("url", () => expect(siteUrl()).toContain("http"));
});

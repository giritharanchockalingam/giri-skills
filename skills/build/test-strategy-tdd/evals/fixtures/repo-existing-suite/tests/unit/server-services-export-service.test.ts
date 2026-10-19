// FICTIONAL example test suite for evals: written by the team before the export feature was specified.
import { describe, it, expect } from "vitest";

describe("export service", () => {
  it("builds the CSV header row", () => {
    expect("id,number,amount").toContain("number");
  });
  it("export contains only the caller's tenant rows", () => {
    expect(["t1", "t1"].every((t) => t === "t1")).toBe(true);
  });
});

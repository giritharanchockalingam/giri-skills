// FICTIONAL example test written by the team before the bell feature was specified.
import { describe, it, expect } from "vitest";
import { isFresh } from "../../lib/coach";

describe("coach", () => {
  it("a nudge older than 30 days is never shown", () => {
    expect(isFresh({ createdAt: 0 }, 31 * 24 * 60 * 60 * 1000)).toBe(false);
  });
});

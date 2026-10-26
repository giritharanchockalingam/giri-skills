import { describe, expect, it } from "vitest";
import { CASES } from "../../evals/corpus.mjs";

describe("corpus", () => {
  it("has cases", () => expect(CASES.length).toBeGreaterThan(0));
});

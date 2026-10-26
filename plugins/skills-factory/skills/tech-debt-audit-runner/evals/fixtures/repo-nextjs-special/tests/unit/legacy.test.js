import { describe, expect, it } from "vitest";
import { mapLegacy } from "../../lib/legacy";

describe("legacy", () => {
  it("maps", () => expect(mapLegacy({ ID: 1, NAME: "a" })).toEqual({ id: 1, name: "a" }));
});

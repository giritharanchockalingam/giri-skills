// Fictional fixture (tech-debt-audit-runner evals): the one tested lib module.
import * as utils from "@/lib/utils";

describe("utils", () => {
  it("clamps", () => {
    expect(utils.clamp(5, 0, 3)).toBe(3);
  });
});

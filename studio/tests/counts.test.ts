import { test } from "node:test";
import assert from "node:assert/strict";
import { countsBridge } from "../lib/countsText.ts";

test("the counts bridge adds up and names each part", () => {
  const c = { library: 78, reference: 50, workspace: 63, published: 23, inProgress: 40, imported: 61, notImported: 17, authored: 2 };
  assert.equal(countsBridge(c), "78 in the library = 61 in this workspace + 17 not imported yet · plus 2 written in this workspace");
  assert.equal(c.imported + c.notImported, c.library);
  assert.match(countsBridge({ ...c, authored: 0 }), /not imported yet$/);
});

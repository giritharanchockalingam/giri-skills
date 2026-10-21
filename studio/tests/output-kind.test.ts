import { test } from "node:test";
import assert from "node:assert/strict";
import { outputKind, deliverables, svgDataUrl } from "../lib/outputKind.ts";

test("deliverables: the document, the diagrams in order, the editable file", () => {
  const d = deliverables(["out/architecture.md", "out/diagrams/container.svg", "out/architecture.html", "out/diagrams/context.svg", "out/architecture.drawio", "out/nfr.csv"]);
  assert.deepEqual(d, { doc: "out/architecture.html", diagrams: ["out/diagrams/context.svg", "out/diagrams/container.svg"], drawio: "out/architecture.drawio" });
  assert.equal(outputKind("A.SVG"), "svg");
  assert.equal(outputKind("x.txt"), "text");
  assert.ok(svgDataUrl("<svg onload='x'/>").startsWith("data:image/svg+xml"), "SVG is shown as an image, never as inline markup");
});

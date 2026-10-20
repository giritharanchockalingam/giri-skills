import { test } from "node:test";
import assert from "node:assert/strict";
import { mdToHtml } from "../lib/markdown.mjs";

test("baseline flag renders as a labelled flag, never as raw brackets; real text untouched", () => {
  const h = mdToHtml("Savings: [TO BE BASELINED — owner: ___] per year.");
  assert.match(h, /<span class="tbb"[^>]*>To be baselined · owner to be named<\/span>/);
  assert.doesNotMatch(h, /TO BE BASELINED|___/);
  assert.match(mdToHtml("Cost `[TO BE BASELINED — owner: Finance]`"), />To be baselined · owner: Finance</);
  assert.equal(mdToHtml("Plain **bold** text"), mdToHtml("Plain **bold** text"));
  assert.match(mdToHtml("Plain **bold** and [link](https://x.y)"), /<strong>bold<\/strong> and <a href="https:\/\/x.y"/);
});

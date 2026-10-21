import { test } from "node:test";
import assert from "node:assert/strict";
import { modelLabel, NO_MODEL } from "../lib/modelLabel.ts";

test("models show their configured id exactly, with the provider; never an invented name", () => {
  assert.equal(modelLabel("gpt-6-luna", {}), "gpt-6-luna · OpenAI");
  assert.equal(modelLabel("gpt-4.1-mini", {}), "gpt-4.1-mini · OpenAI");
  assert.equal(modelLabel("claude-sonnet-4-5", {}), "claude-sonnet-4-5 · Anthropic");
  assert.equal(modelLabel("meta-llama/llama-3.3-70b", {}), "meta-llama/llama-3.3-70b · Meta");
  assert.equal(modelLabel("house-model-7", {}), "house-model-7");
  assert.equal(modelLabel(null, {}), NO_MODEL);
  assert.equal(modelLabel("dry", {}), NO_MODEL);
  assert.equal(modelLabel("gpt-6-luna", { SF_LLM_MODEL: "gpt-6-luna" }), "gpt-6-luna · OpenAI-compatible (your configured model)");
  assert.equal(modelLabel("gpt-6-luna", { SF_LLM_MODEL: "gpt-6-luna", SF_LLM_MODEL_LABEL: "test fixture" }), "gpt-6-luna · OpenAI-compatible (your configured model: test fixture)");
});

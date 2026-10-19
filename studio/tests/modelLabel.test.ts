import { test } from "node:test";
import assert from "node:assert/strict";
import { modelLabel } from "../lib/modelLabel.ts";

test("model labels people can read; the id stays available", () => {
  assert.equal(modelLabel("gpt-6-luna", {}), "GPT-6 Luna (OpenAI)");
  assert.equal(modelLabel("gpt-4.1-mini", {}), "GPT-4.1 Mini (OpenAI)");
  assert.equal(modelLabel("claude-sonnet-4-5", {}), "Claude Sonnet 4.5 (Anthropic)");
  assert.equal(modelLabel("meta-llama/llama-3.3-70b", {}), "Llama 3.3 70b (Meta)");
  assert.equal(modelLabel(null, {}), "no model");
  assert.equal(modelLabel("dry", {}), "no model (deterministic steps only)");
  assert.equal(modelLabel("gpt-6-luna", { SF_LLM_MODEL: "gpt-6-luna", SF_LLM_MODEL_LABEL: "Luna (our OpenAI model)" }), "Luna (our OpenAI model)");
});

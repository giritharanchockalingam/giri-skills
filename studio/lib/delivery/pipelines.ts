/* The pipeline templates the portal ships (data/pipelines.json, written by scripts/ingest.mjs from pipelines/*.json). */
import pipelinesJson from "@/data/pipelines.json";
import type { Pipeline, PipelineMode } from "./core";

export const PIPELINES = pipelinesJson as unknown as Pipeline[];
export const pipelineByName = (name: string): Pipeline | null => PIPELINES.find((p) => p.name === name) ?? null;
export const pipelinesForMode = (mode: PipelineMode | "all"): Pipeline[] => (mode === "all" ? PIPELINES : PIPELINES.filter((p) => p.mode === mode));

// Pipeline templates (pipelines/*.json, docs/DELIVERY-PIPELINES.md) → the shape the portal ships in data/pipelines.json.
// Zero dependencies; used by scripts/ingest.mjs and unit-tested. The folder may not exist yet: then the list is empty.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const str = (v, d = "") => (typeof v === "string" ? v : d);
const list = (v) => (Array.isArray(v) ? v : []);
const obj = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : {});

/** One pipeline file → {name, version, title, description, mode, fits, inputs, stages[{id, adlc_stage, role, steps[{id, kind, skill?}], gate}]}. */
export function shapePipeline(raw) {
  const p = obj(raw);
  const name = str(p.name);
  if (!/^[a-z0-9][a-z0-9-]{0,78}$/.test(name)) throw new Error(`pipeline: invalid name ${JSON.stringify(p.name)}`);
  const mode = str(p.mode) === "greenfield" ? "greenfield" : "brownfield";
  const fits = obj(p.fits);
  return {
    name,
    version: str(p.version, "0.0.0"),
    title: str(p.title, name),
    description: str(p.description),
    mode,
    fits: { stacks: list(fits.stacks).map(String), request_kinds: list(fits.request_kinds).map(String) },
    inputs: list(p.inputs).map((i) => ({ name: str(obj(i).name), type: str(obj(i).type, "string"), required: obj(i).required === true, from: str(obj(i).from) })).filter((i) => i.name),
    stages: list(p.stages).map((s, n) => {
      const st = obj(s);
      const id = str(st.id);
      if (!id) throw new Error(`pipeline ${name}: stage ${n} has no id`);
      return {
        id, adlc_stage: str(st.adlc_stage, id), role: str(st.role),
        steps: list(st.steps).map((x) => { const t = obj(x); return { id: str(t.id), kind: str(t.kind, "skill"), ...(t.skill ? { skill: str(t.skill) } : {}) }; }).filter((x) => x.id),
        gate: obj(st.gate),
      };
    }),
  };
}

/** Every pipelines/<name>.json (composed/ excluded), sorted by name; [] when the folder is missing. */
export function readPipelines(dir) {
  if (!dir || !existsSync(dir)) return [];
  return readdirSync(dir).filter((f) => f.endsWith(".json")).sort()
    .map((f) => shapePipeline(JSON.parse(readFileSync(join(dir, f), "utf8"))));
}

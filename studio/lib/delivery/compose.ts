/* Pipeline composition when no template fits — the TypeScript port of scripts/compose_pipeline.py (same rules, same
 * step library, same output; tests/compose.test.ts proves parity against fixtures the Python script produced).
 * Pure: the catalog (roles, skill fits) and the request kinds come in as data; nothing is persisted here.
 * Contract: docs/DELIVERY-PIPELINES.md → When no template fits. */
import type { Pipeline, PipelineMode } from "./core";

export interface RequestKind { id: string; description: string; stages?: string[]; mode?: PipelineMode; alias_of?: string }
export interface RequestKinds { kinds: RequestKind[]; stacks: Record<string, string> }
export interface SkillFits { stacks?: string[]; request_kinds?: string[] }
export interface ComposeCatalog { roles: { name: string; stages?: string[]; skills?: string[] }[]; fits: Record<string, SkillFits | null | undefined> }
export interface Decision { stage: string; role: string; step: string; skill?: string; decision: "chosen" | "rejected" | "dropped" | "note"; why: string }
export interface ComposedPipeline extends Pipeline {
  stack_profile: { from: string; detect: string; after?: string };
  stages: ComposedStage[];
  outputs: string[];
  composed: { request_kind: string; stacks: string[]; notes: string[] };
}
export type ComposedStep = { id: string; kind: string; skill?: string } & Record<string, unknown>;
export interface ComposedStage { id: string; adlc_stage: string; role: string; steps: ComposedStep[]; gate: Record<string, unknown>; evidence: string[] }
export interface ComposeResult { pipeline: ComposedPipeline | null; decisions: Decision[]; notes: string[] }
export interface ComposeInput { stacks: string[]; requestKind: string; mode?: PipelineMode | null; stages?: string[] | null; name?: string | null }

export const COMPOSE_VERSION = "0.1.0";
const NOTE = "Approve the plan before any code is written; edit plan.md / tasks.csv in the step folder first if files or tests are missing";

interface LibStep {
  id: string; kind: "skill" | "compose" | "agent" | "approval" | "pr"; skill?: string; derive?: string; agent?: string;
  inputs?: Record<string, string>; outputs?: string[]; produces?: string[]; requires?: string[]; optional?: string[]; plan_fallback?: string[];
  constraints?: string[]; step_gate?: boolean; note?: string; title?: string; branch?: string; body?: string;
  gate?: Record<string, unknown>; fallback_gate?: Record<string, unknown>; evidence?: string[];
}

/** The step library: the shipped templates' wiring, per ADLC stage, in order (mirror of LIBRARY in compose_pipeline.py). */
export const LIBRARY: Record<string, LibStep[]> = {
  bootstrap: [
    { id: "scaffold", kind: "skill", skill: "build/project-bootstrap", inputs: { target: "$repo", name: "$in.name" },
      gate: { kind: "output", step: "scaffold", file: "bootstrap-report.json", check: "json" }, evidence: ["$steps.scaffold:bootstrap-report.json"] },
  ],
  requirements: [
    { id: "brief", kind: "compose", derive: "brief-from-request", inputs: { request: "$in.request", brief: "$in.brief" }, outputs: ["brief.json"], evidence: ["$steps.brief:brief.json"] },
    { id: "prd", kind: "skill", skill: "build/product-spec-prd", requires: ["brief"], inputs: { brief: "$steps.brief:brief.json", draft_only: "$run.draft_only" },
      gate: { kind: "output", step: "prd", file: "prd-final.md", check: "sections:[\"Acceptance criteria\"]" }, evidence: ["$steps.prd:prd-final.md"] },
  ],
  architecture: [
    { id: "spec", kind: "compose", derive: "spec-from-prd", requires: ["brief"], optional: ["prd"],
      inputs: { brief: "$steps.brief:brief.json", prd: "$steps.prd:prd-final.md", request: "$in.request" }, outputs: ["spec.md", "spec.json"] },
    { id: "plan", kind: "skill", skill: "build/spec-to-plan", requires: ["spec"], inputs: { spec: "$steps.spec:spec.md", section: "$steps.spec:spec.json#section", repo: "$repo" },
      evidence: ["$steps.plan:plan.md", "$steps.plan:tasks.csv"] },
    { id: "plan-approval", kind: "approval", requires: ["plan"], note: NOTE, gate: { kind: "approval", step: "plan-approval" } },
  ],
  build: [
    { id: "feature", kind: "compose", derive: "feature-from-plan", requires: ["plan"], optional: ["brief"],
      inputs: { plan: "$steps.plan:plan.md", tasks: "$steps.plan:tasks.csv", brief: "$steps.brief:brief.json" }, outputs: ["feature.md", "feature.json"] },
    { id: "files", kind: "agent", agent: "claude-code", produces: ["files.txt"], optional: ["tasks"],
      inputs: { plan: "$steps.plan:plan.md", tasks: "$steps.plan:tasks.csv", target: "$repo" }, plan_fallback: ["$steps.plan:plan.md", "$steps.spec:spec.md"],
      evidence: ["$steps.files:files.txt"] },
    { id: "tests", kind: "skill", skill: "build/test-strategy-tdd", requires: ["feature", "files"],
      inputs: { feature: "$steps.feature:feature.md", files: "$steps.files:files.txt#csv", target: "$repo" },
      evidence: ["$steps.tests:test-plan.md", "$steps.tests:scaffold-report.json"] },
    { id: "code", kind: "agent", agent: "claude-code", optional: ["tests", "files"], inputs: { plan: "$steps.plan:plan.md", tests: "$steps.tests:test-plan.md", files: "$steps.files:files.txt", target: "$repo" },
      plan_fallback: ["$steps.plan:plan.md", "$steps.spec:spec.md"], constraints: ["skills/build/nextjs-enterprise-conventions/SKILL.md", "shared/stack-conventions.md"],
      fallback_gate: { kind: "output", step: "code", file: "diff.patch", check: "exists" }, evidence: ["$steps.code:diff.patch", "$steps.code:agent-summary.md"] },
    { id: "conventions", kind: "skill", skill: "build/nextjs-enterprise-conventions", step_gate: true, inputs: { target: "$repo", baseline: "$profile.baselines.nextjs" },
      gate: { kind: "exit", step: "conventions" }, evidence: ["$steps.conventions:report.md"] },
  ],
  evaluate: [
    { id: "review", kind: "skill", skill: "build/code-review-runner", requires: ["code"], optional: ["prd"], inputs: { diff: "$steps.code:diff.patch", spec: "$steps.prd:prd-final.md" },
      gate: { kind: "output", step: "review", file: "review.md", check: "contains:\"Verdict: **PASS**\"" }, evidence: ["$steps.review:review.md"] },
    { id: "security", kind: "skill", skill: "build/security-review", requires: ["code"], inputs: { diff: "$steps.code:diff.patch", target: "$repo", draft_only: "$run.draft_only" },
      gate: { kind: "exit", step: "security" }, evidence: ["$steps.security:security-review.md"] },
    { id: "perf", kind: "skill", skill: "build/perf-review-runner", inputs: { target: "$repo", baseline: "$profile.baselines.perf" }, gate: { kind: "exit", step: "perf" }, evidence: ["$steps.perf:report.md"] },
    { id: "ui", kind: "skill", skill: "build/ui-component-quality", inputs: { target: "$repo", baseline: "$profile.baselines.ui" }, gate: { kind: "exit", step: "ui" }, evidence: ["$steps.ui:report.md"] },
  ],
  deploy: [
    { id: "observe", kind: "skill", skill: "build/observability-setup", inputs: { target: "$repo" }, evidence: ["$steps.observe:install-report.md"] },
    { id: "ci", kind: "skill", skill: "build/ci-cd-vercel-github", inputs: { target: "$repo" }, evidence: ["$steps.ci:ci-report.md"] },
    { id: "pr", kind: "pr", title: "$in.request", branch: "deliver/$run.id", body: "$evidence", gate: { kind: "external", what: "CI green on the pull request" }, evidence: ["$steps.pr:pr.json"] },
  ],
  operate: [
    { id: "handoff", kind: "skill", skill: "build/handoff-and-thread-close", inputs: { target: "$repo", state: "$run.state" },
      gate: { kind: "output", step: "handoff", file: "HANDOFF.md", check: "exists" }, evidence: ["$steps.handoff:HANDOFF.md"] },
  ],
};
const ADLC_OF: Record<string, string> = { bootstrap: "build" };
const BRIEF_FROM = "product brief for product-spec-prd (layout: skills/build/product-spec-prd/assets/brief-template.json); may carry `files` or `tasks`";
const INPUTS: Record<PipelineMode, Pipeline["inputs"]> = {
  brownfield: [
    { name: "repo", type: "repo", required: true, from: "catalog repository (owner/name) or a local checkout" },
    { name: "ref", type: "string", required: false, from: "branch or commit to start from (default: the checkout as it is)" },
    { name: "request", type: "text", required: true, from: "the request in the requester's words" },
    { name: "brief", type: "json", required: false, from: BRIEF_FROM },
  ],
  greenfield: [
    { name: "repo", type: "repo", required: true, from: "directory to create the application in (created if absent)" },
    { name: "name", type: "string", required: true, from: "project name" },
    { name: "request", type: "text", required: true, from: "what the application must do, in the requester's words" },
    { name: "brief", type: "json", required: false, from: BRIEF_FROM },
  ],
};

export class ComposeError extends Error {}

/** The kind record (aliases followed); throws ComposeError naming the known ids. */
export function resolveKind(kinds: RequestKinds, kind: string): RequestKind {
  const byId = new Map(kinds.kinds.map((k) => [k.id, k]));
  const k = byId.get(kind);
  if (!k) throw new ComposeError(`unknown request kind '${kind}' (one of ${[...byId.keys()].sort().join(", ")})`);
  return k.alias_of ? byId.get(k.alias_of)! : k;
}

/** Stack signal ids (lib/github/detect.ts) a stack profile (scripts/stack_profile.py) implies — sorted; mirror of stacks_from_profile. */
export function stacksFromProfile(profile: Record<string, unknown>): string[] {
  const s = new Set<string>();
  const fw = String(profile.framework ?? ""), fl = String(profile.flavour ?? "");
  if (fw === "nextjs") { s.add("nextjs"); s.add("react"); } else if (fw === "remix" || fw === "vite-react") s.add("react");
  if (fl === "ts") s.add("typescript");
  if (fl === "python" || ["fastapi", "django", "flask"].includes(fw)) s.add("python");
  const mig = profile.migrations_dir;
  if (typeof mig === "string" && mig.startsWith("supabase/")) s.add("supabase");
  if (profile.deploy_target === "vercel") s.add("vercel");
  const ev = profile.evidence && typeof profile.evidence === "object" ? (profile.evidence as Record<string, unknown>) : {};
  if (String(ev.deploy_target ?? "").startsWith(".github/workflows/")) s.add("github-actions");
  const none = (v: unknown) => v == null || v === "" || v === "none";
  if (!none(profile.test_runner) || !none(profile.e2e)) s.add("tests");
  return [...s].sort();
}

/** Absent fits = fits anything; `any` matches every stack. Returns the reason when it does not fit. */
export function fitsMatch(fits: SkillFits | null | undefined, stacks: string[], kind: string): string | null {
  if (!fits) return null;
  const fs = (fits.stacks ?? []).map(String);
  if (fs.length && !fs.includes("any") && !fs.some((x) => stacks.includes(x))) return `stack: fits ${fs.join(", ")}; the repository has ${stacks.join(", ") || "no known signal"}`;
  const fk = (fits.request_kinds ?? []).map(String);
  if (fk.length && !fk.includes(kind)) return `kind: fits ${fk.join(", ")}; the request is a ${kind}`;
  return null;
}

const lib = (stepId: string): LibStep | undefined => Object.values(LIBRARY).flat().find((s) => s.id === stepId);
const stepOf = (ref: string) => ref.slice("$steps.".length).split(":", 1)[0];
const home = (stepId: string) => Object.entries(LIBRARY).find(([, steps]) => steps.some((s) => s.id === stepId))?.[0] ?? "?";
const isStepRef = (v: unknown): v is string => typeof v === "string" && v.startsWith("$steps.");

export function compose(input: ComposeInput, catalog: ComposeCatalog, kinds: RequestKinds): ComposeResult {
  const krec = resolveKind(kinds, input.requestKind);
  const kid = krec.id;
  const mode: PipelineMode = input.mode ?? krec.mode ?? "brownfield";
  if (mode !== "brownfield" && mode !== "greenfield") throw new ComposeError(`mode must be brownfield or greenfield, not '${mode}'`);
  let wanted = input.stages?.length ? [...input.stages] : [...(krec.stages ?? [])];
  const unknown = wanted.filter((s) => !(s in LIBRARY) || s === "bootstrap");
  if (unknown.length) throw new ComposeError(`unknown stage(s) [${unknown.map((u) => `'${u}'`).join(", ")}] (one of ${Object.keys(LIBRARY).filter((k) => k !== "bootstrap").join(", ")})`);
  if (mode === "greenfield") wanted = ["bootstrap", ...wanted];
  const stacks = [...new Set(input.stacks)].sort();
  const decisions: Decision[] = [];
  const notes: string[] = [];
  const present = new Set<string>();
  const stagesOut: ComposedStage[] = [];

  for (const sid of wanted) {
    const adlc = ADLC_OF[sid] ?? sid;
    const roleRec = catalog.roles.find((r) => (r.stages ?? []).includes(adlc));
    if (!roleRec) throw new ComposeError(`no role in roles/ owns the ${adlc} stage`);
    const role = roleRec.name;
    const roleSkills = new Set(roleRec.skills ?? []);
    const chosen: ComposedStep[] = [];
    const here = new Set<string>();
    const decide = (step: string, decision: Decision["decision"], why: string, skill?: string) =>
      decisions.push({ stage: sid, role, step, ...(skill ? { skill } : {}), decision, why });
    const available = (id: string) => present.has(id) || here.has(id);
    const canCarry = (id: string): boolean => { const st = lib(id); return !!st && st.kind === "compose" && (st.requires ?? []).every((r) => available(r) || canCarry(r)); };
    const rootMissing = (id: string): string => { const st = lib(id); if (st?.kind === "compose") for (const r of st.requires ?? []) if (!available(r)) return rootMissing(r); return id; };

    const writeStep = (st: LibStep): ComposedStep => {
      const out: ComposedStep = { id: st.id, kind: st.kind };
      if (st.kind === "skill") out.skill = st.skill; else if (st.kind === "compose") out.derive = st.derive; else if (st.kind === "agent") out.agent = st.agent;
      if (st.inputs) {
        const inputs: Record<string, string> = {};
        for (const [k, v] of Object.entries(st.inputs)) {
          if (st.kind === "agent" && k === "plan") { inputs[k] = st.plan_fallback!.find((p) => available(stepOf(p)))!; continue; }
          if (isStepRef(v) && !available(stepOf(v))) continue;
          inputs[k] = v;
        }
        out.inputs = inputs;
      }
      if (st.kind === "compose") out.outputs = [...st.outputs!];
      else if (st.kind === "agent" && st.produces) out.produces = [...st.produces];
      else if (st.kind === "agent") out.constraints = st.constraints!.filter((c) => stacks.includes("nextjs") || !c.startsWith("skills/build/nextjs"));
      else if (st.kind === "skill" && st.step_gate) out.gate = true;
      else if (st.kind === "approval") { out.role = role; out.note = st.note; }
      else if (st.kind === "pr") { out.title = st.title; out.branch = st.branch; out.body = st.body; }
      return out;
    };
    const add = (st: LibStep, why: string) => {
      for (const r of st.requires ?? []) if (!available(r)) carry(r);
      for (const [k, v] of Object.entries(st.inputs ?? {})) if (isStepRef(v) && (st.optional ?? []).includes(k) && !available(stepOf(v)))
        decide(st.id, "note", `optional input \`${k}\` dropped: step ${stepOf(v)} is not in this pipeline`, st.skill);
      chosen.push(writeStep(st)); here.add(st.id);
      decide(st.id, "chosen", why, st.skill);
    };
    const carry = (id: string) => {
      const st = lib(id)!;
      const h = home(id);
      add(st, `compose ${st.derive} (${h === sid ? "its home stage" : `carried from the absent ${h} stage`}): a later step needs ${st.outputs![0]}`);
    };

    for (const st of LIBRARY[sid]) {
      if (st.kind === "compose") continue;
      if (st.kind === "skill") {
        if (!roleSkills.has(st.skill!)) { decide(st.id, "rejected", `role ${role} does not list ${st.skill}`, st.skill); continue; }
        const why = fitsMatch(catalog.fits[st.skill!], stacks, kid);
        if (why) { decide(st.id, "rejected", why, st.skill); continue; }
      }
      const missing = (st.requires ?? []).filter((r) => !available(r) && !canCarry(r));
      let planRef: string | null = null;
      if (st.kind === "agent") {
        planRef = st.plan_fallback!.find((p) => available(stepOf(p)) || canCarry(stepOf(p))) ?? null;
        if (!planRef) missing.push("plan");
      }
      if (missing.length) {
        const roots = [...new Set(missing.map((m) => rootMissing(m)))].sort();
        decide(st.id, "rejected", `needs step(s) ${missing.join(", ")}: ${roots.map((r) => `${r} (${home(r)} stage, absent or dropped)`).join(", ")}`, st.skill);
        continue;
      }
      if (planRef && !available(stepOf(planRef))) carry(stepOf(planRef));
      add(st, st.kind === "skill" ? "fits the stack and the request kind; every input resolves"
        : st.kind === "agent" && st.produces ? `the files step (plan: ${planRef}): the files the change touches, derived from tasks.csv when every task names them`
        : st.kind === "agent" ? `the build step (plan: ${planRef})`
        : st.kind === "approval" ? "follows the plan" : "the pull request carries the evidence");
    }
    const wiredHere = new Set(LIBRARY[sid].map((s) => s.skill).filter(Boolean));
    const elsewhere: string[] = [], unwired: string[] = [];
    for (const sk of [...roleSkills].filter((s) => !wiredHere.has(s)).sort()) {
      const h = Object.entries(LIBRARY).find(([, steps]) => steps.some((s) => s.skill === sk))?.[0];
      if (h) elsewhere.push(`${sk} (${h})`); else unwired.push(sk);
    }
    if (elsewhere.length) decide("-", "rejected", `wired in another stage by the step library: ${elsewhere.join(", ")}`);
    if (unwired.length) decide("-", "rejected", `no wiring recipe in the step library (inputs not derivable from earlier steps or the profile): ${unwired.join(", ")}`);

    if (!chosen.some((s) => s.kind === "skill")) {
      decide("-", "dropped", `no skill of role ${role} fits ${stacks.join(", ") || "the stack"} for a ${kid}: stage dropped`);
      notes.push(`stage ${sid} dropped: no skill of role ${role} fits the stack (${stacks.join(", ") || "none"}) for a ${kid}`);
      continue;
    }
    const libIds = LIBRARY[sid].map((s) => s.id);
    const key = (s: ComposedStep) => (libIds.includes(s.id) ? 1000 + libIds.indexOf(s.id) : 0);
    chosen.sort((a, b) => key(a) - key(b));   // stable: carried steps keep their order, home steps follow library order
    for (const s of chosen) present.add(s.id);
    let gates = chosen.map((s) => lib(s.id)!.gate).filter((g): g is Record<string, unknown> => !!g);
    if (!gates.length) gates = chosen.map((s) => lib(s.id)!.fallback_gate).filter((g): g is Record<string, unknown> => !!g);
    const gate = gates.length === 1 ? gates[0] : { kind: "all", of: gates };
    const evidence = chosen.flatMap((s) => lib(s.id)!.evidence ?? []);
    stagesOut.push({ id: sid, adlc_stage: adlc, role, steps: chosen, gate, evidence });
  }

  if (!stagesOut.length) return { pipeline: null, decisions, notes: [...notes, "nothing composed: no stage kept a fitting skill"] };
  const name = input.name || `composed-${kid}-${stacks.join("-") || "any"}`;
  const pipeline: ComposedPipeline = {
    name, version: COMPOSE_VERSION,
    title: `Composed ${kid} pipeline for ${stacks.join(", ") || "an unprofiled repository"}`,
    description: `Composed by scripts/compose_pipeline.py: ${kid} request on a ${mode} ${stacks.join(", ") || "unknown"} stack — stages ${stagesOut.map((s) => s.id).join(", ")}; the step wiring is the shipped templates'.`
      + (notes.length ? ` Notes: ${notes.join("; ")}.` : ""),
    mode,
    fits: { stacks: stacks.length ? stacks : ["any"], request_kinds: [kid] },
    inputs: INPUTS[mode],
    stack_profile: { from: "repo", detect: "scripts/stack_profile.py", ...(stagesOut[0].id === "bootstrap" ? { after: "bootstrap" } : {}) },
    stages: stagesOut,
    outputs: [...(present.has("pr") ? ["$steps.pr:pr.json"] : []), "$evidence"],
    composed: { request_kind: kid, stacks, notes },
  };
  return { pipeline, decisions, notes };
}

/** The decision table as text (stage → role → step: chosen / rejected / dropped and why). */
export function explain(result: ComposeResult): string {
  const p = result.pipeline;
  const head = p ? `composed: ${p.name} — stages ${p.stages.map((s) => s.id).join(", ")}` : "composed: nothing";
  const rows = result.decisions.map((d) => `${d.stage} | ${d.role} | ${d.step}${d.skill ? ` | ${d.skill}` : ""} | ${d.decision} | ${d.why}`);
  return [head, ...result.notes.map((n) => `note: ${n}`), ...rows].join("\n");
}

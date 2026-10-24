/* Skills Factory → Port, the pure part: the "AI Skill" blueprint, one entity per published skill, and the self-service
 * action definition a Port admin imports. Shapes follow docs.port.io (blueprints, entities, self-service actions);
 * fields Port's docs do not pin down are marked "verify on first live run" in docs/PORT.md. */

export const BLUEPRINT_ID = "aiSkill";

/** Port blueprint identifier the factory's skills live under (owner decision D7, 2026-10-23: keep `aiSkill`, extend it
 *  with the spec's `sf_` properties, relate it to Port's own Skills-registry `skill` blueprint rather than writing into it). */
export const REGISTRY_BLUEPRINT_ID = "skill";

/** Properties the factory owns on the Port entity (spec §4.1). Everything here is overwritten on every sync; Port never
 *  recomputes any of it. A value the factory does not have is null — never 0, never a placeholder (house rule 1). */
export const SF_PROPERTIES = {
  sf_skill_slug: { type: "string", title: "Skill slug" },
  sf_version: { type: "string", title: "Published version", description: "Exact published version. Never a range." },
  sf_content_hash: { type: "string", title: "Content hash", description: "Manifest hash pinned at approval. A mismatch with the factory means the entity is stale." },
  sf_status: { type: "string", title: "Release state", enum: ["published", "retired"], enumColors: { published: "green", retired: "darkGray" } },
  sf_eval_verdict: { type: "string", title: "Eval verdict", enum: ["healthy", "being-improved", "not-evaluated"], enumColors: { healthy: "green", "being-improved": "orange", "not-evaluated": "lightGray" }, description: "From the Skills Factory eval harness." },
  sf_trigger_score: { type: "number", title: "Trigger score (0–1)", description: "Routing accuracy from the latest behavioural eval. Null when not evaluated." },
  sf_lift: { type: "number", title: "Lift", description: "Quality lift with the skill versus the model alone. Null when not evaluated." },
  sf_eval_cases: { type: "number", title: "Eval cases" },
  sf_eval_model: { type: "string", title: "Eval model" },
  sf_eval_at: { type: "string", title: "Evaluated", format: "date-time" },
  sf_approval_valid: { type: "boolean", title: "Approval valid", description: "True only when the approval hash equals the current content hash." },
  sf_factory_url: { type: "string", title: "Release page", format: "url" },
  sf_mcp_tool: { type: "string", title: "MCP tool" },
  sf_owner: { type: "string", title: "Owner" },
  sf_synced_at: { type: "string", title: "Synced", format: "date-time" },
} as const;

export const AI_SKILL_BLUEPRINT = {
  identifier: BLUEPRINT_ID,
  title: "AI Skill",
  icon: "AI",
  // Port caps blueprint descriptions at 200 characters (422 otherwise); the longer §8 copy goes on the catalog page.
  description: "Governed AI skill from Skills Factory. Verdicts come from its eval harness; sf_ properties are factory-managed and overwritten on sync. Run from here or your IDE via MCP.",
  schema: {
    properties: {
      purpose: { type: "string", title: "Purpose", format: "markdown" },
      version: { type: "number", title: "Live version" },
      published_at: { type: "string", title: "Published", format: "date-time" },
      eval_pass_rate: { type: "number", title: "Eval pass rate (%)" },
      eval_cases: { type: "number", title: "Eval cases" },
      approved: { type: "boolean", title: "Approved" },
      library_status: { type: "string", title: "Library status", enum: ["current", "library_updated", "blocked"] },
      stage: { type: "string", title: "Lifecycle stage" },
      inputs: { type: "array", title: "Inputs" },
      uses_model: { type: "boolean", title: "Uses a model" },
      manifest_hash: { type: "string", title: "Manifest hash" },
      portal_url: { type: "string", title: "Skills Factory page", format: "url" },
      mcp_tool: { type: "string", title: "MCP tool name" },
      ...SF_PROPERTIES,
    },
    required: [],
  },
  relations: {},
} as const;

/** Relation added only when the tenant has Port's Skills-registry blueprint (`skill`): the SKILL.md entity Port's
 *  GitHub integration discovered for the same skill. Set, never created: the registry stays Port's. */
export const REGISTRY_RELATION = { registry_file: { title: "Registry file (SKILL.md)", target: REGISTRY_BLUEPRINT_ID, required: false, many: false } } as const;

export type EvalVerdict = "healthy" | "being-improved" | "not-evaluated";

export interface SkillForPort {
  slug: string; name: string; purpose: string; version: number; published_at: string | null; manifest_hash: string;
  inputs: { name: string; required: boolean }[]; usesModel: boolean; evalPassRate: number | null; evalCases: number;
  approved: boolean; drift: "current" | "library_updated" | "blocked" | "n/a"; stage: string | null;
  /** spec §4.1 — all optional so the pre-WP1 callers and tests keep working; absent means "not known", synced as null */
  status?: "published" | "retired";
  verdict?: EvalVerdict; triggerScore?: number | null; lift?: number | null; evalModel?: string | null; evalAt?: string | null;
  owner?: string | null;
  /** `<owner>/<repo>/<path>/SKILL.md` as Port's registry identifies it, when the tenant has the registry blueprint */
  registryFileId?: string | null;
}

/** Port identifiers allow letters, digits and - _ @ . (max 100); slugs already fit. */
export const portId = (slug: string) => slug.replace(/[^A-Za-z0-9_@.-]/g, "-").slice(0, 100);

export function skillEntity(s: SkillForPort, portalBase: string, syncedAt: string = new Date().toISOString()) {
  const base = portalBase.replace(/\/$/, "");
  return {
    identifier: portId(s.slug),
    title: s.name,
    properties: {
      purpose: s.purpose,
      version: s.version,
      published_at: s.published_at,
      eval_pass_rate: s.evalPassRate == null ? null : Math.round(s.evalPassRate * 1000) / 10,
      eval_cases: s.evalCases,
      approved: s.approved,
      library_status: s.drift === "n/a" ? "current" : s.drift,
      stage: s.stage,
      inputs: s.inputs.map((i) => `${i.name}${i.required ? "" : " (optional)"}`),
      uses_model: s.usesModel,
      manifest_hash: s.manifest_hash,
      portal_url: `${base}/skills/${s.slug}`,
      mcp_tool: s.slug,
      // spec §4.1 (factory-owned, overwritten on every sync)
      sf_skill_slug: s.slug,
      sf_version: String(s.version),
      sf_content_hash: s.manifest_hash,
      sf_status: s.status ?? "published",
      sf_eval_verdict: s.verdict ?? "not-evaluated",
      sf_trigger_score: s.triggerScore ?? null,
      sf_lift: s.lift ?? null,
      sf_eval_cases: s.evalCases,
      sf_eval_model: s.evalModel ?? null,
      sf_eval_at: s.evalAt ?? null,
      sf_approval_valid: s.approved,
      sf_factory_url: `${base}/skills/${s.slug}/release`,
      sf_mcp_tool: s.status === "retired" ? null : s.slug,
      sf_owner: s.owner ?? null,
      sf_synced_at: syncedAt,
    },
    relations: s.registryFileId ? { registry_file: s.registryFileId } : {},
  };
}

/** The factory's verdict codes → the three words Port shows (spec §4.1 keeps the factory's wording). */
export const verdictForPort = (code: "OK" | "DESC" | "BODY" | "BOTH" | null | undefined): EvalVerdict => (code == null ? "not-evaluated" : code === "OK" ? "healthy" : "being-improved");

/** The "Run skill" day-2 action on AI Skill entities. Port sends this body (JQ templates) to our signed webhook. */
export function runSkillAction(webhookUrl: string) {
  return {
    identifier: "run_ai_skill",
    title: "Run skill",
    icon: "AI",
    description: "Run this governed skill in Skills Factory. Inputs are JSON keyed by the skill's input names (see the Inputs property).",
    trigger: {
      type: "self-service",
      operation: "DAY-2",
      blueprintIdentifier: BLUEPRINT_ID,
      userInputs: {
        properties: {
          inputs: { type: "object", title: "Inputs (JSON)", description: "e.g. {\"workload\": \"feature,requests_per_month,...\"}" },
          note: { type: "string", title: "Why (kept with the run)" },
        },
        required: ["inputs"],
      },
    },
    invocationMethod: {
      type: "WEBHOOK",
      url: webhookUrl,
      agent: false,
      synchronized: false,
      method: "POST",
      body: {
        port_run_id: "{{ .run.id }}",
        skill: "{{ .entity.identifier }}",
        inputs: "{{ .inputs.inputs }}",
        note: "{{ .inputs.note }}",
        requested_by: "{{ .trigger.by.user.email }}",
      },
    },
    requiredApproval: false,
  };
}

/** The webhook body, tolerant of Port rendering `inputs` as an object or as a JSON string. */
export interface PortRunRequest { portRunId: string; skill: string; inputs: Record<string, unknown>; note: string; requestedBy: string; sync: boolean }
export function parsePortRun(body: unknown): PortRunRequest | string {
  if (!body || typeof body !== "object") return "body must be a JSON object";
  const b = body as Record<string, unknown>;
  const portRunId = typeof b.port_run_id === "string" ? b.port_run_id.trim() : "";
  // a workflow's entity input may render as the entity object, its JSON, or its identifier
  let rawSkill: unknown = b.skill;
  if (typeof rawSkill === "string" && rawSkill.trim().startsWith("{")) { try { rawSkill = JSON.parse(rawSkill); } catch { /* keep string */ } }
  const skill = (typeof rawSkill === "string" ? rawSkill : rawSkill && typeof rawSkill === "object" ? String((rawSkill as { identifier?: unknown }).identifier ?? "") : "").trim();
  if (!/^[A-Za-z0-9_-]{4,100}$/.test(portRunId)) return "port_run_id missing or malformed";
  if (!/^[a-z0-9][a-z0-9-]{0,79}$/.test(skill)) return "skill missing or malformed";
  let inputs: unknown = b.inputs ?? {};
  if (typeof inputs === "string") { try { inputs = inputs.trim() ? JSON.parse(inputs) : {}; } catch { return "inputs is not valid JSON"; } }
  if (!inputs || typeof inputs !== "object" || Array.isArray(inputs)) return "inputs must be a JSON object keyed by input name";
  return { portRunId, skill, inputs: inputs as Record<string, unknown>, note: typeof b.note === "string" ? b.note.slice(0, 500) : "", requestedBy: typeof b.requested_by === "string" ? b.requested_by.slice(0, 200) : "", sync: b.mode === "sync" };
}

/** Port workflows (the current self-service model): a self-serve trigger on an AI Skill plus a WEBHOOK node that waits
 *  for our answer (Port allows 10 s; most skills finish in about 1 s, longer runs come back as "accepted" with a link).
 *  Authenticated with a workspace API key stored as the Port secret SF_API_KEY. */
export function runSkillWorkflow(webhookUrl: string) {
  return {
    identifier: "run_ai_skill",
    title: "Run governed skill",
    icon: "AI",
    description: "Run a published Skills Factory skill under its evaluation, approval and audit. Inputs are JSON keyed by the skill's input names (see the Inputs column).",
    category: "Governed AI Skills",
    allowAnyoneToViewRuns: true,
    nodes: [
      {
        identifier: "trigger",
        title: "Run governed skill",
        icon: null,
        description: null,
        config: {
          type: "SELF_SERVE_TRIGGER",
          userInputs: {
            properties: {
              skill: { title: "Skill", type: "string", format: "entity", blueprint: BLUEPRINT_ID },
              inputs: { title: "Inputs (JSON)", type: "string", description: "JSON keyed by the skill input names, e.g. {\"workload\": \"feature,requests_per_month,...\"}" },
              note: { title: "Why (kept with the run)", type: "string" },
            },
            required: ["skill", "inputs"],
            order: ["skill", "inputs", "note"],
          },
        },
      },
      {
        identifier: "run_in_skills_factory",
        title: "Run in Skills Factory",
        icon: null,
        description: "Validated, limited and audited exactly like the API and MCP server.",
        config: {
          type: "WEBHOOK",
          url: webhookUrl,
          method: "POST",
          synchronized: true,
          verbose: true,
          onTimeout: "continue",
          headers: { Authorization: "Bearer {{ .secrets[\"SF_API_KEY\"] }}", "Content-Type": "application/json" },
          body: {
            mode: "sync",
            port_run_id: "{{ .workflowRun.identifier }}",
            skill: "{{ .outputs.trigger.skill }}",
            inputs: "{{ .outputs.trigger.inputs }}",
            note: "{{ .outputs.trigger.note }}",
          },
        },
      },
    ],
    connections: [{ sourceIdentifier: "trigger", targetIdentifier: "run_in_skills_factory", description: null }],
  };
}

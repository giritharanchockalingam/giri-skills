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
  sf_summary: { type: "string", format: "markdown", title: "Start here", description: "What the skill does, whether to trust it, and how to run it — in plain words, from the factory's own data." },
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
      sf_summary: skillSummary(s, portalBase),
    },
    relations: s.registryFileId ? { registry_file: s.registryFileId } : {},
  };
}

/** Plain-language summary for a reader who knows nothing about the factory (the §7 fresh-eyes bar). Every sentence is
 *  derived from the same data the sf_ properties carry; nothing is added that the factory does not know. */
export function skillSummary(s: SkillForPort, portalBase: string): string {
  const base = portalBase.replace(/\/$/, "");
  const verdict = s.verdict ?? "not-evaluated";
  const silver = (s.status ?? "published") === "published" && verdict === "healthy" && s.approved;
  const lines: string[] = [];
  lines.push("## What it does", "", (s.purpose || s.name).trim(), "");
  lines.push("## Can I trust it?", "");
  if ((s.status ?? "published") === "retired") lines.push("**No — retired.** It can no longer be run; this page is kept as the record.", "");
  else if (silver) lines.push("**Yes — trusted for use (Silver).** It passed the factory's evaluation and is approved for exactly the content that runs.", "");
  else if (verdict === "being-improved") lines.push("**Use with care (Bronze).** It is published and evaluated, but below the factory's quality bar and being improved.", "");
  else if (verdict === "not-evaluated") lines.push("**Use with care (Bronze).** It is published but has not been through the factory's behavioural evaluation yet.", "");
  else lines.push("**Use with care (Bronze).** Its approval does not cover the current content.", "");
  const ev = verdict === "healthy" ? "passed the factory's evaluation" : verdict === "being-improved" ? "was evaluated and is below the quality bar" : "has not been evaluated yet";
  const nums = [s.triggerScore != null ? `picked for its own tasks ${Math.round(s.triggerScore * 100)}% of the time` : null, s.lift != null ? `improves answers by ${s.lift >= 0 ? "+" : ""}${s.lift.toFixed(2)} over the model alone` : null, s.evalCases ? `${s.evalCases} test cases` : null].filter(Boolean);
  lines.push(`- **Evaluation:** ${ev}${nums.length ? ` — ${nums.join(", ")}` : ""}${s.evalModel ? ` (graded with ${s.evalModel})` : ""}.`);
  lines.push(`- **Approval:** ${s.approved ? "a reviewer approved this exact version; any edit would void it" : "no valid approval for the current content"}.`);
  lines.push(`- **What runs:** published version ${s.version}, pinned to content hash \`${s.manifest_hash.slice(0, 12)}\`.`);
  if (s.drift === "library_updated") lines.push("- **Library:** a newer copy exists in the skill library; version " + s.version + " is still what runs until a new version is approved.");
  if (s.drift === "blocked") lines.push("- **Library:** the library copy has changed since this version was approved; version " + s.version + " keeps running as approved, and the update needs a new version and review.");
  lines.push(`- **Evidence:** [release page](${base}/skills/${s.slug}/release) — evaluation runs, approval and history.`, "");
  if ((s.status ?? "published") !== "retired") {
    lines.push("## How to run it", "");
    lines.push(`- **In Port:** Workflows → **Run governed skill**, choose “${s.name}”, give the inputs as JSON.`);
    if (s.inputs.some((i) => i.name === "diff")) lines.push("- **On a pull request:** Workflows → **Run governed skill on a PR**, choose the repository, the PR number and this skill — the factory fetches the diff itself.");
    lines.push(`- **From your IDE** (Cursor, Claude Code, any MCP client): tool \`${s.slug}\` on the **skills-factory** MCP server.`);
    if (s.inputs.length) lines.push(`- **Inputs:** ${s.inputs.map((i) => `\`${i.name}\`${i.required ? "" : " (optional)"}`).join(", ")}.`);
    lines.push("- Every run is checked and recorded in Skills Factory, with a link back here.");
  }
  return lines.join("\n");
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
        action: "run_ai_skill",
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

/** Action / workflow identifiers the receiver accepts (spec §6.2: unknown identifiers are rejected). */
export const KNOWN_ACTIONS: ReadonlySet<string> = new Set(["run_ai_skill", "run_sf_skill", "run_sf_skill_on_repo"]);

/** The webhook body, tolerant of Port rendering `inputs` as an object or as a JSON string. */
export interface PortRunRequest { portRunId: string; skill: string; inputs: Record<string, unknown>; note: string; requestedBy: string; sync: boolean; action: string | null; target: string | null; pr: number | null }

/** An entity input as Port renders it in a workflow body: the entity object, its JSON, or its identifier. */
export function entityId(v: unknown): string | null {
  let x: unknown = v;
  if (typeof x === "string" && x.trim().startsWith("{")) { try { x = JSON.parse(x); } catch { /* keep string */ } }
  const id = typeof x === "string" ? x : x && typeof x === "object" ? String((x as { identifier?: unknown }).identifier ?? "") : "";
  return id.trim() ? id.trim() : null;
}
export function parsePortRun(body: unknown): PortRunRequest | string {
  if (!body || typeof body !== "object") return "body must be a JSON object";
  const b = body as Record<string, unknown>;
  const portRunId = typeof b.port_run_id === "string" ? b.port_run_id.trim() : "";
  // a workflow's entity input may render as the entity object, its JSON, or its identifier
  let rawSkill: unknown = b.skill;
  if (typeof rawSkill === "string" && rawSkill.trim().startsWith("{")) { try { rawSkill = JSON.parse(rawSkill); } catch { /* keep string */ } }
  const skill = (typeof rawSkill === "string" ? rawSkill : rawSkill && typeof rawSkill === "object" ? String((rawSkill as { identifier?: unknown }).identifier ?? "") : "").trim();
  if (!/^[A-Za-z0-9_-]{4,100}$/.test(portRunId)) return "port_run_id missing or malformed";
  if (/^sf_live_/i.test(portRunId)) return "port_run_id looks like an API key — refusing to store it";   // a key pasted in the wrong field must never land in a run record
  if (!/^[a-z0-9][a-z0-9-]{0,79}$/.test(skill)) return "skill missing or malformed";
  let inputs: unknown = b.inputs ?? {};
  if (typeof inputs === "string") { try { inputs = inputs.trim() ? JSON.parse(inputs) : {}; } catch { return "inputs is not valid JSON"; } }
  if (!inputs || typeof inputs !== "object" || Array.isArray(inputs)) return "inputs must be a JSON object keyed by input name";
  const action = typeof b.action === "string" && b.action.trim() ? b.action.trim().slice(0, 100) : null;
  if (action !== null && !/^[A-Za-z0-9_-]{1,100}$/.test(action)) return "action identifier malformed";
  // the repository entity the run targets (WP4); a workflow entity input may render as object, JSON or identifier
  const target = entityId(b.target);
  if (target !== null && !/^[A-Za-z0-9_@.\/-]{1,200}$/.test(target)) return "target identifier malformed";
  const prRaw = typeof b.pr === "number" ? b.pr : typeof b.pr === "string" && b.pr.trim() ? Number(b.pr.trim().replace(/^#/, "")) : null;
  if (prRaw !== null && !(Number.isInteger(prRaw) && prRaw > 0 && prRaw < 10_000_000)) return "pr must be a pull request number";
  const pr = prRaw;
  return { portRunId, skill, inputs: inputs as Record<string, unknown>, note: typeof b.note === "string" ? b.note.slice(0, 500) : "", requestedBy: typeof b.requested_by === "string" ? b.requested_by.slice(0, 200) : "", sync: b.mode === "sync", action, target, pr };
}

/** Port workflows (the current self-service model): a self-serve trigger on an AI Skill plus a WEBHOOK node that waits
 *  for our answer (Port allows 10 s; most skills finish in about 1 s, longer runs come back as "accepted" with a link).
 *  Authenticated with a workspace API key stored as the Port secret SF_API_KEY. */
export function runSkillWorkflow(webhookUrl: string) {
  return {
    identifier: "run_governed_skill",                      // the identifier the live org created on 2026-10-20; the body's `action` stays run_ai_skill
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
            action: "run_ai_skill",
            mode: "sync",
            port_run_id: "{{ .workflowRun.identifier }}",
            requested_by: "{{ .trigger.by.user.email }}",
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

/* ── WP4 — run evidence (spec §4.3) and running a skill on a repository (spec §5.3, §7 steps 2–3) ── */

export const RUN_BLUEPRINT_ID = "sf_skill_run";
export const REPOSITORY_BLUEPRINT_ID = "githubRepository";
export const PR_BLUEPRINT_ID = "githubPullRequest";
/** Port's GitHub (Ocean) integration names PR entities `<repository entity id>-pr-<number>` (verified on the tenant, 2026-10-24). */
export const prEntityId = (repository: string, pr: number) => `${repository}-pr-${pr}`;
/** The skill whose succeeded run on a PR's current head counts as "reviewed" (§7). */
export const REVIEW_SKILL = "code-review-runner";

/** One entity per factory run that started from Port. Status words are the factory's own (never a skip shown as a pass). */
export const SKILL_RUN_BLUEPRINT = {
  identifier: RUN_BLUEPRINT_ID,
  title: "Skill run",
  icon: "AI",
  description: "One Skills Factory run started from Port: the exact skill version, its status in the factory's own words, and a link to the evidence.",
  schema: {
    properties: {
      sf_run_id: { type: "string", title: "Factory run id" },
      sf_skill_slug: { type: "string", title: "Skill" },
      sf_skill_version: { type: "string", title: "Skill version" },
      sf_content_hash: { type: "string", title: "Content hash" },
      sf_status: { type: "string", title: "Status", enum: ["succeeded", "failed", "timeout", "needs_input", "skipped-steps"], enumColors: { succeeded: "green", failed: "red", timeout: "orange", needs_input: "yellow", "skipped-steps": "orange" } },
      sf_checks: { type: "string", title: "Output checks passed" },
      sf_started_at: { type: "string", title: "Started", format: "date-time" },
      sf_duration_s: { type: "number", title: "Duration (s)" },
      sf_factory_run_url: { type: "string", title: "Factory run", format: "url" },
      sf_port_run_id: { type: "string", title: "Port run" },
      sf_pr_number: { type: "number", title: "Pull request" },
      sf_head_sha: { type: "string", title: "Head commit" },
      sf_pr_url: { type: "string", title: "Pull request URL", format: "url" },
      sf_is_head_review: { type: "boolean", title: "On the PR's current head", description: "True while the reviewed commit is the PR's head; the factory sets it false when the PR moves on." },
    },
    required: ["sf_run_id", "sf_skill_slug", "sf_status"],
  },
  relations: {
    skill: { title: "Skill", target: BLUEPRINT_ID, required: false, many: false },
    target: { title: "Repository", target: REPOSITORY_BLUEPRINT_ID, required: false, many: false },
    triggered_by: { title: "Triggered by", target: "_user", required: false, many: false },
    pull_request: { title: "Pull request", target: PR_BLUEPRINT_ID, required: false, many: false },
  },
} as const;

/** On every PR: how many succeeded code reviews exist for its CURRENT head (Port computes it from the runs). */
export const PR_REVIEW_AGGREGATION = {
  sf_passing_head_reviews: {
    title: "Passing reviews on head",
    type: "number",
    target: RUN_BLUEPRINT_ID,
    calculationSpec: { calculationBy: "entities", func: "count" },
    query: { combinator: "and", rules: [
      { property: "sf_status", operator: "=", value: "succeeded" },
      { property: "sf_skill_slug", operator: "=", value: REVIEW_SKILL },
      { property: "sf_is_head_review", operator: "=", value: true },
    ] },
  },
} as const;

/** The release gate (§7 step 4): a PR is "reviewed" in Port only with a succeeded code review on its head commit. */
export const PR_REVIEW_GATE_SCORECARD = {
  identifier: "pr_review_gate",
  title: "PR review gate",
  levels: [{ title: "Not reviewed", color: "red" }, { title: "Reviewed", color: "green" }],
  rules: [{
    identifier: "has_passing_review_run", title: "Succeeded code review on the head commit", level: "Reviewed",
    description: "A Skills Factory code-review-runner run succeeded on this PR's current head commit (recorded as a Skill run).",
    query: { combinator: "and", conditions: [{ property: "sf_passing_head_reviews", operator: ">", value: 0 }] },
  }],
} as const;

export interface RunForPort {
  runId: string; slug: string; version: number | null; manifestHash: string | null; status: string; checksPassed: number; checksTotal: number;
  durationMs: number | null; finishedAt: string; factoryUrl: string; portRunId: string;
  repository: string | null; pr: number | null; headSha: string | null; prUrl: string | null; requestedBy: string | null;
}

const RUN_STATUSES = new Set<string>(SKILL_RUN_BLUEPRINT.schema.properties.sf_status.enum);

export function runEntity(r: RunForPort, opts: { withUser: boolean; withPr?: boolean } = { withUser: true }) {
  const started = r.durationMs != null ? new Date(new Date(r.finishedAt).getTime() - r.durationMs).toISOString() : null;
  const relations: Record<string, string> = { skill: portId(r.slug) };
  if (r.repository) relations.target = r.repository;
  if (opts.withUser && r.requestedBy && /@/.test(r.requestedBy)) relations.triggered_by = r.requestedBy;
  if (opts.withPr !== false && r.repository && r.pr) relations.pull_request = prEntityId(r.repository, r.pr);
  return {
    identifier: `run_${r.runId}`,
    title: `${r.slug} v${r.version ?? "?"} — ${r.status}${r.pr ? ` · PR #${r.pr}` : ""}`.slice(0, 200),
    properties: {
      sf_run_id: r.runId,
      sf_skill_slug: r.slug,
      sf_skill_version: r.version == null ? null : String(r.version),
      sf_content_hash: r.manifestHash,
      // an unknown factory status is reported as failed rather than invented into a new word
      sf_status: RUN_STATUSES.has(r.status) ? r.status : "failed",
      sf_checks: `${r.checksPassed}/${r.checksTotal}`,
      sf_started_at: started,
      sf_duration_s: r.durationMs == null ? null : Math.round(r.durationMs / 100) / 10,
      sf_factory_run_url: r.factoryUrl,
      sf_port_run_id: r.portRunId,
      sf_pr_number: r.pr,
      sf_head_sha: r.headSha,
      sf_pr_url: r.prUrl,
      sf_is_head_review: r.pr ? true : null,
    },
    relations,
  };
}

/** Workflow on a GitHub Repository: pick a pull request and a governed skill; the factory pulls the PR diff itself. */
export function runSkillOnRepoWorkflow(webhookUrl: string) {
  return {
    identifier: "run_sf_skill_on_repo",
    title: "Run governed skill on a PR",
    icon: "AI",
    description: "Run a published Skills Factory skill (e.g. Code review) on a pull request of this repository; the run is recorded as a Skill run entity.",
    category: "Governed AI Skills",
    allowAnyoneToViewRuns: true,
    nodes: [
      {
        identifier: "trigger",
        title: "Run governed skill on a PR",
        icon: null,
        description: null,
        config: {
          type: "SELF_SERVE_TRIGGER",
          userInputs: {
            properties: {
              repository: { title: "Repository", type: "string", format: "entity", blueprint: REPOSITORY_BLUEPRINT_ID },
              pr: { title: "Pull request number", type: "number" },
              skill: { title: "Skill", type: "string", format: "entity", blueprint: BLUEPRINT_ID },
              inputs: { title: "Other inputs (JSON, optional)", type: "string", description: "The PR diff is fetched by the factory; add only the skill's other inputs, e.g. {\"spec\": \"…\"}" },
              note: { title: "Why (kept with the run)", type: "string" },
            },
            required: ["repository", "pr", "skill"],
            order: ["repository", "pr", "skill", "inputs", "note"],
          },
        },
      },
      {
        identifier: "run_in_skills_factory",
        title: "Run in Skills Factory",
        icon: null,
        description: "The factory fetches the PR diff, runs the published version, and records a Skill run entity.",
        config: {
          type: "WEBHOOK",
          url: webhookUrl,
          method: "POST",
          synchronized: true,
          verbose: true,
          onTimeout: "continue",
          headers: { Authorization: "Bearer {{ .secrets[\"SF_API_KEY\"] }}", "Content-Type": "application/json" },
          body: {
            action: "run_sf_skill_on_repo",
            mode: "sync",
            port_run_id: "{{ .workflowRun.identifier }}",
            requested_by: "{{ .trigger.by.user.email }}",
            target: "{{ .outputs.trigger.repository }}",
            pr: "{{ .outputs.trigger.pr }}",
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

/* Input schemas for every server action ("use server" files). Each action parses its input here before doing any work.
 *
 * Form schemas mirror exactly how the actions have always read their FormData, so parsing never changes behaviour:
 *   text(max)   — missing → "", cut to max characters, trimmed          (was: String(fd.get(k) ?? "").slice(0, max).trim())
 *   rawText(max)— missing → "", cut to max characters, NOT trimmed      (was: String(fd.get(k) ?? "").slice(0, max))
 *   textList    — every value of a repeated field, as strings           (was: fd.getAll(k).map(String))
 *   number      — Number() of the field; NaN is kept for the action's own range check (was: Number(fd.get(k)))
 * Business rules and their user-facing messages stay in the actions, after the role check, so messages and their order
 * are unchanged. Use: `const input = Schema.parse(fromForm(Schema, fd))`. */
import { z } from "zod";

const first = (v: unknown): unknown => (Array.isArray(v) ? v[0] : v);
/** fd.get(k) semantics on fromForm's arrays: the first value, or null when the field is absent. */
const entry = (v: unknown): unknown => first(v) ?? null;

export const text = (max = 10_000) => z.preprocess((v) => String(entry(v) ?? "").slice(0, max).trim(), z.string());
export const rawText = (max = Infinity) => z.preprocess((v) => String(entry(v) ?? "").slice(0, max), z.string());
export const textList = z.preprocess((v) => (Array.isArray(v) ? v : v == null ? [] : [v]).map(String), z.array(z.string()));
export const number = z.preprocess((v) => Number(entry(v)), z.union([z.number(), z.nan()]));

/** Collect the fields a form schema declares from FormData (all values per key; text fields take the first). */
export function fromForm<S extends z.ZodRawShape>(schema: z.ZodObject<S>, fd: FormData): Record<string, FormDataEntryValue[]> {
  return Object.fromEntries(Object.keys(schema.shape).map((k) => [k, fd.getAll(k)]));
}

/** Actions bound directly to a <form action> with no fields still receive the form's FormData; nothing else is accepted. */
export const NoFields = z.instanceof(FormData).optional();
/** Actions called from client code with no arguments. */
export const NoArgs = z.undefined();
/** ActionForm-driven actions with no fields of their own. */
export const EmptyForm = z.object({});

/* ───────────── app/actions.ts ───────────── */

const id64 = text(64);
const slug80 = text(80);

export const CreateWorkspaceForm = z.object({ name: text(120) });
export const SelectWorkspaceForm = z.object({ workspace_id: id64 });
export const CreateSkillForm = z.object({ name: text(160), slug: text(80), purpose: text(2000), intended_users: text(2000), usage_guidance: text(4000) });
export const UpdateSkillForm = z.object({ skill_id: id64, name: text(160), purpose: text(2000), intended_users: text(2000), usage_guidance: text(4000) });
export const SaveManifestForm = z.object({ version_id: id64, manifest: text(500_000), change_note: text(500) });
export const SaveFileForm = z.object({ version_id: id64, path: text(220), content: rawText(400_000), slug: slug80 });
export const DeleteFileForm = z.object({ version_id: id64, path: text(220), slug: slug80 });
export const UpdateDraftsFromLibraryForm = z.object({ skill_ids: text(200 * 40) });
export const RevokeInvitationForm = z.object({ id: id64 });
export const CreateDraftForm = z.object({ from_version_id: id64, change_note: text(500) });
export const VersionForm = z.object({ version_id: id64, slug: slug80 });
export const ReviewVersionForm = z.object({ version_id: id64, decision: text(10), note: text(2000), slug: slug80 });
export const PublishVersionForm = z.object({ version_id: id64 });
export const RetireVersionForm = z.object({ version_id: id64, note: text(500) });
export const SaveEvalCaseForm = z.object({ version_id: id64, case_id: id64, name: text(160), inputs: text(200_000), checks: text(20_000), notes: text(4000), slug: slug80 });
export const DeleteEvalCaseForm = z.object({ case_id: id64, slug: slug80 });
export const ImportFromRepoForm = z.object({ repo_skill: textList });
export const UpdateFromLibraryForm = z.object({ skill_id: id64 });
export const AddMemberForm = z.object({ email: text(200), role: text(20) });
export const RemoveMemberForm = z.object({ user_id: id64 });
export const CreateApiKeyForm = z.object({ name: text(80) });
export const RevokeApiKeyForm = z.object({ key_id: id64 });
export const SavePolicyForm = z.object({ allowed_tools: textList, allowed_providers: textList, monthly_budget_usd: text(20), max_concurrency: text(5), action_approval: text(20) });
export const SaveConnectionForm = z.object({ name: text(80), kind: text(20), secret_ref: text(64), base_url: text(300) });
export const CancelRunForm = z.object({ run_id: id64 });

/* ───────────── app/agentActions.ts ───────────── */

export const CreateAgentForm = z.object({ name: text(160), template: text(80), description: text(500) });
export const SaveAgentDraftForm = z.object({ version_id: id64, spec: rawText() });
export const NewAgentDraftForm = z.object({ agent_id: id64 });
export const PublishAgentVersionForm = z.object({ version_id: id64 });

/* ───────────── app/talentActions.ts ───────────── */

/** kind: "pool" selects a talent pool; anything else is a role (as before). */
const talentKind = text(8).transform((k): "role" | "pool" => (k === "pool" ? "pool" : "role"));
export const CreateTalentForm = z.object({ kind: talentKind, name: text(160), template: text(80) });
export const SaveTalentDraftForm = z.object({ kind: talentKind, version_id: id64, spec: rawText() });
export const NewTalentDraftForm = z.object({ kind: talentKind, talent_id: id64 });
export const PublishTalentVersionForm = z.object({ kind: talentKind, version_id: id64 });
/** routeTask(roleSkills, task): non-string skills could never match the library, so they are dropped. */
export const RouteTaskArgs = z.tuple([z.array(z.unknown()).transform((a) => a.filter((s): s is string => typeof s === "string")), z.string()]);
export const RouteAnyTaskArgs = z.tuple([z.string()]);

/* ───────────── app/insightsActions.ts ───────────── */

export const SKILL_ID = /^[a-z0-9-]+\/[a-z0-9-]+$/;
/** An integer in [0, max], else null (fields the dashboard counts; anything else is not recorded). */
const boundedInt = (max: number) => z.number().int().min(0).max(max).nullable().catch(null);
export const BrowserRunInput = z.object({
  skill: z.string().regex(SKILL_ID),
  status: z.enum(["succeeded", "failed", "needs_input"]),
  example: z.boolean().catch(false),
  mode: z.enum(["new", "existing"]).nullable().catch(null),
  checksPassed: boundedInt(10_000),
  checksTotal: boundedInt(10_000),
  durationMs: boundedInt(3_600_000),
});
export const SaveBaselineForm = z.object({ skill: text(Infinity), manual_minutes: number, hourly_rate_usd: text(Infinity), owner: text(Infinity), source: text(Infinity) });
export const RemoveBaselineForm = z.object({ skill: rawText() });

/* ───────────── app/catalog/actions.ts ───────────── */

export const DisconnectGithubForm = z.object({ installation_id: number });
export const EntityIdArg = z.string().regex(/^[0-9a-f-]{36}$/);

// access by job role (app/accessActions.ts)
export const SetSkillsByRoleForm = z.object({ enabled: text(5) });
export const AssignRoleForm = z.object({ holder: text(80), talent_id: id64 });
export const UnassignRoleForm = z.object({ id: id64 });
export const RequestAccessForm = z.object({ talent_id: id64, skill: text(200), note: text(1000) });
export const DecideAccessForm = z.object({ id: id64, decision: text(10), note: text(1000) });

/* ───────────── delivery runs (app/api/delivery-runs, app/deliverActions.ts, MCP deliver) ───────────── */

const PIPELINE_NAME = /^[a-z0-9][a-z0-9-]{0,78}$/;
const REPO = /^[\w.-]+\/[\w.-]+$|^[\w./~-]+$/;   // owner/name (catalog) or a local checkout path (IDE)
const REF = /^[\w./-]{0,200}$/;
const STAGE_ID = /^[a-z0-9][a-z0-9-]{0,78}$/;
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/** POST /api/delivery-runs and the MCP `deliver` tool. */
export const DeliveryStartInput = z.object({
  pipeline: z.string().regex(PIPELINE_NAME, "pipeline must be a template name (a-z, 0-9, -)"),
  repo: z.string().trim().min(1).max(300).regex(REPO, "repo must be owner/name or a checkout path"),
  ref: z.string().trim().max(200).regex(REF).optional().default(""),
  request: z.string().trim().min(1, "request is required").max(20_000),
  executor: z.enum(["github-actions", "ide", "local"]).default("github-actions"),
});
export type DeliveryStartInput = z.infer<typeof DeliveryStartInput>;
const Sha256 = z.string().regex(/^[0-9a-f]{64}$/, "sha256 must be 64 hex characters");
/** POST /api/delivery-runs/{id}/stage — one stage record from the executor (DELIVERY-PIPELINES.md → Evidence). */
export const DeliveryStageInput = z.object({
  id: z.string().regex(STAGE_ID),
  adlc_stage: z.string().max(40).optional(),
  role: z.string().max(80).optional(),
  status: z.enum(["queued", "running", "awaiting_approval", "blocked", "failed", "succeeded", "skipped"]),
  gate: z.object({ kind: z.string().max(40), verdict: z.enum(["pass", "fail", "pending"]), detail: z.string().max(4000).optional() }).nullable().optional(),
  evidence: z.array(z.object({ path: z.string().min(1).max(400), sha256: Sha256, bytes: z.number().int().min(0) })).max(200).optional(),
  started_at: z.string().datetime({ offset: true }).nullable().optional(),
  finished_at: z.string().datetime({ offset: true }).nullable().optional(),
  error: z.string().max(4000).nullable().optional(),
  /** run-level facts the executor learns along the way */
  stack_profile: z.record(z.unknown()).optional(),
  pr: z.object({ number: z.number().int().positive().optional(), url: z.string().url().optional(), head_sha: z.string().max(64).optional() }).optional(),
  executor_ref: z.string().max(400).optional(),
});
export type DeliveryStageInput = z.infer<typeof DeliveryStageInput>;
/** POST /api/delivery-runs/{id}/approve */
export const DeliveryApproveInput = z.object({ stage_id: z.string().regex(STAGE_ID), note: z.string().trim().max(2000).default("") });
/** The Deliver page form (app/deliverActions.ts). */
export const StartDeliveryForm = z.object({ pipeline: text(80), repo: text(300), ref: text(200), request: text(20_000), executor: text(20) });
/** Deliver page → "No template fits? Compose one": the composition inputs, and the same plus the run inputs to start it. */
export const ComposeDeliveryForm = z.object({ repo: text(300), request_kind: text(40), mode: text(20) });
export const StartComposedDeliveryForm = z.object({ repo: text(300), request_kind: text(40), mode: text(20), ref: text(200), request: text(20_000), executor: text(20) });
export const ComposeInputSchema = z.object({
  repo: z.string().trim().min(1).max(300).regex(/^[\w.-]+\/[\w.-]+$/, "repo must be owner/name as the catalog lists it"),
  request_kind: z.string().regex(/^[a-z][a-z-]{0,39}$/, "request_kind must be a kind id"),
  mode: z.enum(["brownfield", "greenfield"]).optional(),
});
export type ComposeInputSchema = z.infer<typeof ComposeInputSchema>;
export const ApproveDeliveryForm = z.object({ run_id: id64, stage_id: text(80), note: text(2000) });

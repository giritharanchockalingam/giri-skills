/* POST /api/eval-runs/{id}/step — runs the next pending case of an evaluation run and records its result.
 * A case passes when every one of its deterministic checks passes. pass_rate = passed cases / cases. */
import { apiContext, apiError, json } from "@/lib/factory/http";
import { can } from "@/lib/factory/roles";
import { validateInputs, describeInputs } from "@/lib/factory/schema";
import { sha256 } from "@/lib/factory/hash";
import { executeRun } from "@/lib/factory/runtime";
import { getPolicy, must, type EvalCaseRow, type EvalRunRow, type VersionRow } from "@/lib/factory/db";

export const maxDuration = 60;
export const dynamic = "force-dynamic";

export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const ctx = await apiContext();
  if (!ctx) return apiError(401, "unauthenticated", "Sign in and select a workspace.");
  if (!can(ctx.role, "eval.run")) return apiError(403, "forbidden", `Your role (${ctx.role}) cannot run evaluations.`);
  const { id } = await params;
  const { data: er } = await ctx.supabase.from("sf_eval_runs").select("*").eq("id", id).maybeSingle();
  const evalRun = er as EvalRunRow | null;
  if (!evalRun) return apiError(404, "not_found", "Evaluation run not found.");
  if (evalRun.status !== "running") return json({ done: true, status: evalRun.status, pass_rate: evalRun.pass_rate, results: evalRun.results });
  const next = evalRun.results.find((r) => r.status === "pending");
  if (!next) return finish(ctx, evalRun);

  const { data: v } = await ctx.supabase.from("sf_skill_versions").select("*, sf_skills!sf_skill_versions_skill_id_fkey(slug, workspace_id)").eq("id", evalRun.version_id).single();
  const version = v as VersionRow & { sf_skills: { slug: string; workspace_id: string } };
  if (version.sf_skills.workspace_id !== ctx.workspace.id) return apiError(404, "not_found", "Version not found.");
  const { data: c } = await ctx.supabase.from("sf_eval_cases").select("*").eq("id", next.case_id).maybeSingle();
  const evalCase = c as EvalCaseRow | null;
  const t0 = Date.now();
  let result = { ...next };
  if (!evalCase) {
    result = { ...result, status: "failed", error: "case was deleted after the evaluation started", duration_ms: 0 };
  } else {
    const validated = validateInputs(version.manifest, evalCase.inputs, { allowFixtures: true });
    const assume = (evalCase.expected?.assume ?? {}) as Record<string, string>;
    const assumptions = Object.fromEntries(Object.entries(assume).filter(([k, val]) => typeof val === "string" && version.manifest.inputs.some((i) => i.name === k)));
    if (validated.problems.length) {
      result = { ...result, status: "failed", error: "invalid case inputs: " + validated.problems.map((p) => `${p.path} ${p.message}`).join("; "), duration_ms: 0 };
    } else {
      const checks = Array.isArray(evalCase.checks) ? evalCase.checks : [];
      const { data: created, error } = await ctx.supabase.rpc("sf_run_insert", { p_version: version.id, p_source: "eval", p_inputs_ref: describeInputs(validated.inputs, sha256), p_idempotency_key: null });
      if (error || created?.error) {
        result = { ...result, status: "failed", error: error?.message ?? String(created.message), duration_ms: 0 };
      } else {
        const runId = String(created.run_id);
        await ctx.supabase.from("sf_runs").update({ status: "running", started_at: new Date().toISOString() }).eq("id", runId);
        const files = version.source.kind === "authored" ? (must(await ctx.supabase.from("sf_files").select("path, content").eq("version_id", version.id), "files") as { path: string; content: string }[]) : [];
        const patch = await executeRun({ runId, manifest: version.manifest, source: version.source, slug: version.sf_skills.slug, files, inputs: validated.inputs, assumptions, policy: await getPolicy(ctx), checks, status: version.status, versionId: version.id });
        const { response, ...row } = patch;
        await ctx.supabase.from("sf_runs").update(row).eq("id", runId);
        const cc = response?.case_checks ?? [];
        const passed = cc.filter((x) => x.pass).length;
        const noChecks = checks.length === 0;
        result = {
          ...result, run_id: runId, status: row.status, checks: cc, passed, total: cc.length, duration_ms: Date.now() - t0,
          error: noChecks ? "case has no checks — nothing to verify" : row.status === "timeout" || row.error?.startsWith("runtime") ? row.error : null,
        };
      }
    }
  }
  const results = evalRun.results.map((r) => (r.case_id === next.case_id ? result : r));
  const { error: ue } = await ctx.supabase.from("sf_eval_runs").update({ results }).eq("id", id);
  if (ue) return apiError(500, "persist_failed", ue.message);
  const remaining = results.filter((r) => r.status === "pending").length;
  if (remaining === 0) return finish(ctx, { ...evalRun, results });
  return json({ done: false, remaining, last: result, results });
}

const casePassed = (r: EvalRunRow["results"][number]) => r.total > 0 && r.passed === r.total && !["timeout", "cancelled"].includes(r.status) && !(r.error && r.error.startsWith("runtime"));

async function finish(ctx: Awaited<ReturnType<typeof apiContext>> & object, evalRun: EvalRunRow) {
  const passedCases = evalRun.results.filter(casePassed).length;
  const passRate = evalRun.results.length ? passedCases / evalRun.results.length : 0;
  const { error } = await ctx.supabase.from("sf_eval_runs").update({ status: "finished", pass_rate: passRate, finished_at: new Date().toISOString() }).eq("id", evalRun.id);
  if (error) return apiError(500, "persist_failed", error.message);
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "eval.finish", p_entity_type: "eval_run", p_entity_id: evalRun.id, p_details: { version_id: evalRun.version_id, pass_rate: passRate, cases: evalRun.results.length, passed: passedCases } });
  return json({ done: true, status: "finished", pass_rate: passRate, results: evalRun.results });
}

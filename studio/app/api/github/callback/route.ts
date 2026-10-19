/* Install / update redirect from GitHub: ?code&installation_id&setup_action&state.
 * Links the installation to the workspace only after PROVING the signed-in GitHub user can access it
 * (OAuth code → user token → /user/installations). Then runs the first sync. */
import { NextResponse } from "next/server";
import { getContext } from "@/lib/factory/db";
import { githubConfig, verifyState, exchangeCode, userCanAccessInstallation, getInstallation, GithubError } from "@/lib/github/app";
import { syncWorkspace } from "@/lib/github/sync";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function GET(req: Request) {
  const url = new URL(req.url);
  const back = (q: string) => NextResponse.redirect(new URL(`/catalog?${q}`, req.url));
  const c = githubConfig();
  if (!c.ok) return back("error=not-configured");
  const ctx = await getContext();
  const q = url.searchParams;
  const installationId = Number(q.get("installation_id"));
  const code = q.get("code") ?? "";
  if (!Number.isSafeInteger(installationId) || installationId <= 0) return back("error=missing-installation");

  // workspace: from the signed state when GitHub carried it, else the user's current workspace
  const state = q.get("state");
  const st = state ? verifyState(state, c.cfg.clientSecret) : null;
  if (state && (!st || st.u !== ctx.user.id)) return back("error=bad-state");
  const ws = ctx.memberships.find((m) => m.workspace_id === (st?.w ?? ctx.workspace?.id));
  if (!ws || ws.role !== "admin") return back("error=admin-only");

  try {
    if (!code) return back("error=no-oauth-code");      // the App must request authorization during install (manifest sets it)
    const userToken = await exchangeCode(c.cfg, code);
    if (!(await userCanAccessInstallation(userToken, installationId))) return back("error=not-your-installation");
    const inst = await getInstallation(c.cfg, installationId);
    const row = {
      workspace_id: ws.workspace_id, installation_id: installationId, account_login: inst.account.login,
      account_type: inst.account.type === "Organization" ? "Organization" : "User",
      repository_selection: inst.repository_selection, suspended_at: inst.suspended_at, verified_by: ctx.user.id,
    };
    const { data: existing } = await ctx.supabase.from("sf_github_installations").select("workspace_id").eq("installation_id", installationId).maybeSingle();
    if (existing && existing.workspace_id !== ws.workspace_id) return back("error=linked-elsewhere");
    const { error } = existing
      ? await ctx.supabase.from("sf_github_installations").update(row).eq("installation_id", installationId)
      : await ctx.supabase.from("sf_github_installations").insert(row);
    if (error) return back(`error=${encodeURIComponent(error.code === "23505" ? "linked-elsewhere" : "save-failed")}`);
    await ctx.supabase.rpc("sf_audit", { p_workspace: ws.workspace_id, p_action: existing ? "github.update" : "github.connect", p_entity_type: "github_installation",
      p_entity_id: String(installationId), p_details: { account: inst.account.login, selection: inst.repository_selection } });
    const r = await syncWorkspace(ctx.supabase, ws.workspace_id, ctx.user.id, c.cfg);
    return back(`connected=${encodeURIComponent(inst.account.login)}&synced=${r.repos}`);
  } catch (e) {
    const msg = e instanceof GithubError ? e.message : (e as Error).message;
    return back(`error=github&detail=${encodeURIComponent(msg.slice(0, 180))}`);
  }
}

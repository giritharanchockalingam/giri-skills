/* GitHub redirects here after "Create GitHub App" (manifest flow) with a one-time code. We convert it into the App's
 * credentials and show them ONCE, for an administrator to put into the deployment's environment (Vercel). They are
 * not stored in the database and not logged. Refused once the App is configured. */
import { NextResponse } from "next/server";
import { getContext } from "@/lib/factory/db";
import { githubConfig, gh, GithubError } from "@/lib/github/app";

export const dynamic = "force-dynamic";
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));

export async function GET(req: Request) {
  const ctx = await getContext();
  if (ctx.role !== "admin") return NextResponse.json({ error: { code: "forbidden", message: "Workspace administrators only." } }, { status: 403 });
  if (githubConfig().ok) return NextResponse.redirect(new URL("/catalog?notice=already-configured", req.url));
  const code = new URL(req.url).searchParams.get("code") ?? "";
  if (!/^[A-Za-z0-9_-]{8,100}$/.test(code)) return NextResponse.json({ error: { code: "bad_request", message: "Missing or invalid code." } }, { status: 400 });
  let app: { id: number; slug: string; client_id: string; client_secret: string; webhook_secret: string | null; pem: string; owner: { login: string }; html_url: string };
  try {
    app = (await gh<typeof app>(`/app-manifests/${code}/conversions`, "", { method: "POST" })).data;
  } catch (e) {
    return NextResponse.json({ error: { code: "github_failed", message: e instanceof GithubError ? e.message : "GitHub did not accept the code (it is single-use and expires after an hour)." } }, { status: 502 });
  }
  const env: [string, string][] = [
    ["GITHUB_APP_ID", String(app.id)], ["GITHUB_APP_SLUG", app.slug], ["GITHUB_APP_CLIENT_ID", app.client_id],
    ["GITHUB_APP_CLIENT_SECRET", app.client_secret], ["GITHUB_WEBHOOK_SECRET", app.webhook_secret ?? ""], ["GITHUB_APP_PRIVATE_KEY", app.pem],
  ];
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GitHub App created</title>
<meta name="referrer" content="no-referrer"><style>body{font:15px/1.5 system-ui,sans-serif;max-width:860px;margin:40px auto;padding:0 16px;color:#0f1a21}
code,pre{font:12.5px ui-monospace,Menlo,monospace}pre{background:#eef2f5;padding:10px;border-radius:8px;white-space:pre-wrap;word-break:break-all}
.warn{background:#f8efd8;padding:10px 12px;border-radius:8px}button{font:600 13px system-ui;padding:6px 12px;border-radius:999px;border:1px solid #bbb;background:#fff;cursor:pointer}</style></head><body>
<h1>GitHub App “${esc(app.slug)}” created</h1>
<p class="warn"><b>Shown once.</b> Add these six values to the Vercel project's Environment Variables (Production), then redeploy. They are not saved anywhere else — if you lose this page, generate a new private key in the App's settings on GitHub.</p>
${env.map(([k, v]) => `<h3><code>${k}</code> <button onclick="navigator.clipboard.writeText(document.getElementById('${k}').textContent)">Copy</button></h3><pre id="${k}">${esc(v)}</pre>`).join("\n")}
<p>App settings: <a href="${esc(app.html_url)}" rel="noreferrer">${esc(app.html_url)}</a>. After redeploying, open <a href="/catalog">Platform › Repositories</a> and choose <b>Connect GitHub</b>.</p>
</body></html>`;
  return new NextResponse(html, { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store, max-age=0", "X-Robots-Tag": "noindex" } });
}

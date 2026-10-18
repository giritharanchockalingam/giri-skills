import Link from "next/link";
import { loadSkillPage } from "@/lib/factory/skillPage";
import { can } from "@/lib/factory/roles";
import { runtimeConfig } from "@/lib/factory/runtime";
import { requirements } from "@/lib/factory/manifest";
import type { ConnectionRow } from "@/lib/factory/db";
import { VersionBar } from "@/components/factory/VersionBar";
import { TestForm } from "@/components/factory/TestForm";

export const dynamic = "force-dynamic";

/** Test: the run form only. What the run needs (tools, connections) sits beside it; runs are listed under Activity. */
export default async function TestPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ v?: string }> }) {
  const { slug } = await params; const { v } = await searchParams;
  const d = await loadSkillPage(slug, v ?? null);
  const allowed = can(d.ctx.role, d.version.status === "published" ? "run.published" : "run.any_version") && !["retired", "superseded"].includes(d.version.status);
  const cfg = runtimeConfig();
  const serverKey = Boolean(process.env.ANTHROPIC_API_KEY);
  const req = requirements(d.version.manifest);
  const { data: conns } = req.connections.length > 0
    ? await d.ctx.supabase.from("sf_connections").select("*").eq("workspace_id", d.ctx.workspace.id)
    : { data: null };
  const connections = (conns ?? []) as ConnectionRow[];
  const vq = `?v=${d.version.version}`;
  return (
    <>
      <VersionBar slug={slug} view="test" versions={d.versions} current={d.version} />
      <div className="detail-grid">
        <div className="card card-pad min-w-0">
          <div className="h3">Test skill</div>
          <p className="caption mt-1 mb-4">Real inputs → v{d.version.version} runs on the server → outputs checked → recorded as a run.</p>
          {allowed ? (
            <TestForm versionId={d.version.id} manifest={d.version.manifest} runtimeOk={cfg.ok} runtimeReason={cfg.reason} keyPresent={serverKey} slug={slug} />
          ) : (
            <div className="notice notice-info">{["retired", "superseded"].includes(d.version.status) ? `Version v${d.version.version} is ${d.version.status} and cannot be run.` : `Your role (${d.ctx.role}) can only run published versions. ${d.published ? `Published: v${d.published.version}.` : "This skill has no published version yet."}`}</div>
          )}
        </div>
        <aside className="sidebar">
          <div className="card card-pad">
            <div className="h3 mb-2">Needs</div>
            <dl className="kv">
              <dt>Tools</dt><dd>{req.tools.length ? req.tools.join(", ") : "none"}</dd>
              <dt>Connections</dt>
              <dd>{req.connections.length === 0 ? "none" : req.connections.map((c) => {
                const row = connections.find((x) => x.name === c);
                const ok = c === "anthropic" ? serverKey : row?.status === "configured";
                return <div key={c}><code>{c}</code> — {ok ? <span className="pass">configured</span> : <span className="fail">not configured</span>}{c === "anthropic" && !serverKey && <span className="caption"> (ANTHROPIC_API_KEY missing on the server; llm steps will be skipped)</span>}</div>;
              })}</dd>
              <dt>Runs</dt><dd>{d.runCount} of v{d.version.version} · <Link href={`/skills/${slug}/activity/${vq}`} className="link">Activity</Link></dd>
            </dl>
            {can(d.ctx.role, "admin.connections") && <Link href="/admin#connections" className="link-flame mt-3 inline-block">Manage connections →</Link>}
          </div>
          {d.version.source.kind === "repo" && (
            <div className="card card-pad">
              <div className="h3 mb-1">Run in browser (no server)</div>
              <p className="caption">The repository page runs the same runner in your browser with Pyodide. Nothing is recorded, and an API key you paste there goes from your browser straight to the provider.</p>
              <Link href={`/repo/${d.version.source.repo_skill}/test/`} className="btn btn-secondary btn-sm mt-3">Open browser runner</Link>
            </div>
          )}
        </aside>
      </div>
    </>
  );
}

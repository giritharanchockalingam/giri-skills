import Link from "next/link";
import { loadSkillPage } from "@/lib/factory/skillPage";
import { can } from "@/lib/factory/roles";
import { runtimeConfig } from "@/lib/factory/runtime";
import { fmtDate } from "@/lib/factory/db";
import { VersionBar } from "@/components/factory/VersionBar";
import { TestForm } from "@/components/factory/TestForm";
import { RunPill } from "@/components/factory/Pills";
import type { RunRow } from "@/lib/factory/db";

export const dynamic = "force-dynamic";

export default async function TestPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ v?: string }> }) {
  const { slug } = await params; const { v } = await searchParams;
  const d = await loadSkillPage(slug, v ?? null);
  const allowed = can(d.ctx.role, d.version.status === "published" ? "run.published" : "run.any_version") && !["retired", "superseded"].includes(d.version.status);
  const cfg = runtimeConfig();
  const { data: recent } = await d.ctx.supabase.from("sf_runs").select("id, status, created_at, source, duration_ms, error").eq("version_id", d.version.id).order("created_at", { ascending: false }).limit(5);
  return (
    <>
      <VersionBar slug={slug} view="test" versions={d.versions} current={d.version} />
      <div className="two-col">
        <div className="card card-pad min-w-0">
          <div className="h3">Test skill</div>
          <p className="caption mt-1 mb-4">Supply a real input. The server validates it against the contract, runs the exact version v{d.version.version} with the repository runner, validates the outputs, and records everything as a run you can inspect.</p>
          {allowed ? (
            <TestForm versionId={d.version.id} manifest={d.version.manifest} runtimeOk={cfg.ok} runtimeReason={cfg.reason} keyPresent={Boolean(process.env.ANTHROPIC_API_KEY)} slug={slug} />
          ) : (
            <div className="notice notice-info">{["retired", "superseded"].includes(d.version.status) ? `Version v${d.version.version} is ${d.version.status} and cannot be run.` : `Your role (${d.ctx.role}) can only run published versions. ${d.published ? `Published: v${d.published.version}.` : "This skill has no published version yet."}`}</div>
          )}
        </div>
        <aside className="sidebar">
          <div className="card card-pad">
            <div className="h3 mb-2">Recent runs of v{d.version.version}</div>
            <div className="list">
              {((recent ?? []) as Pick<RunRow, "id" | "status" | "created_at" | "source" | "duration_ms" | "error">[]).map((r) => (
                <Link key={r.id} href={`/runs/${r.id}`} className="list-row row-link"><span className="min-w-0"><span className="name">{fmtDate(r.created_at)}</span><div className="meta"><span>{r.source}</span>{r.duration_ms != null && <span>{(r.duration_ms / 1000).toFixed(1)} s</span>}</div></span><RunPill status={r.status} small /></Link>
              ))}
              {(recent ?? []).length === 0 && <p className="none">No runs yet.</p>}
            </div>
            <Link href={`/skills/${slug}/activity?v=${d.version.version}`} className="link-flame mt-3 inline-block">All activity →</Link>
          </div>
          {d.version.source.kind === "repo" && (
            <div className="card card-pad">
              <div className="h3 mb-1">Run in browser (no server)</div>
              <p className="caption">The repository page runs the same runner in your browser with Pyodide. Nothing is recorded, and an API key you paste there goes from your browser straight to the provider.</p>
              <Link href={`/repo/${d.version.source.repo_skill}/#run`} className="btn btn-secondary btn-sm mt-3">Open browser runner</Link>
            </div>
          )}
        </aside>
      </div>
    </>
  );
}

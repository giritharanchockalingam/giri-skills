import Link from "next/link";
import { loadSkillPage } from "@/lib/factory/skillPage";
import { can } from "@/lib/factory/roles";
import { type FileRow } from "@/lib/factory/db";
import { VersionBar } from "@/components/factory/VersionBar";
import { FileEditor } from "@/components/factory/FileEditor";

export const dynamic = "force-dynamic";

/** Files: the resources packaged with this version — editable for authored drafts, read-only from the repository bundle. */
export default async function FilesPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ v?: string }> }) {
  const { slug } = await params; const { v } = await searchParams;
  const d = await loadSkillPage(slug, v ?? null);
  const editable = can(d.ctx.role, "version.edit") && d.version.status === "draft";
  const authored = d.version.source.kind === "authored";
  const { data: files } = authored
    ? await d.ctx.supabase.from("sf_files").select("path, content, sha256, updated_at").eq("version_id", d.version.id).order("path")
    : { data: null };
  return (
    <>
      <VersionBar slug={slug} view="files" versions={d.versions} current={d.version} />
      {authored ? (
        <div className="card card-pad">
          <div className="h3 mb-1">Resources <span className="muted font-normal">({(files ?? []).length})</span></div>
          <p className="caption mb-4">Scripts, templates and reference files packaged with this version. Steps run <code>python3 scripts/&lt;file&gt;</code> inside the run folder with the environment scrubbed.</p>
          <FileEditor versionId={d.version.id} slug={slug} files={(files ?? []) as FileRow[]} editable={editable} />
        </div>
      ) : (
        <div className="card card-pad">
          <div className="h3 mb-1">Resources <span className="muted font-normal">({d.version.manifest.resources.length})</span></div>
          <p className="caption mb-3">From the repository bundle at build time; read-only here. To change them, edit the repository skill (<Link href={`/repo/${d.version.source.repo_skill}/files/`} className="link">{d.version.source.repo_skill}</Link>) and re-import as a new draft.</p>
          <ul className="file-list">{d.version.manifest.resources.map((r) => <li key={r}>{r}</li>)}</ul>
        </div>
      )}
    </>
  );
}

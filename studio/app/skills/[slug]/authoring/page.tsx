import Link from "next/link";
import { loadSkillPage } from "@/lib/factory/skillPage";
import { can } from "@/lib/factory/roles";
import { type FileRow } from "@/lib/factory/db";
import { updateSkill, createDraft } from "@/app/actions";
import { ActionForm } from "@/components/factory/ActionForm";
import { VersionBar } from "@/components/factory/VersionBar";
import { ManifestEditor } from "@/components/factory/ManifestEditor";
import { FileEditor } from "@/components/factory/FileEditor";

export const dynamic = "force-dynamic";

export default async function AuthoringPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ v?: string }> }) {
  const { slug } = await params; const { v } = await searchParams;
  const d = await loadSkillPage(slug, v ?? null);
  const canEdit = can(d.ctx.role, "version.edit");
  const editable = canEdit && d.version.status === "draft";
  const { data: files } = await d.ctx.supabase.from("sf_files").select("path, content, sha256, updated_at").eq("version_id", d.version.id).order("path");
  return (
    <>
      <VersionBar slug={slug} view="authoring" versions={d.versions} current={d.version}
        right={canEdit && d.version.status !== "draft" && (
          <ActionForm action={createDraft} submit="Create improved draft" submitClass="btn btn-primary" hidden={{ from_version_id: d.version.id }} />
        )} />
      {!canEdit && <div className="notice notice-info mb-5">Your role ({d.ctx.role}) can read the contract but not change it. Authors and admins edit drafts.</div>}
      <div className="stack">
        <div className="card card-pad">
          <div className="h3 mb-3">Skill details</div>
          <ActionForm action={updateSkill} submit="Save details" hidden={{ skill_id: d.skill.id }} disabled={!canEdit}>
            <div className="form-grid form-grid-2">
              <div className="field span-2"><label htmlFor="s-name">Name</label><input id="s-name" name="name" className="input" defaultValue={d.skill.name} required maxLength={160} disabled={!canEdit} /></div>
              <div className="field span-2"><label htmlFor="s-purpose">Purpose</label><textarea id="s-purpose" name="purpose" className="textarea" style={{ minHeight: 72 }} defaultValue={d.skill.purpose} maxLength={2000} disabled={!canEdit} /></div>
              <div className="field"><label htmlFor="s-users">Intended users</label><textarea id="s-users" name="intended_users" className="textarea" style={{ minHeight: 64 }} defaultValue={d.skill.intended_users} maxLength={2000} disabled={!canEdit} /></div>
              <div className="field"><label htmlFor="s-usage">When to use it</label><textarea id="s-usage" name="usage_guidance" className="textarea" style={{ minHeight: 64 }} defaultValue={d.skill.usage_guidance} maxLength={4000} disabled={!canEdit} /></div>
            </div>
          </ActionForm>
          <p className="caption mt-3">These describe the skill in the catalog. The contract below is versioned; saving it also mirrors purpose/users/guidance here.</p>
        </div>

        <div className="card card-pad">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
            <div><div className="h3">Contract — v{d.version.version}</div><p className="caption">Inputs, outputs, steps, model, limits and release criteria. Saving re-hashes the manifest; a reviewer&apos;s approval is pinned to that hash.</p></div>
            {d.version.source.kind === "repo" && <span className="caption">Scripts and assets come from the repository bundle (<Link href={`/repo/${d.version.source.repo_skill}/`} className="link">{d.version.source.repo_skill}</Link>).</span>}
          </div>
          <ManifestEditor versionId={d.version.id} slug={slug} manifest={d.version.manifest} editable={editable} />
        </div>

        {d.version.source.kind === "authored" ? (
          <div className="card card-pad">
            <div className="h3 mb-1">Resources</div>
            <p className="caption mb-4">Scripts, templates and reference files packaged with this version. Steps run <code>python3 scripts/&lt;file&gt;</code> inside the run folder with the environment scrubbed.</p>
            <FileEditor versionId={d.version.id} slug={slug} files={(files ?? []) as FileRow[]} editable={editable} />
          </div>
        ) : (
          <div className="card card-pad">
            <div className="h3 mb-1">Resources <span className="muted font-normal">({d.version.manifest.resources.length})</span></div>
            <p className="caption mb-3">From the repository bundle at build time; read-only here. To change them, edit the repository skill and re-import as a new draft.</p>
            <ul className="file-list">{d.version.manifest.resources.map((r) => <li key={r}>{r}</li>)}</ul>
          </div>
        )}
      </div>
    </>
  );
}

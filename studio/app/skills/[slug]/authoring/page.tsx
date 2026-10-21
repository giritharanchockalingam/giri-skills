import Link from "next/link";
import { loadSkillPage } from "@/lib/factory/skillPage";
import { can } from "@/lib/factory/roles";
import { mdToHtml } from "@/lib/markdown.mjs";
import { updateSkill, createDraft } from "@/app/actions";
import { ActionForm } from "@/components/factory/ActionForm";
import { VersionBar } from "@/components/factory/VersionBar";
import { ManifestEditor } from "@/components/factory/ManifestEditor";

export const dynamic = "force-dynamic";

export default async function AuthoringPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ v?: string }> }) {
  const { slug } = await params; const { v } = await searchParams;
  const d = await loadSkillPage(slug, v ?? null);
  const canEdit = can(d.ctx.role, "version.edit");
  const editable = canEdit && d.version.status === "draft";
  const instructions = d.version.manifest.instructions_md.trim();
  return (
    <>
      <VersionBar slug={slug} view="authoring" versions={d.versions} current={d.version}
        right={canEdit && d.version.status !== "draft" && (
          <ActionForm action={createDraft} submit="Create improved draft" submitClass="btn btn-primary" hidden={{ from_version_id: d.version.id }} />
        )} />
      {!canEdit && <div className="notice notice-info mb-5">Your role ({d.ctx.role}) can read the contract but not change it. Authors and admins edit drafts.</div>}
      <div className="stack">
        <div className="card card-pad">
          <div className="eyebrow mb-4">Instructions · v{d.version.version}</div>
          {instructions ? <div className="prose" dangerouslySetInnerHTML={{ __html: mdToHtml(instructions) }} /> : <p className="none">No instructions written yet{editable ? " — add them in the contract below (Instructions, Markdown)." : "."}</p>}
        </div>
        <details className="disclosure">
          <summary>Skill details</summary>
          <div className="card card-pad mt-3">
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
        </details>

        <div className="card card-pad">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
            <div><div className="h3">Contract — v{d.version.version}</div><p className="caption">Inputs, outputs, steps, model, limits and release criteria. Saving re-hashes the manifest; a reviewer&apos;s approval is pinned to that hash.</p></div>
            {d.version.source.kind === "repo" && <span className="caption">Scripts and assets come from the repository bundle (<Link href={`/library/${d.version.source.repo_skill}/`} className="link">{d.version.source.repo_skill}</Link>).</span>}
          </div>
          <ManifestEditor versionId={d.version.id} slug={slug} manifest={d.version.manifest} editable={editable} />
        </div>

      </div>
    </>
  );
}

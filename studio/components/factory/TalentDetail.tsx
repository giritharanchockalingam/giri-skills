/* Server component: header, versions, publish/draft controls and the editor for one role or pool. */
import Link from "next/link";
import { notFound } from "next/navigation";
import { requireWorkspace } from "@/lib/factory/db";
import { can } from "@/lib/factory/roles";
import { PageHead } from "@/components/PageHead";
import { ActionForm } from "@/components/factory/ActionForm";
import { RoleEditor, PoolEditor } from "@/components/factory/TalentEditors";
import { newTalentDraft, publishTalentVersion } from "@/app/talentActions";
import { ROLE_TEMPLATES, skillCatalogLite, workspacePlaybooks, workspaceRoles } from "@/lib/factory/talentData";
import { getTalentBySlug, listTalentVersions } from "@/lib/db/talent";
import { STAGES, SHELVES } from "@/lib/data";

export async function TalentDetail({ kind, slug, v }: { kind: "role" | "pool"; slug: string; v?: string }) {
  const ctx = await requireWorkspace();
  const talent = await getTalentBySlug(ctx.supabase, ctx.workspace.id, kind, slug);
  if (!talent) notFound();
  const versions = await listTalentVersions(ctx.supabase, talent.id);
  const current = versions.find((x) => String(x.version) === v) ?? versions.find((x) => x.status === "draft") ?? versions[0];
  if (!current) notFound();
  const editable = current.status === "draft" && can(ctx.role, "talent.edit");
  const base = kind === "role" ? "/roles" : "/pools";
  const [playbooks, roles] = await Promise.all([workspacePlaybooks(ctx), kind === "pool" ? workspaceRoles(ctx) : Promise.resolve(new Map())]);
  const stages = [...STAGES, ...SHELVES];
  const catalog = skillCatalogLite();

  return (
    <>
      <PageHead eyebrow={`${kind === "role" ? "Roles" : "Talent pools"} · ${talent.slug}`} title={talent.name} em="" lead={talent.description}
        caption={<span className="chip-group">{versions.map((x) => <Link key={x.id} href={`${base}/${slug}?v=${x.version}`} className="chip" aria-pressed={x.id === current.id}>v{x.version} · {x.status}</Link>)}</span>} />
      <div className="action-row mb-6" style={{ marginTop: 0 }}>
        {current.status === "draft" && can(ctx.role, "talent.publish") && <ActionForm action={publishTalentVersion} submit="Publish" submitClass="btn btn-secondary" confirm={`Publish v${current.version}? It becomes frozen.`} hidden={{ kind, version_id: current.id }} />}
        {current.status !== "draft" && !versions.some((x) => x.status === "draft") && can(ctx.role, "talent.edit") && <ActionForm action={newTalentDraft} submit="Edit as new draft" submitClass="btn btn-secondary" hidden={{ kind, talent_id: talent.id }} />}
        {!editable && current.status === "draft" && <span className="caption">Read-only for your role.</span>}
        {current.status !== "draft" && <span className="caption">v{current.version} is {current.status} and frozen.</span>}
      </div>
      {kind === "role"
        ? <RoleEditor key={current.id} initial={{ ...current.spec, name: slug }} template={ROLE_TEMPLATES.find((r) => r.name === (current.spec.based_on ?? talent.based_on))}
            versionId={current.id} catalog={catalog} stages={stages} playbooks={[...playbooks.values()]} editable={editable} />
        : <PoolEditor key={current.id} initial={{ ...current.spec, name: slug }} versionId={current.id} roles={[...roles.values()]} catalog={catalog} stages={stages}
            playbooks={[...playbooks.values()]} editable={editable} />}
    </>
  );
}

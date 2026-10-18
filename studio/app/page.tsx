import Link from "next/link";
import { requireWorkspace, type SkillRow, type VersionRow, type ReleaseStateRow } from "@/lib/factory/db";
import { can } from "@/lib/factory/roles";
import { skills as repoSkills, STAGES, SHELVES, stageOfRepoSkill } from "@/lib/data";
import { PageHead } from "@/components/PageHead";
import { SkillsCatalog, type CatalogItem } from "@/components/factory/SkillsCatalog";
import { ImportDrawer } from "@/components/factory/ImportDrawer";

export const metadata = { title: "Skills · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function SkillsPage({ searchParams }: { searchParams: Promise<{ import?: string; stage?: string }> }) {
  const sp = await searchParams;
  const ctx = await requireWorkspace();
  const sb = ctx.supabase;
  const [skillsQ, versionsQ, statesQ] = await Promise.all([
    sb.from("sf_skills").select("*").eq("workspace_id", ctx.workspace.id).order("updated_at", { ascending: false }),
    sb.from("sf_skill_versions").select("id, skill_id, version, status, source, updated_at").order("version", { ascending: false }),
    sb.from("sf_version_release_state").select("version_id, skill_id, status, latest_eval_pass_rate, eval_current, approval_valid, approval_stale, publishable, eval_case_count").eq("workspace_id", ctx.workspace.id),
  ]);
  const skills = (skillsQ.data ?? []) as SkillRow[];
  const versions = (versionsQ.data ?? []) as Pick<VersionRow, "id" | "skill_id" | "version" | "status" | "source" | "updated_at">[];
  const states = (statesQ.data ?? []) as Pick<ReleaseStateRow, "version_id" | "status" | "latest_eval_pass_rate" | "eval_current" | "approval_valid" | "approval_stale" | "publishable" | "eval_case_count">[];
  const stateById = new Map(states.map((s) => [s.version_id, s]));
  const items: CatalogItem[] = skills.map((s) => {
    const vs = versions.filter((v) => v.skill_id === s.id);
    const working = vs.find((v) => ["draft", "in_review", "approved"].includes(v.status)) ?? null;
    const published = vs.find((v) => v.status === "published") ?? null;
    const st = working ? stateById.get(working.id) ?? null : published ? stateById.get(published.id) ?? null : null;
    return {
      id: s.id, slug: s.slug, name: s.name, purpose: s.purpose, status: s.status, updated_at: s.updated_at,
      source: (vs[0]?.source.kind ?? "authored") as "repo" | "authored",
      publishedVersion: published?.version ?? null, workingVersion: working?.version ?? null, workingStatus: (working?.status ?? null) as CatalogItem["workingStatus"],
      evalPassRate: st?.latest_eval_pass_rate == null ? null : Number(st.latest_eval_pass_rate), evalCurrent: st?.eval_current ?? null, cases: st?.eval_case_count ?? 0,
      approval: st?.approval_valid ? "valid" : st?.approval_stale ? "stale" : "none",
      stage: vs[0]?.source.kind === "repo" ? stageOfRepoSkill(vs[0].source.repo_skill) : null,
    };
  });
  const imported = new Set(versions.filter((v) => v.source.kind === "repo").map((v) => v.source.repo_skill));
  const importable = repoSkills.filter((s) => s.agent).map((s) => ({ id: s.id, name: s.name, domain: s.domain, description: s.description, imported: imported.has(s.id) }));
  const published = items.filter((i) => i.status === "published").length;
  const drafts = items.filter((i) => i.workingVersion != null).length;

  return (
    <>
      <PageHead eyebrow={`Skills · ${ctx.workspace.name}`} title="Skills you can" em="trust" after="."
        lead={items.length ? `${items.length} skill${items.length === 1 ? "" : "s"}: ${published} published, ${drafts} with a draft in progress.` : "No skills in this workspace yet."}
        caption="A skill is a versioned, tested capability with a declared input/output contract. Published versions are immutable and callable through the API."
        note={<><Link href="/repo/" className="link-flame">Repository catalog (40 skills, eval scorecard) →</Link> · <Link href="/upstream/" className="link-flame">Upstream library →</Link></>} />
      <div className="hero-actions mb-6">
        {can(ctx.role, "skill.create") ? (
          <>
            <Link href="/skills/new" className="btn btn-primary">New skill</Link>
            <ImportDrawer importable={importable} initialOpen={sp.import === "1"} />
          </>
        ) : <span className="caption">Your role ({ctx.role}) can run published skills. Authors create and import skills.</span>}
      </div>
      <SkillsCatalog items={items} canCreate={can(ctx.role, "skill.create")} initialStage={sp.stage ?? "all"}
        stageOpts={[...STAGES.map((x) => ({ key: x.id, label: `${x.n} ${x.name}` })), ...SHELVES.map((x) => ({ key: x.id, label: x.name })), { key: "unassigned", label: "Unassigned" }]} />
    </>
  );
}

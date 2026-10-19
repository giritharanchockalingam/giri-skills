import Link from "next/link";
import { loadFunnel } from "@/lib/db/skills";
import { skillCounts, countsSentence } from "@/lib/counts";
import { FunnelStrip } from "@/components/factory/Funnel";
import { GATE_ORDER, GATE_LABEL, GATE_HELP, type Gate } from "@/lib/factory/funnel";
import { requireWorkspace } from "@/lib/factory/db";
import { loadPipeline } from "@/lib/db/skills";
import { can } from "@/lib/factory/roles";
import { skills as repoSkills, STAGES, SHELVES, stageOfRepoSkill } from "@/lib/data";
import { PageHead } from "@/components/PageHead";
import { SkillsCatalog, type CatalogItem } from "@/components/factory/SkillsCatalog";
import { ImportDrawer } from "@/components/factory/ImportDrawer";

export const metadata = { title: "Skills · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function SkillsPage({ searchParams }: { searchParams: Promise<{ import?: string; stage?: string; gate?: string }> }) {
  const sp = await searchParams;
  const ctx = await requireWorkspace();
  const { skills, versions, states } = await loadPipeline(ctx.supabase, ctx.workspace.id);
  const [funnel, counts] = await Promise.all([loadFunnel(ctx.supabase, ctx.workspace.id), skillCounts(ctx.supabase, ctx.workspace.id)]);
  const gate = (GATE_ORDER as string[]).includes(sp.gate ?? "") ? (sp.gate as Gate) : null;
  const inGate = gate ? new Set(funnel.filter((f) => f.gate === gate).map((f) => f.slug)) : null;
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

  return (
    <>
      <PageHead eyebrow={`Skills · publish pipeline · ${ctx.workspace.name}`} title="Publish" em="pipeline" after="."
        lead={items.length ? countsSentence(counts) : "No skills in this workspace yet."}
        caption="For people who publish skills: versions, evaluation evidence, approvals. To use a skill, start from Home or the Library — nothing here needs to be published for that."
        note={<><Link href="/repo/" className="link-flame">Library ({repoSkills.length} skills, evaluation scorecard) →</Link> · <Link href="/upstream/" className="link-flame">Reference skills →</Link></>} />
      <div className="hero-actions mb-6">
        {can(ctx.role, "skill.create") ? (
          <>
            <Link href="/skills/new" className="btn btn-primary">New skill</Link>
            <ImportDrawer importable={importable} initialOpen={sp.import === "1"} />
          </>
        ) : <span className="caption">Your role ({ctx.role}) can run published skills. Authors create and import skills.</span>}
      </div>
      <FunnelStrip items={funnel} active={gate} />
      {gate && <p className="caption mb-4">Showing <b>{GATE_LABEL[gate]}</b>: {GATE_HELP[gate]} <Link className="link" href="/pipeline">Show all</Link></p>}
      <SkillsCatalog items={inGate ? items.filter((i) => inGate.has(i.slug)) : items} canCreate={can(ctx.role, "skill.create")} initialStage={sp.stage ?? "all"}
        stageOpts={[...STAGES.map((x) => ({ key: x.id, label: `${x.n} ${x.name}` })), ...SHELVES.map((x) => ({ key: x.id, label: x.name })), { key: "unassigned", label: "Unassigned" }]} />
    </>
  );
}

import { skillTitle } from "@/lib/names";
import { ActionForm } from "@/components/factory/ActionForm";
import { updateDraftsFromLibrary } from "@/app/actions";
import { skillDrift, contractKey } from "@/lib/factory/drift";
import { libraryContract, libraryCasesStale } from "@/lib/factory/libraryContract";
import { currentPin, currentSkillSha } from "@/lib/factory/pins";
import Link from "next/link";
import { loadFunnel } from "@/lib/db/skills";
import { skillCounts, countsBridge } from "@/lib/counts";
import { FunnelStrip, ClosestList } from "@/components/factory/Funnel";
import { GATE_ORDER, GATE_LABEL, GATE_HELP, closestToPublish, type Gate } from "@/lib/factory/funnel";
import { requireWorkspace } from "@/lib/factory/db";
import { loadPipeline, loadFrozenShas, loadCaseContracts } from "@/lib/db/skills";
import { can } from "@/lib/factory/roles";
import { skills as repoSkills, STAGES, SHELVES, stageOfRepoSkill } from "@/lib/data";
import { PageHead } from "@/components/PageHead";
import { SkillsCatalog, type CatalogItem } from "@/components/factory/SkillsCatalog";
import { ImportDrawer } from "@/components/factory/ImportDrawer";

export const metadata = { title: "Publish pipeline · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function SkillsPage({ searchParams }: { searchParams: Promise<{ import?: string; stage?: string; gate?: string }> }) {
  const sp = await searchParams;
  const ctx = await requireWorkspace();
  const { skills, versions, states } = await loadPipeline(ctx.supabase, ctx.workspace.id);
  const [funnel, counts] = await Promise.all([loadFunnel(ctx.supabase, ctx.workspace.id), skillCounts(ctx.supabase, ctx.workspace.id)]);
  const gate = (GATE_ORDER as string[]).includes(sp.gate ?? "") ? (sp.gate as Gate) : null;
  const gateBySlug = new Map(funnel.map((f) => [f.slug, f.gate]));
  const inGate = gate ? new Set(funnel.filter((f) => f.gate === gate).map((f) => f.slug)) : null;
  const stateById = new Map(states.map((s) => [s.version_id, s]));
  // the library's test cases as each repo draft holds them (a draft with old checks is offered the library update)
  const draftIds = versions.filter((v) => v.status === "draft" && v.source.kind === "repo").map((v) => v.id);
  const [frozen, draftCases] = await Promise.all([loadFrozenShas(ctx.supabase, { workspaceId: ctx.workspace.id }), loadCaseContracts(ctx.supabase, draftIds)]);
  const items: CatalogItem[] = skills.map((s) => {
    const vs = versions.filter((v) => v.skill_id === s.id);
    const working = vs.find((v) => ["draft", "in_review", "approved"].includes(v.status)) ?? null;
    const published = vs.find((v) => v.status === "published") ?? null;
    const st = working ? stateById.get(working.id) ?? null : published ? stateById.get(published.id) ?? null : null;
    return {
      id: s.id, slug: s.slug, name: skillTitle(s.name), purpose: s.purpose, status: s.status, updated_at: s.updated_at,
      source: (vs[0]?.source.kind ?? "authored") as "repo" | "authored",
      publishedVersion: published?.version ?? null, workingVersion: working?.version ?? null, workingStatus: (working?.status ?? null) as CatalogItem["workingStatus"],
      evalPassRate: st?.latest_eval_pass_rate == null ? null : Number(st.latest_eval_pass_rate), evalCurrent: st?.eval_current ?? null, cases: st?.eval_case_count ?? 0,
      approval: st?.approval_valid ? "valid" : st?.approval_stale ? "stale" : "none",
      stage: vs[0]?.source.kind === "repo" ? stageOfRepoSkill(vs[0].source.repo_skill) : null,
      gate: gateBySlug.get(s.slug),
      minPassRate: st?.min_eval_pass_rate == null ? null : Number(st.min_eval_pass_rate),
      drift: skillDrift(vs.map((v) => ({ ...v, contract: contractKey(v as never) })), currentPin, libraryContract(vs.find((v) => v.source.kind === "repo")?.source.repo_skill),
        working?.status === "draft" && working.source.kind === "repo" ? libraryCasesStale(working.source.repo_skill, draftCases.get(working.id) ?? []) : false, frozen, currentSkillSha),
    };
  });
  const blocked = items.filter((i) => i.drift === "blocked");
  const staleDrafts = items.filter((i) => i.drift === "library_updated" && i.workingStatus === "draft");
  const staleLive = items.filter((i) => i.drift === "library_updated" && i.workingStatus !== "draft" && i.publishedVersion != null);
  const canCreate = can(ctx.role, "version.create");
  const closest = closestToPublish(items.map((i) => ({ slug: i.slug, name: i.name, gate: i.gate, passRate: i.evalPassRate, minPassRate: i.minPassRate ?? null, cases: i.cases, version: i.workingVersion })));
  const imported = new Set(versions.filter((v) => v.source.kind === "repo").map((v) => v.source.repo_skill));
  const importable = repoSkills.filter((s) => s.agent).map((s) => ({ id: s.id, name: s.name, domain: s.domain, description: s.description, imported: imported.has(s.id) }));

  return (
    <>
      <PageHead eyebrow={`Build · publish pipeline · ${ctx.workspace.name}`} title="Publish" em="pipeline" after="."
        lead={items.length ? <>What stands between each skill and release: test it, get it approved, publish it. Only published versions run from Claude, Cursor or any app. This workspace: <b>{counts.published} published</b>, {counts.inProgress} in progress ({countsBridge(counts)}).</> : "No skills in this workspace yet. Import one from the library to start."} />
      <div className="hero-actions mb-6">
        {can(ctx.role, "skill.create") ? (
          <>
            <Link href="/skills/new" className="btn btn-primary">New skill</Link>
            <ImportDrawer importable={importable} initialOpen={sp.import === "1"} />
          </>
        ) : <span className="caption">Your role ({ctx.role}) can run published skills. Authors create and import skills.</span>}
      </div>
      <FunnelStrip items={funnel} active={gate} />
      {blocked.length > 0 && (
        <div className="notice notice-err mb-4" role="alert"><b>{blocked.length} published skill{blocked.length === 1 ? "" : "s"} can&apos;t run:</b> the library changed {blocked.length === 1 ? "its" : "their"} files after approval ({blocked.map((b, i) => <span key={b.slug}>{i ? ", " : ""}<Link className="link" href={`/skills/${b.slug}`}>{b.name}</Link></span>)}). Open each to create a version from the library.</div>)}
      {(staleDrafts.length > 0 || staleLive.length > 0) && (
        <div className="notice notice-hold mb-4" role="status">
          <b>The library has moved on for {staleDrafts.length + staleLive.length} skill{staleDrafts.length + staleLive.length === 1 ? "" : "s"}</b> (their instructions, inputs or steps changed).
          {staleDrafts.length > 0 && <> {staleDrafts.length} draft{staleDrafts.length === 1 ? "" : "s"} can be updated in place; test cases you added are kept.</>}
          {staleLive.length > 0 && <> {staleLive.length} published skill{staleLive.length === 1 ? " keeps" : "s keep"} running as approved; to release the newer version, open each one marked <b>Update from library</b> below.</>}
          {canCreate && staleDrafts.length > 0 && <div className="mt-2"><ActionForm action={updateDraftsFromLibrary} submit={`Update ${staleDrafts.length} draft${staleDrafts.length === 1 ? "" : "s"} from the library`} hidden={{ skill_ids: staleDrafts.map((d) => d.id).join(",") }} confirm={`Update ${staleDrafts.length} drafts to the library's current inputs, steps and test cases? Cases you added are kept.`} /></div>}
        </div>)}
      {!gate && <ClosestList rows={closest} />}
      {gate && <p className="caption mb-4">Showing <b>{GATE_LABEL[gate]}</b>: {GATE_HELP[gate]} <Link className="link" href="/pipeline">Show all</Link></p>}
      <SkillsCatalog items={inGate ? items.filter((i) => inGate.has(i.slug)) : items} canCreate={can(ctx.role, "skill.create")} initialStage={sp.stage ?? "all"}
        stageOpts={[...STAGES.map((x) => ({ key: x.id, label: `${x.n} ${x.name}` })), ...SHELVES.map((x) => ({ key: x.id, label: x.name })), { key: "unassigned", label: "Unassigned" }]} />
    </>
  );
}

import Link from "next/link";
import { skills, scoreFor, stageName } from "@/lib/data";
import { humanName, whatYouGet, displayDescription } from "@/lib/names";
import { libraryRows, librarySummary, publishedByLibrarySkill } from "@/lib/library";
import { requireWorkspace } from "@/lib/factory/db";
import { loadPipeline } from "@/lib/db/skills";
import { LibraryTable } from "@/components/LibraryTable";
import { skillCounts, countsBridge } from "@/lib/counts";
import { loadAccessData } from "@/lib/db/access";
import { allowedKeysFor } from "@/lib/access";
import { PageHead } from "@/components/PageHead";

export const metadata = { title: "Library · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function LibraryPage() {
  const ctx = await requireWorkspace();
  const [{ versions, skills: wsSkills }, access, counts] = await Promise.all([loadPipeline(ctx.supabase, ctx.workspace.id), loadAccessData(ctx.supabase, ctx.workspace.id), skillCounts(ctx.supabase, ctx.workspace.id)]);
  const restricted = access.enabled && ctx.role === "consumer";
  const mine = restricted ? allowedKeysFor(ctx.user.id, access.roles, access.assignments) : null;
  const slugOf = new Map(versions.filter((v) => v.source.kind === "repo" && v.source.repo_skill).map((v) => [v.source.repo_skill as string, wsSkills.find((w) => w.id === v.skill_id)?.slug ?? ""]));
  const published = publishedByLibrarySkill(versions);
  const rows = libraryRows(skills.map((s) => {
    const stage = Array.isArray(s.stage) ? s.stage[0] : s.stage;
    return {
      id: s.id, title: humanName(s.id.split("/")[1] ?? s.name), outcome: displayDescription((s as { card?: string }).card || whatYouGet(s.description)),
      stage: stageName(stage), domain: s.domain, verdict: scoreFor(s.id)?.verdict ?? null, published: published.get(s.id) ?? null,
      ...(mine ? { mine: mine.has(s.id) || mine.has(slugOf.get(s.id) ?? "") } : {}),
    };
  }));
  const sum = librarySummary(rows);
  const stages = [...new Set(rows.map((r) => r.stage))].sort();
  return (
    <>
      <PageHead
        eyebrow="Library"
        title={`${sum.total} skills,`}
        em={`${sum.approved} approved for use`}
        lead={<>Approved skills passed their tests and were signed off in {ctx.workspace.name}: they run the tested version, here or from Claude, Cursor or any app. Every other skill can be tried on its own example.{restricted ? " Your job roles decide which approved skills you can run; ask for access from any other." : ""} {sum.proven} of {sum.total} are proven by evaluation; the rest are being improved.</>}
        note={<><Link href="/" className="link-flame">← Describe the work instead</Link> · <Link href="/connect" className="link-flame">Use from your tools →</Link></>}
      />
      <LibraryTable rows={rows} stages={stages} workspace={ctx.workspace.name} />
      <p className="caption mt-4">{countsBridge(counts)}. Open a skill to run it and see its evidence. Detailed scores for skill owners are in <Link href="/evaluations" className="link">Evaluations</Link>.</p>
    </>
  );
}

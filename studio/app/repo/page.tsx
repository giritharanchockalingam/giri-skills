import Link from "next/link";
import { skills, scoreFor, stageName } from "@/lib/data";
import { humanName, whatYouGet, displayDescription } from "@/lib/names";
import { libraryRows, librarySummary } from "@/lib/library";
import { requireWorkspace } from "@/lib/factory/db";
import { loadPipeline } from "@/lib/db/skills";
import { LibraryTable } from "@/components/LibraryTable";
import { PageHead } from "@/components/PageHead";

export const metadata = { title: "Library · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function LibraryPage() {
  const ctx = await requireWorkspace();
  const { versions } = await loadPipeline(ctx.supabase, ctx.workspace.id);
  const published = new Map<string, number>();
  for (const v of versions) {
    if (v.status !== "published" || v.source.kind !== "repo") continue;
    const id = v.source.repo_skill;
    if (!id) continue;
    published.set(id, Math.max(published.get(id) ?? 0, v.version));
  }
  const rows = libraryRows(skills.map((s) => {
    const stage = Array.isArray(s.stage) ? s.stage[0] : s.stage;
    return {
      id: s.id, title: humanName(s.id.split("/")[1] ?? s.name), outcome: displayDescription((s as { card?: string }).card || whatYouGet(s.description)),
      stage: stageName(stage), domain: s.domain, verdict: scoreFor(s.id)?.verdict ?? null, published: published.get(s.id) ?? null,
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
        lead={<>Approved skills passed their tests and were signed off in {ctx.workspace.name}: they run the tested version, here or from Claude, Cursor or any app. Every other skill can be tried on its own example. {sum.proven} of {sum.total} are proven by evaluation; the rest are being improved.</>}
        note={<><Link href="/" className="link-flame">← Describe the work instead</Link> · <Link href="/connect" className="link-flame">Use from your tools →</Link></>}
      />
      <LibraryTable rows={rows} stages={stages} workspace={ctx.workspace.name} />
      <p className="caption mt-4">Open a skill to run it and see its evidence. Detailed scores for skill owners are in <Link href="/evaluations" className="link">Evaluations</Link>.</p>
    </>
  );
}

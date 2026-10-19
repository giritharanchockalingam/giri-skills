import { modelLabel } from "@/lib/modelLabel";
import { catalogRows, DOMAINS, meta } from "@/lib/data";
import { summarize } from "@/lib/verdict";
import { CatalogTable } from "@/components/CatalogTable";
import { PageHead } from "@/components/PageHead";
import { COL_TIPS } from "@/components/DomainTable";
import Link from "next/link";

export const metadata = { title: "Repository skills · Skills Factory" };

export default function RepoCatalogPage() {
  const rows = catalogRows();
  const s = summarize(rows.map((r) => r.verdict));
  const cases = rows.reduce((a, r) => a + r.cases, 0);
  return (
    <>
      <PageHead
        eyebrow="Library"
        title={`${s.total} skills,`}
        em="ready to run"
        lead={<>Every skill here runs in your browser on its own example, or on your files. Open one and press Run. {s.healthy} are rated healthy by their evaluations; {s.needsWork} need work.</>}
        caption={<>{cases} evaluation cases · {meta.runs} evaluation runs with {modelLabel(meta.model)} on {meta.date}</>}
        note={<><Link href="/" className="link-flame">← Describe a task instead</Link> · <Link href="/upstream/" className="link-flame">{meta.counts.upstream} reference skills from GitHub →</Link></>}
      />
      <CatalogTable rows={rows} domains={DOMAINS} />
      <dl className="kv metric-defs mt-4" aria-label="What the columns mean">
        <div><dt>Lift</dt><dd>{COL_TIPS.lift}: the share of expected items the answer got right with the skill loaded, minus without it, on the same cases. Positive = the skill helps.</dd></div>
        <div><dt>Trigger</dt><dd>{COL_TIPS.trigger}. Low means people asking for this job may get a different skill.</dd></div>
        <div><dt>Counts</dt><dd>{rows.length} skills in the library · {meta.counts.upstream} reference skills. Your workspace&apos;s own counts are on the Publish pipeline.</dd></div>
      </dl>
    </>
  );
}

import { catalogRows, DOMAINS, meta } from "@/lib/data";
import { summarize } from "@/lib/verdict";
import { CatalogTable } from "@/components/CatalogTable";
import { PageHead } from "@/components/PageHead";
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
        caption={<>{cases} eval cases · {meta.model} · {meta.runs} runs · {meta.date}</>}
        note={<><Link href="/" className="link-flame">← Describe a task instead</Link> · <Link href="/upstream/" className="link-flame">{meta.counts.upstream} reference skills from GitHub →</Link></>}
      />
      <CatalogTable rows={rows} domains={DOMAINS} />
    </>
  );
}

import { catalogRows, DOMAINS, meta } from "@/lib/data";
import { summarize } from "@/lib/verdict";
import { CatalogTable } from "@/components/CatalogTable";
import { PageHead } from "@/components/PageHead";
import Link from "next/link";

export default function CatalogPage() {
  const rows = catalogRows();
  const s = summarize(rows.map((r) => r.verdict));
  const cases = rows.reduce((a, r) => a + r.cases, 0);
  return (
    <>
      <PageHead
        eyebrow="giri-skills · skill catalog"
        title="Forty skills,"
        em="measured"
        lead={<>{s.total} skills across {DOMAINS.length} domains. {s.healthy} are healthy; {s.needsWork} need work.</>}
        caption={<>{cases} eval cases · {meta.model} · {meta.runs} runs · {meta.date}</>}
        note={<Link href="/upstream/" className="link-flame">Plus {meta.counts.upstream} vendored upstream skills →</Link>}
      />
      <CatalogTable rows={rows} domains={DOMAINS} />
    </>
  );
}

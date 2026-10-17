import { catalogRows, DOMAINS, meta } from "@/lib/data";
import { summarize } from "@/lib/verdict";
import { CatalogTable } from "@/components/CatalogTable";
import { PageHead } from "@/components/PageHead";

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
      />
      <CatalogTable rows={rows} domains={DOMAINS} />
    </>
  );
}

import { catalogRows, DOMAINS, VERDICTS, scorecard, meta } from "@/lib/data";
import { CatalogTable } from "@/components/CatalogTable";
import { PageHead } from "@/components/PageHead";

export default function CatalogPage() {
  const rows = catalogRows();
  const ok = scorecard.filter((r) => r.verdict === "OK").length;
  const cases = rows.reduce((a, r) => a + r.cases, 0);
  return (
    <>
      <PageHead
        eyebrow="giri-skills · skills factory"
        title="Forty skills,"
        em="measured"
        sub={<>{rows.length} skills across {DOMAINS.length} domains · {cases} eval cases · {ok} OK, {rows.length - ok} need work · {meta.model}, {meta.runs} runs</>}
      />
      <CatalogTable rows={rows} domains={DOMAINS} verdicts={VERDICTS} />
    </>
  );
}

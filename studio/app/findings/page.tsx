import { findings, skills, DOMAINS, VERDICTS, meta } from "@/lib/data";
import { FindingsList } from "@/components/FindingsList";
import { Collapsible } from "@/components/Collapsible";
import { PageHead, SectionHead } from "@/components/PageHead";

export const metadata = { title: "Findings · giri-skills" };

export default function FindingsPage() {
  const f = findings;
  return (
    <>
      <PageHead
        eyebrow="giri-skills · eval findings"
        title="The"
        em="fix"
        after=" list."
        sub={<>{f.proposals.length} ranked proposals from the {meta.date} run · {skills.length} skills · {skills.reduce((a, s) => a + s.cases.length, 0)} cases · {meta.runs} runs · {meta.model}</>}
      />

      <Collapsible title="Read before acting on any proposal" defaultOpen={false}>
        <div className="prose" dangerouslySetInnerHTML={{ __html: f.caveatsHtml }} />
      </Collapsible>

      <section className="section">
        <SectionHead eyebrow="By domain" title="Verdict" em="counts" />
        <div className="grid grid-safe gap-6 lg:grid-cols-[minmax(0,460px)_minmax(0,1fr)] lg:items-start">
          <div className="card tbl-wrap">
            <table className="tbl">
              <thead><tr><th>Domain</th><th className="num">OK</th><th className="num">DESC</th><th className="num">BODY</th><th className="num">BOTH</th></tr></thead>
              <tbody>
                {f.verdictCounts.map((r) => (
                  <tr key={r.domain} className={r.domain.startsWith("Total") ? "total" : ""}>
                    <td className={r.domain.startsWith("Total") ? "" : "cell-name"}>{r.domain}</td>
                    <td className="num">{r.OK}</td><td className="num">{r.DESC}</td><td className="num">{r.BODY}</td><td className="num">{r.BOTH}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card card-pad">
            <div className="eyebrow mb-3">Notes</div>
            <div className="prose text-[14px]" dangerouslySetInnerHTML={{ __html: f.verdictNotesHtml }} />
          </div>
        </div>
      </section>

      <section className="section">
        <SectionHead eyebrow={`${f.proposals.length} proposals · ranked by severity`} title="Ranked" em="proposals" />
        <FindingsList proposals={f.proposals} domains={DOMAINS} verdicts={VERDICTS} />
      </section>
    </>
  );
}

import { findings, DOMAINS, VERDICTS } from "@/lib/data";
import { FindingsList } from "@/components/FindingsList";
import { Collapsible } from "@/components/Collapsible";

export const metadata = { title: "Findings · giri-skills" };

export default function FindingsPage() {
  const f = findings;
  return (
    <>
      <h1 className="mb-1">Eval findings</h1>
      <p className="mb-3 max-w-[100ch] text-[12px] text-fg-2">{f.intro.replace(/\*\*|`/g, "")}</p>

      <Collapsible title="Caveats (read before acting on any proposal)" defaultOpen={false}>
        <div className="prose px-4 py-2" dangerouslySetInnerHTML={{ __html: f.caveatsHtml }} />
      </Collapsible>

      <h2>Verdict counts</h2>
      <div className="grid gap-4 lg:grid-cols-[auto_minmax(0,1fr)]">
        <div className="tbl-wrap w-fit">
          <table className="tbl">
            <thead><tr><th>domain</th><th className="num">OK</th><th className="num">DESC</th><th className="num">BODY</th><th className="num">BOTH</th></tr></thead>
            <tbody>
              {f.verdictCounts.map((r) => (
                <tr key={r.domain} className={r.domain.startsWith("Total") ? "font-semibold" : ""}>
                  <td>{r.domain}</td>
                  <td className="num">{r.OK}</td><td className="num">{r.DESC}</td><td className="num">{r.BODY}</td><td className="num">{r.BOTH}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="prose text-[12px] text-fg-2" dangerouslySetInnerHTML={{ __html: f.verdictNotesHtml }} />
      </div>

      <h2>Ranked proposals ({f.proposals.length})</h2>
      <FindingsList proposals={f.proposals} domains={DOMAINS} verdicts={VERDICTS} />
    </>
  );
}

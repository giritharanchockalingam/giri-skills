import { findings, scorecard, domainSummaries, meta } from "@/lib/data";
import { summarize, conclusionSentence } from "@/lib/verdict";
import { FindingsList } from "@/components/FindingsList";
import { Collapsible } from "@/components/Collapsible";
import { DomainTable } from "@/components/DomainTable";
import { PageHead, SectionHead } from "@/components/PageHead";
import { DOMAINS } from "@/lib/data";

export const metadata = { title: "Findings · giri-skills" };

export default function FindingsPage() {
  const f = findings;
  const s = summarize(scorecard.map((r) => r.verdict));
  const { rows, total } = domainSummaries();
  return (
    <>
      <PageHead
        eyebrow="giri-skills · fix list"
        title="The"
        em="fix"
        after=" list."
        lead={<>{conclusionSentence(s)} Below: {f.proposals.length} proposals, worst first, each with a paste-ready description.</>}
        caption={<>From the {meta.date} run · {meta.model} · {meta.runs} runs</>}
      />

      <Collapsible title="Read before acting on any proposal" caption="How the verdicts were produced and what they cannot tell you." defaultOpen={false}>
        <div className="prose" dangerouslySetInnerHTML={{ __html: f.caveatsHtml }} />
      </Collapsible>

      <section className="section">
        <SectionHead title="By" em="domain" caption="Where the proposals cluster." />
        <DomainTable rows={rows} total={total} showAverages={false} />
        <div className="card card-pad mt-5">
          <div className="h3 mb-2">Notes on the counts</div>
          <div className="prose" dangerouslySetInnerHTML={{ __html: f.verdictNotesHtml }} />
        </div>
      </section>

      <section className="section">
        <SectionHead title="Ranked" em="proposals" caption={`${f.proposals.length} skills with a proposed fix, most severe first.`} />
        <FindingsList proposals={f.proposals} domains={DOMAINS} />
      </section>
    </>
  );
}

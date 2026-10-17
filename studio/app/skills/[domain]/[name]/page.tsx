import Link from "next/link";
import { notFound } from "next/navigation";
import { skills, scoreFor, proposalFor, trigger, quality, fmt } from "@/lib/data";
import { verdictInfo } from "@/lib/verdict";
import { VerdictBadge, Lift, Trig } from "@/components/Badge";
import { CaseEvals } from "@/components/CaseEvals";
import { COL_TIPS } from "@/components/DomainTable";
import { SectionHead, StatStrip } from "@/components/PageHead";

export function generateStaticParams() {
  return skills.map((s) => ({ domain: s.domain, name: s.name }));
}
export const dynamicParams = false;

export async function generateMetadata({ params }: { params: Promise<{ domain: string; name: string }> }) {
  const { domain, name } = await params;
  return { title: `${name} · ${domain} · giri-skills` };
}

export default async function SkillPage({ params }: { params: Promise<{ domain: string; name: string }> }) {
  const { domain, name } = await params;
  const id = `${domain}/${name}`;
  const skill = skills.find((s) => s.id === id);
  if (!skill) notFound();
  const sc = scoreFor(id);
  const prop = proposalFor(id);
  const trig = trigger.filter((t) => t.skill === id);
  const qual = quality.filter((q) => q.skill === id);
  const fileCount = skill.files.references.length + skill.files.assets.length + skill.files.scripts.length;
  const info = verdictInfo(sc?.verdict);

  return (
    <>
      <div className="page-head">
        <nav className="caption" aria-label="Breadcrumb">
          <Link href="/" className="link">Skills</Link> <span aria-hidden="true">›</span> {domain}
        </nav>
        <div className="eyebrow mt-5">{skill.name}{skill.metadata.version && <> · v{skill.metadata.version}</>}</div>
        <h1 className="h1" style={{ marginBottom: 12 }}>{skill.name.replace(/-/g, " ")}</h1>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <VerdictBadge v={sc?.verdict} />
          <span className="caption">{info.explanation}</span>
        </div>
        <p className="lead mt-5">{skill.description}</p>
      </div>

      <div className="card card-pad">
        <StatStrip stats={[
          { label: "Trigger", value: <Trig n={sc?.triggerAcc} />, title: COL_TIPS.trigger },
          { label: "FP rate", value: fmt(sc?.fpRate), title: COL_TIPS.fp },
          { label: "Without", value: fmt(sc?.without), title: COL_TIPS.without },
          { label: "With", value: fmt(sc?.with), title: COL_TIPS.with },
          { label: "Lift", value: <Lift n={sc?.lift} />, title: COL_TIPS.lift },
          { label: "Eval cases", value: skill.cases.length },
        ]} />
      </div>

      <div className="two-col mt-7">
        <div className="card card-pad">
          <div className="eyebrow mb-4">SKILL.md</div>
          <div className="prose" dangerouslySetInnerHTML={{ __html: skill.bodyHtml }} />
        </div>
        <aside className="sidebar">
          {prop && (
            <Link href={`/findings/#${prop.number}`} className="card card-link card-pad block">
              <div className="eyebrow mb-2">Finding</div>
              <div className="serif text-[22px] leading-tight">Fix proposal #{prop.number} <span className="text-flame">→</span></div>
              <div className="caption tnum mt-2">{prop.stats}</div>
            </Link>
          )}
          <div className="card card-pad">
            <div className="h3 mb-3">Files <span className="muted font-normal">({fileCount})</span></div>
            {(["references", "assets", "scripts"] as const).map((k) => (
              <div key={k} className="mb-4 last:mb-0">
                <div className="caption capitalize">{k} ({skill.files[k].length})</div>
                {skill.files[k].length === 0 ? (
                  <div className="none text-[14px]">none</div>
                ) : (
                  <ul className="file-list mt-1">{skill.files[k].map((f) => <li key={f}>{k}/{f}</li>)}</ul>
                )}
              </div>
            ))}
          </div>
          {skill.license && <div className="caption px-1">License · {skill.license}</div>}
        </aside>
      </div>

      <section className="section">
        <SectionHead title="Eval" em="cases" caption={`${skill.cases.length} cases · ${trig.length} router picks · ${qual.length} judge verdicts`} />
        <CaseEvals cases={skill.cases} trigger={trig} quality={qual} skillName={skill.name} />
      </section>
    </>
  );
}

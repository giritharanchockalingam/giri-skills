import Link from "next/link";
import { notFound } from "next/navigation";
import { skills, scoreFor, proposalFor, trigger, quality, fmt } from "@/lib/data";
import { VerdictBadge, Lift, Trig } from "@/components/Badge";
import { CaseEvals } from "@/components/CaseEvals";
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

  return (
    <>
      <div className="page-head">
        <nav className="mono text-[12px] text-ink-3" aria-label="Breadcrumb">
          <Link href="/" className="hover:text-ink">Skills</Link> <span aria-hidden="true">›</span> {domain}
        </nav>
        <div className="eyebrow mt-5">{skill.name}{skill.metadata.version && <> · v{skill.metadata.version}</>}</div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <h1 className="h1" style={{ marginBottom: 0 }}>{skill.name.replace(/-/g, " ")}</h1>
          <VerdictBadge v={sc?.verdict} />
        </div>
        <p className="lead mt-5">{skill.description}</p>
      </div>

      <div className="card card-pad">
        <StatStrip stats={[
          { label: "trigger acc", value: <Trig n={sc?.triggerAcc} /> },
          { label: "FP rate", value: fmt(sc?.fpRate) },
          { label: "without", value: fmt(sc?.without) },
          { label: "with", value: fmt(sc?.with) },
          { label: "lift", value: <Lift n={sc?.lift} /> },
          { label: "eval cases", value: skill.cases.length },
        ]} />
      </div>

      <div className="two-col mt-7">
        <div className="card card-pad">
          <div className="eyebrow mb-4">SKILL.md</div>
          <div className="prose" dangerouslySetInnerHTML={{ __html: skill.bodyHtml }} />
        </div>
        <aside className="sidebar">
          <div className="card card-pad">
            <div className="eyebrow mb-3">Files · {fileCount}</div>
            {(["references", "assets", "scripts"] as const).map((k) => (
              <div key={k} className="mb-4 last:mb-0">
                <div className="h3 text-[13px]">{k} <span className="tag">({skill.files[k].length})</span></div>
                {skill.files[k].length === 0 ? (
                  <div className="none text-[14px]">none</div>
                ) : (
                  <ul className="file-list mt-1">{skill.files[k].map((f) => <li key={f}>{k}/{f}</li>)}</ul>
                )}
              </div>
            ))}
          </div>
          {prop && (
            <Link href={`/findings/#${prop.number}`} className="card card-link card-pad block">
              <div className="eyebrow mb-2">Finding</div>
              <div className="serif text-[22px] leading-tight">Fix proposal #{prop.number} <span className="text-flame">→</span></div>
              <div className="mono mt-2 text-[12px] text-ink-3">{prop.stats}</div>
            </Link>
          )}
          {skill.license && (
            <div className="tag px-1">license · {skill.license}</div>
          )}
        </aside>
      </div>

      <section className="section">
        <SectionHead eyebrow={`${skill.cases.length} cases · ${trig.length} router picks · ${qual.length} judge verdicts`} title="Eval" em="cases" />
        <CaseEvals cases={skill.cases} trigger={trig} quality={qual} skillName={skill.name} />
      </section>
    </>
  );
}

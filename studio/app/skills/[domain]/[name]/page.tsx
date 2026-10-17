import Link from "next/link";
import { notFound } from "next/navigation";
import { skills, scoreFor, proposalFor, trigger, quality, fmt } from "@/lib/data";
import { VerdictBadge, Lift } from "@/components/Badge";
import { CaseEvals } from "@/components/CaseEvals";

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

  const stat = (label: string, value: React.ReactNode) => (
    <div className="flex flex-col px-3 py-1.5">
      <span className="text-[10.5px] uppercase tracking-wide text-fg-3">{label}</span>
      <span className="mono text-[14px]">{value}</span>
    </div>
  );

  return (
    <>
      <div className="mb-1 text-[11.5px] text-fg-3"><Link href="/">Skills</Link> / {domain}</div>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mono">{skill.name}</h1>
        <span className="text-fg-2">{domain}</span>
        <VerdictBadge v={sc?.verdict} />
        {skill.metadata.version && <span className="mono text-[11px] text-fg-3">v{skill.metadata.version}</span>}
        {prop && (
          <Link href={`/findings/#${prop.number}`} className="ml-auto text-[12px]">finding #{prop.number} →</Link>
        )}
      </div>

      <div className="panel mt-3 flex w-fit divide-x divide-line">
        {stat("trigger acc", fmt(sc?.triggerAcc))}
        {stat("FP rate", fmt(sc?.fpRate))}
        {stat("without", fmt(sc?.without))}
        {stat("with", fmt(sc?.with))}
        {stat("lift", <Lift n={sc?.lift} />)}
      </div>

      <h2>Description</h2>
      <p className="max-w-[90ch] text-fg-2">{skill.description}</p>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div>
          <h2>SKILL.md</h2>
          <div className="panel px-4 py-2">
            <div className="prose" dangerouslySetInnerHTML={{ __html: skill.bodyHtml }} />
          </div>
        </div>
        <div>
          <h2>Files</h2>
          <div className="panel px-3 py-2 text-[12px]">
            {(["scripts", "references", "assets"] as const).map((k) => (
              <div key={k} className="mb-2">
                <div className="text-[10.5px] uppercase tracking-wide text-fg-3">{k} ({skill.files[k].length})</div>
                {skill.files[k].length === 0 ? (
                  <div className="muted">—</div>
                ) : (
                  <ul className="mono">{skill.files[k].map((f) => <li key={f}>{k}/{f}</li>)}</ul>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      <h2>Eval cases ({skill.cases.length})</h2>
      <CaseEvals cases={skill.cases} trigger={trig} quality={qual} skillName={skill.name} />
    </>
  );
}

"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import type { Proposal, Verdict } from "@/lib/data";
import { skillHref } from "@/lib/data";
import { VerdictBadge } from "./Badge";
import { Chips } from "./Chips";
import { CopyButton } from "./CopyButton";

export function FindingsList({ proposals, domains, verdicts }: { proposals: Proposal[]; domains: string[]; verdicts: Verdict[] }) {
  const [dom, setDom] = useState<Set<string>>(new Set());
  const [ver, setVer] = useState<Set<Verdict>>(new Set());
  const list = useMemo(
    () => proposals.filter((p) => (dom.size === 0 || dom.has(p.domain)) && (ver.size === 0 || ver.has(p.verdict))),
    [proposals, dom, ver],
  );
  return (
    <div className="flex flex-col gap-5">
      <div className="card toolbar">
        <Chips label="domain" options={domains} value={dom} onChange={setDom} />
        <Chips label="verdict" options={verdicts} value={ver} onChange={setVer} />
        <span className="toolbar-count">{list.length} of {proposals.length}</span>
      </div>
      <div className="flex flex-col gap-4">
        {list.map((p) => (
          <article key={p.number} id={String(p.number)} className="card card-pad scroll-mt-20">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <a href={`#${p.number}`} className="mono text-[13px] font-medium text-flame" aria-label={`anchor ${p.number}`}>#{p.number}</a>
              <Link href={skillHref(p.skill)} className="serif text-[22px] leading-tight hover:text-flame">{p.name}</Link>
              <span className="tag">{p.domain}</span>
              <VerdictBadge v={p.verdict} />
              <span className="mono text-[12px] text-ink-3">{p.stats}</span>
            </div>
            <p className="mt-3 max-w-[90ch] text-[15px] leading-relaxed text-ink-2">{p.evidence}</p>
            {p.descriptionProposal && (
              <div className="mt-5">
                <div className="eyebrow mb-2">Description (paste-ready)</div>
                <div className="codeblock">
                  <CopyButton text={p.descriptionProposal} />
                  {p.descriptionProposal}
                </div>
              </div>
            )}
            {p.bodyProposal && (
              <div className="mt-5">
                <div className="eyebrow mb-2">Body</div>
                <p className="max-w-[90ch] text-[15px] leading-relaxed text-ink-2">{p.bodyProposal}</p>
              </div>
            )}
          </article>
        ))}
        {list.length === 0 && <div className="card card-pad none">No proposals match.</div>}
      </div>
    </div>
  );
}

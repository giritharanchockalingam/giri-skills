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
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Chips label="domain" options={domains} value={dom} onChange={setDom} />
        <Chips label="verdict" options={verdicts} value={ver} onChange={setVer} />
        <span className="mono ml-auto text-[11.5px] text-fg-3">{list.length} of {proposals.length}</span>
      </div>
      <div className="flex flex-col gap-2">
        {list.map((p) => (
          <article key={p.number} id={String(p.number)} className="panel scroll-mt-14 px-3 py-2">
            <div className="flex flex-wrap items-center gap-2">
              <a href={`#${p.number}`} className="mono text-fg-3 hover:text-fg" aria-label={`anchor ${p.number}`}>#{p.number}</a>
              <Link href={skillHref(p.skill)} className="mono font-semibold">{p.name}</Link>
              <span className="text-[11.5px] text-fg-3">{p.domain}</span>
              <VerdictBadge v={p.verdict} />
              <span className="mono text-[11.5px] text-fg-2">({p.stats})</span>
            </div>
            <p className="mt-1 max-w-[110ch] text-fg-2">{p.evidence}</p>
            {p.descriptionProposal && (
              <div className="mt-2">
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-[10.5px] uppercase tracking-wide text-fg-3">description (paste-ready)</span>
                  <CopyButton text={p.descriptionProposal} />
                </div>
                <pre className="whitespace-pre-wrap"><code>{p.descriptionProposal}</code></pre>
              </div>
            )}
            {p.bodyProposal && (
              <div className="mt-2">
                <div className="text-[10.5px] uppercase tracking-wide text-fg-3">body</div>
                <p className="max-w-[110ch] text-fg-2">{p.bodyProposal}</p>
              </div>
            )}
          </article>
        ))}
        {list.length === 0 && <div className="muted">no proposals match</div>}
      </div>
    </div>
  );
}

"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import type { Proposal } from "@/lib/data";
import { skillHref } from "@/lib/data";
import { matchesVerdictFilter, type VerdictFilter } from "@/lib/verdict";
import { VerdictBadge } from "./Badge";
import { DomainFilter, VerdictFilterControl } from "./FilterBar";
import { CopyButton } from "./CopyButton";

export function FindingsList({ proposals, domains }: { proposals: Proposal[]; domains: string[] }) {
  const [dom, setDom] = useState<string>("all");
  const [ver, setVer] = useState<VerdictFilter>("all");
  const list = useMemo(
    () => proposals.filter((p) => (dom === "all" || p.domain === dom) && matchesVerdictFilter(ver, p.verdict)),
    [proposals, dom, ver],
  );
  return (
    <div className="flex flex-col gap-5">
      <div className="card toolbar">
        <DomainFilter id="f-domain" domains={domains} value={dom} onChange={setDom} />
        <VerdictFilterControl id="f-verdict" value={ver} onChange={setVer} />
        <span className="toolbar-count">{list.length} of {proposals.length} proposals</span>
      </div>
      <div className="flex flex-col gap-4">
        {list.map((p) => (
          <article key={p.number} id={String(p.number)} className="card card-pad scroll-mt-20">
            <div className="caption tnum">Proposal {p.number} of {proposals.length} · {p.domain}</div>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
              <Link href={skillHref(p.skill)} className="serif text-[22px] leading-tight hover:text-flame">{p.name}</Link>
              <VerdictBadge v={p.verdict} />
            </div>
            <div className="caption tnum mt-2">{p.stats}</div>
            <p className="mt-4 max-w-[80ch] text-[15px] leading-relaxed text-ink-2">{p.evidence}</p>
            {p.descriptionProposal && (
              <div className="mt-6">
                <div className="h3 mb-2">New description <span className="caption font-normal">— paste into SKILL.md frontmatter</span></div>
                <div className="codeblock">
                  <CopyButton text={p.descriptionProposal} />
                  {p.descriptionProposal}
                </div>
              </div>
            )}
            {p.bodyProposal && (
              <div className="mt-6">
                <div className="h3 mb-2">Instruction changes</div>
                <p className="max-w-[80ch] text-[15px] leading-relaxed text-ink-2">{p.bodyProposal}</p>
              </div>
            )}
          </article>
        ))}
        {list.length === 0 && <div className="card card-pad none">No proposals match.</div>}
      </div>
    </div>
  );
}

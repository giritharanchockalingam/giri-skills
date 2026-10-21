"use client";
import { GATE_ORDER, GATE_LABEL, type Gate } from "@/lib/factory/funnel";
import { matches } from "@/lib/search";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChoiceFilter } from "@/components/FilterBar";
import { SkillPill, GatePill } from "./Pills";
import { EmptyState } from "./EmptyState";
import type { SkillStatus } from "@/lib/factory/db";
import type { VersionStatus } from "@/lib/factory/release";

export interface CatalogItem {
  id: string; slug: string; name: string; purpose: string; status: SkillStatus; updated_at: string; source: "repo" | "authored"; gate?: Gate;
  publishedVersion: number | null; workingVersion: number | null; workingStatus: VersionStatus | null;
  evalPassRate: number | null; evalCurrent: boolean | null; cases: number; approval: "valid" | "stale" | "none";
  stage: string | null; minPassRate?: number | null; drift?: import("@/lib/factory/drift").Drift;
}

/** One status vocabulary: the funnel stage (retired skills are outside the funnel). */
const statusKey = (i: CatalogItem) => (i.status === "retired" ? "retired" : i.gate ?? i.status);
const STATUS_OPTS = [...GATE_ORDER.map((g) => ({ key: g, label: GATE_LABEL[g] })), { key: "retired", label: "Retired" }];
const Status = ({ i, small }: { i: CatalogItem; small?: boolean }) => (i.drift === "blocked"
  ? <span className={`pill pill-rust ${small ? "pill-sm" : ""}`} title="The library changed this skill's files after its live version was approved; it can't run until a new version is published.">Blocked: library changed</span>
  : i.status !== "retired" && i.gate ? <GatePill gate={i.gate} small={small} /> : <SkillPill status={i.status} small={small} />);
const SOURCE_OPTS = [{ key: "repo", label: "From repository" }, { key: "authored", label: "Authored" }] as const;

/** The next action for a skill at each funnel stage, and the tab where it happens. */
const NEXT: Partial<Record<Gate, { label: string; tab: string }>> = {
  draft: { label: "Add test cases", tab: "evaluations" }, needs_eval: { label: "Run evaluation", tab: "evaluations" },
  below_bar: { label: "Improve, re-evaluate", tab: "evaluations" }, needs_approval: { label: "Request review", tab: "release" }, ready: { label: "Publish", tab: "release" },
};
const evidence = (i: CatalogItem) => (i.evalPassRate == null ? (i.cases ? `${i.cases} case${i.cases === 1 ? "" : "s"}, not run` : "no cases") : (i.evalCurrent ? `${Math.round(i.evalPassRate * 100)}% pass · ${Math.round(i.evalPassRate * i.cases)} of ${i.cases} cases` : `${Math.round(i.evalPassRate * 100)}% pass (older case set)`));

export function SkillsCatalog({ items, canCreate, stageOpts, initialStage = "all" }: { items: CatalogItem[]; canCreate: boolean; stageOpts: readonly { key: string; label: string }[]; initialStage?: string }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<string>("all");
  const [source, setSource] = useState<string>("all");
  const [stage, setStage] = useState<string>(initialStage);
  const filtered = useMemo(() => {
    const n = q.trim().toLowerCase();
    return items.filter((i) => (stage === "all" || (i.stage ?? "unassigned") === stage) && (status === "all" || statusKey(i) === status) && (source === "all" || i.source === source) && matches(n, i.name, i.slug, i.purpose));
  }, [items, q, status, source, stage]);
  const go = (slug: string) => router.push(`/skills/${slug}`);

  if (items.length === 0) {
    return <div className="card"><EmptyState title="No skills in this workspace" detail={canCreate ? "Create one, or import repository skills — each comes with scripts, instructions and evaluation cases." : "An author needs to create or import a skill first."} action={canCreate ? "New skill" : undefined} href={canCreate ? "/skills/new" : undefined} /></div>;
  }
  return (
    <div className="flex flex-col gap-5">
      <div className="card toolbar">
        <input className="input" type="search" placeholder="Search name or purpose" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search skills" style={{ maxWidth: 320 }} />
        <label className="select-inline"><span className="chip-label">Stage</span>
          <select className="select" value={stage} onChange={(e) => setStage(e.target.value)} aria-label="AI development lifecycle stage" style={{ width: "auto", minHeight: 36 }}>
            <option value="all">All stages</option>
            {stageOpts.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
          </select>
        </label>
        <ChoiceFilter id="f-status" label="Status" options={STATUS_OPTS} value={status as "all"} onChange={setStatus} />
        <ChoiceFilter id="f-source" label="Source" options={SOURCE_OPTS} value={source as "all"} onChange={setSource} />
        <span className="toolbar-count">{filtered.length} of {items.length}</span>
      </div>
      <div className="card">
        <div className="tablewrap"><table className="tbl only-desktop">
          <thead><tr><th>Skill</th><th>Status</th><th>Live version</th><th title="The version being worked on; its stage is the Status">Working version</th><th title="Latest evaluation on the working version (or the published one): pass rate across its cases">Evidence</th><th title="Reviewer approval on the exact manifest of the working version">Approval</th><th>Next step</th><th style={{ width: "28%" }}>Purpose</th></tr></thead>
          <tbody>
            {filtered.map((i) => (
              <tr key={i.id} className="clickable" tabIndex={0} onClick={() => go(i.slug)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(i.slug); } }}>
                <td><Link href={`/skills/${i.slug}`} className="cell-name" onClick={(e) => e.stopPropagation()}>{i.name}</Link><div className="caption">{i.source === "repo" ? "from the library" : "authored here"}{i.slug !== i.name.toLowerCase().replace(/[^a-z0-9]+/g, "-") ? ` · ${i.slug}` : ""}</div></td>
                <td><Status i={i} /></td>
                <td className="muted">{i.publishedVersion != null ? `v${i.publishedVersion}` : "—"}</td>
                <td className="muted">{i.workingVersion != null ? `v${i.workingVersion}` : "—"}</td>
                <td className="ink-2">{evidence(i)}</td>
                <td>{i.approval === "valid" ? <span className="pass">valid</span> : i.approval === "stale" ? <span className="fail">stale</span> : <span className="muted">none</span>}</td>
                <td>{i.drift === "blocked" || i.drift === "library_updated" ? <Link href={`/skills/${i.slug}`} className="link" onClick={(e) => e.stopPropagation()}>Update from library</Link> : i.gate && NEXT[i.gate] ? <Link href={`/skills/${i.slug}/${NEXT[i.gate]!.tab}`} className="link" onClick={(e) => e.stopPropagation()}>{NEXT[i.gate]!.label}</Link> : <span className="muted">—</span>}</td>
                <td className="desc" title={i.purpose}><span>{i.purpose || <span className="none">No purpose written yet</span>}</span></td>
              </tr>
            ))}
            {filtered.length === 0 && <tr><td colSpan={8} className="none">No skills match.</td></tr>}
          </tbody>
        </table></div>
        <div className="row-list only-mobile">
          {filtered.map((i) => (
            <Link key={i.id} href={`/skills/${i.slug}`} className="row-card">
              <div className="row-card-top"><span className="row-card-name">{i.name}</span><Status i={i} small /></div>
              <div className="row-card-meta">
                <span>Live <b>{i.publishedVersion != null ? `v${i.publishedVersion}` : "—"}</b></span>
                {i.workingVersion != null && <span>Working <b>v{i.workingVersion}</b></span>}
                <span>Evidence <b>{evidence(i)}</b></span>
              </div>
              <div className="row-card-desc">{i.purpose || "No purpose written yet"}</div>
            </Link>
          ))}
          {filtered.length === 0 && <div className="row-card none">No skills match.</div>}
        </div>
      </div>
    </div>
  );
}

"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChoiceFilter } from "@/components/FilterBar";
import { SkillPill, VersionPill } from "./Pills";
import { EmptyState } from "./EmptyState";
import type { SkillStatus } from "@/lib/factory/db";
import type { VersionStatus } from "@/lib/factory/release";

export interface CatalogItem {
  id: string; slug: string; name: string; purpose: string; status: SkillStatus; updated_at: string; source: "repo" | "authored";
  publishedVersion: number | null; workingVersion: number | null; workingStatus: VersionStatus | null;
  evalPassRate: number | null; evalCurrent: boolean | null; cases: number; approval: "valid" | "stale" | "none";
  stage: string | null;
}

const STATUS_OPTS = [{ key: "published", label: "Published" }, { key: "draft", label: "Draft" }, { key: "retired", label: "Retired" }] as const;
const SOURCE_OPTS = [{ key: "repo", label: "From repository" }, { key: "authored", label: "Authored" }] as const;

const evidence = (i: CatalogItem) => (i.evalPassRate == null ? (i.cases ? `${i.cases} case${i.cases === 1 ? "" : "s"}, not run` : "no cases") : `${Math.round(i.evalPassRate * 100)}% pass${i.evalCurrent ? "" : " (outdated)"}`);

export function SkillsCatalog({ items, canCreate, stageOpts, initialStage = "all" }: { items: CatalogItem[]; canCreate: boolean; stageOpts: readonly { key: string; label: string }[]; initialStage?: string }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<string>("all");
  const [source, setSource] = useState<string>("all");
  const [stage, setStage] = useState<string>(initialStage);
  const filtered = useMemo(() => {
    const n = q.trim().toLowerCase();
    return items.filter((i) => (stage === "all" || (i.stage ?? "unassigned") === stage) && (status === "all" || i.status === status) && (source === "all" || i.source === source) && (!n || i.name.toLowerCase().includes(n) || i.slug.includes(n) || i.purpose.toLowerCase().includes(n)));
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
          <select className="select" value={stage} onChange={(e) => setStage(e.target.value)} aria-label="ADLC stage" style={{ width: "auto", minHeight: 36 }}>
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
          <thead><tr><th>Skill</th><th>Status</th><th>Published</th><th>In progress</th><th title="Latest evaluation on the working version (or the published one): pass rate across its cases">Evidence</th><th title="Reviewer approval on the exact manifest of the working version">Approval</th><th style={{ width: "34%" }}>Purpose</th></tr></thead>
          <tbody>
            {filtered.map((i) => (
              <tr key={i.id} className="clickable" tabIndex={0} onClick={() => go(i.slug)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(i.slug); } }}>
                <td><Link href={`/skills/${i.slug}`} className="cell-name" onClick={(e) => e.stopPropagation()}>{i.name}</Link><div className="caption">{i.slug} · {i.source === "repo" ? "repository" : "authored"}</div></td>
                <td><SkillPill status={i.status} /></td>
                <td className="muted">{i.publishedVersion != null ? `v${i.publishedVersion}` : "—"}</td>
                <td>{i.workingVersion != null && i.workingStatus ? <span className="flex items-center gap-2"><span className="muted">v{i.workingVersion}</span><VersionPill status={i.workingStatus} small /></span> : <span className="muted">—</span>}</td>
                <td className="ink-2">{evidence(i)}</td>
                <td>{i.approval === "valid" ? <span className="pass">valid</span> : i.approval === "stale" ? <span className="fail">stale</span> : <span className="muted">none</span>}</td>
                <td className="desc" title={i.purpose}><span>{i.purpose || <span className="none">No purpose written yet</span>}</span></td>
              </tr>
            ))}
            {filtered.length === 0 && <tr><td colSpan={7} className="none">No skills match.</td></tr>}
          </tbody>
        </table></div>
        <div className="row-list only-mobile">
          {filtered.map((i) => (
            <Link key={i.id} href={`/skills/${i.slug}`} className="row-card">
              <div className="row-card-top"><span className="row-card-name">{i.name}</span><SkillPill status={i.status} small /></div>
              <div className="row-card-meta">
                <span>Published <b>{i.publishedVersion != null ? `v${i.publishedVersion}` : "—"}</b></span>
                {i.workingVersion != null && i.workingStatus && <span>v{i.workingVersion} <VersionPill status={i.workingStatus} small /></span>}
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

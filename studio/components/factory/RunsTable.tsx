"use client";
import { LocalTime } from "@/components/LocalTime";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChoiceFilter } from "@/components/FilterBar";
import { RunPill } from "./Pills";
import {fmtMs, fmtUsd } from "@/lib/factory/format";
import type { RunStatus } from "@/lib/factory/db";

export interface RunListItem { id: string; status: RunStatus; source: string; created_at: string; duration_ms: number | null; provider: string | null; model: string | null; cost_usd: number | string | null; cost_is_estimate: boolean; error: string | null; skill: string; slug: string; version: number }

const STATUS_OPTS = [{ key: "succeeded", label: "Succeeded" }, { key: "failed", label: "Failed" }, { key: "needs_input", label: "Needs input" }, { key: "timeout", label: "Timed out" }, { key: "cancelled", label: "Cancelled" }, { key: "running", label: "Running" }] as const;
const SOURCE_OPTS = [{ key: "ui", label: "Test (UI)" }, { key: "api", label: "API" }, { key: "eval", label: "Evaluation" }] as const;

export function RunsTable({ items, caption, showSkill }: { items: RunListItem[]; caption: string; showSkill?: boolean }) {
  const router = useRouter();
  const [status, setStatus] = useState<string>("all");
  const [source, setSource] = useState<string>("all");
  const filtered = useMemo(() => items.filter((r) => (status === "all" || r.status === status) && (source === "all" || r.source === source)), [items, status, source]);
  const go = (id: string) => router.push(`/runs/${id}`);
  return (
    <div className="flex flex-col gap-5">
      <div className="card toolbar">
        <ChoiceFilter id="r-status" label="Status" options={STATUS_OPTS} value={status as "all"} onChange={setStatus} />
        <ChoiceFilter id="r-source" label="Source" options={SOURCE_OPTS} value={source as "all"} onChange={setSource} />
        <span className="toolbar-count">{filtered.length} of {items.length} · {caption}</span>
      </div>
      <div className="card">
        {items.length === 0 ? <div className="empty"><div className="none">No runs recorded yet.</div><p className="caption">Runs appear here when someone tests a skill, runs an evaluation, or calls the API.</p></div> : (
          <>
            <div className="tablewrap"><table className="tbl only-desktop">
              <thead><tr><th>When</th>{showSkill && <th>Skill</th>}<th>Status</th><th>Source</th><th>Provider · model</th><th className="num">Duration</th><th className="num" title="Estimated from provider-reported tokens × price table; — when no model call was made">Cost (est.)</th><th>Detail</th></tr></thead>
              <tbody>{filtered.map((r) => (
                <tr key={r.id} className="clickable" tabIndex={0} onClick={() => go(r.id)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(r.id); } }}>
                  <td><Link href={`/runs/${r.id}`} className="cell-name" onClick={(e) => e.stopPropagation()}><LocalTime iso={r.created_at} /></Link></td>
                  {showSkill && <td>{r.skill} <span className="muted">v{r.version}</span></td>}
                  <td><RunPill status={r.status} small /></td><td className="muted">{r.source}</td>
                  <td className="ink-2">{r.provider ?? "—"}{r.model ? ` · ${r.model}` : ""}</td>
                  <td className="num">{fmtMs(r.duration_ms)}</td><td className="num">{fmtUsd(r.cost_usd, r.cost_is_estimate)}</td>
                  <td className="desc" title={r.error ?? ""}><span>{r.error ?? ""}</span></td>
                </tr>
              ))}{filtered.length === 0 && <tr><td colSpan={8} className="none">No runs match.</td></tr>}</tbody>
            </table></div>
            <div className="row-list only-mobile">{filtered.map((r) => (
              <Link key={r.id} href={`/runs/${r.id}`} className="row-card">
                <div className="row-card-top"><span className="row-card-name">{showSkill ? `${r.skill} v${r.version}` : <LocalTime iso={r.created_at} />}</span><RunPill status={r.status} small /></div>
                <div className="row-card-meta">{showSkill && <span><LocalTime iso={r.created_at} /></span>}<span>{r.source}</span><span>{fmtMs(r.duration_ms)}</span>{r.cost_usd != null && <span>{fmtUsd(r.cost_usd, r.cost_is_estimate)}</span>}</div>
                {r.error && <div className="row-card-desc">{r.error}</div>}
              </Link>
            ))}{filtered.length === 0 && <div className="row-card none">No runs match.</div>}</div>
          </>
        )}
      </div>
    </div>
  );
}

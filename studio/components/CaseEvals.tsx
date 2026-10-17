"use client";
import { useState } from "react";
import type { EvalCase, TriggerRow, QualityRow } from "@/lib/data";
import { PassPill } from "./Badge";

export function CaseEvals({ cases, trigger, quality, skillName }: {
  cases: EvalCase[]; trigger: TriggerRow[]; quality: QualityRow[]; skillName: string;
}) {
  return (
    <div className="flex flex-col gap-6">
      {cases.map((c) => (
        <CaseBlock key={c.id} c={c} trigger={trigger.filter((t) => t.caseId === c.id)} quality={quality.filter((q) => q.caseId === c.id)} skillName={skillName} />
      ))}
      {cases.length === 0 && <div className="card card-pad none">No eval cases.</div>}
    </div>
  );
}

function CaseBlock({ c, trigger, quality, skillName }: { c: EvalCase; trigger: TriggerRow[]; quality: QualityRow[]; skillName: string }) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  const toggle = (k: number) => setOpen((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const runs = [...new Set(quality.map((q) => q.run))].sort((a, b) => a - b);
  const cell = (idx: number, mode: "without" | "with", run: number) => quality.find((q) => q.expectedIdx === idx && q.mode === mode && q.run === run);
  const count = (mode: "without" | "with") => {
    const rows = quality.filter((q) => q.mode === mode);
    return { pass: rows.filter((q) => q.pass).length, total: rows.length };
  };
  const wo = count("without"), wi = count("with");
  const routedOk = trigger.filter((t) => t.correct).length;

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">{c.id}</span>
        <span className="caption tnum">
          Routed {routedOk} of {trigger.length} · passed {wo.pass} of {wo.total} without, {wi.pass} of {wi.total} with
        </span>
      </div>

      <div className="card-pad">
        <div className="h3 mb-2">Prompt</div>
        <div className="prompt-block">{c.prompt}</div>
        <div className="h3 mt-6 mb-2">Expected in the answer</div>
        <ol className="flex flex-col gap-2 text-[15px] text-ink-2">
          {c.expected.map((e, i) => (
            <li key={i} className="flex gap-3"><span className="stat-num shrink-0 text-ink-3">{i + 1}.</span><span>{e}</span></li>
          ))}
        </ol>
      </div>

      <div className="grid grid-safe gap-7 border-t border-rule-soft px-6 py-5 max-md:px-[18px] lg:grid-cols-[minmax(240px,300px)_minmax(0,1fr)]">
        <div>
          <div className="h3 mb-1">Router picks</div>
          <div className="caption mb-2">Expected: {skillName}</div>
          <table className="mini">
            <thead><tr><th>Run</th><th>Picked</th><th>Result</th></tr></thead>
            <tbody>
              {[...trigger].sort((a, b) => a.run - b.run).map((t) => (
                <tr key={t.run}>
                  <td className="stat-num">{t.run}</td>
                  <td className={`${t.correct === 0 ? "fail" : ""}`} style={{ overflowWrap: "anywhere" }}>{t.selected}</td>
                  <td><PassPill pass={t.correct == null ? null : !!t.correct} /></td>
                </tr>
              ))}
              {trigger.length === 0 && <tr><td colSpan={3} className="none">No router rows.</td></tr>}
            </tbody>
          </table>
        </div>

        <div className="min-w-0">
          <div className="h3 mb-1">Judge verdicts</div>
          <div className="caption mb-2">Per expected item, without and with the skill loaded. Select an item for the judge's evidence.</div>

          {/* desktop: grid */}
          <table className="mini judge-table">
            <thead>
              <tr>
                <th>#</th><th style={{ width: "50%" }}>Expected</th>
                {runs.map((r) => <th key={`wo${r}`}>Without, run {r}</th>)}
                {runs.map((r) => <th key={`w${r}`}>With, run {r}</th>)}
              </tr>
            </thead>
            <tbody>
              {c.expected.map((e, i) => {
                const isOpen = open.has(i);
                return (
                  <RowPair key={i} isOpen={isOpen} onToggle={() => toggle(i)}
                    main={
                      <>
                        <td className="stat-num text-ink-3">{i + 1}</td>
                        <td className="ink-2">{e}</td>
                        {runs.map((r) => { const q = cell(i, "without", r); return <td key={`wo${r}`}><PassPill pass={q ? q.pass : null} /></td>; })}
                        {runs.map((r) => { const q = cell(i, "with", r); return <td key={`w${r}`}><PassPill pass={q ? q.pass : null} /></td>; })}
                      </>
                    }
                    detail={<td colSpan={2 + runs.length * 2} className="!pt-0"><Evidence i={i} runs={runs} cell={cell} /></td>}
                  />
                );
              })}
            </tbody>
          </table>

          {/* mobile: one stacked block per expected item */}
          <div className="judge-blocks">
            {c.expected.map((e, i) => {
              const isOpen = open.has(i);
              return (
                <div key={i} className="judge-block">
                  <div className="judge-block-text"><span className="stat-num text-ink-3">{i + 1}.</span> {e}</div>
                  <div className="judge-runs">
                    {runs.map((r) => { const q = cell(i, "without", r); return <span key={`wo${r}`}>Without r{r} <PassPill pass={q ? q.pass : null} /></span>; })}
                    {runs.map((r) => { const q = cell(i, "with", r); return <span key={`w${r}`}>With r{r} <PassPill pass={q ? q.pass : null} /></span>; })}
                  </div>
                  <button type="button" className="judge-toggle" onClick={() => toggle(i)} aria-expanded={isOpen}>{isOpen ? "Hide evidence" : "Show evidence"}</button>
                  {isOpen && <Evidence i={i} runs={runs} cell={cell} />}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

function Evidence({ i, runs, cell }: { i: number; runs: number[]; cell: (idx: number, mode: "without" | "with", run: number) => QualityRow | undefined }) {
  return (
    <div className="subpanel flex flex-col gap-3 text-[14px]">
      {(["without", "with"] as const).flatMap((mode) => runs.map((r) => {
        const q = cell(i, mode, r);
        return (
          <div key={`${mode}${r}`} className="flex flex-wrap gap-x-4 gap-y-1 sm:flex-nowrap">
            <span className="w-[110px] shrink-0 text-ink-3 capitalize">{mode}, run {r}</span>
            <span className="w-[56px] shrink-0"><PassPill pass={q ? q.pass : null} /></span>
            <span className="ink-2">{q?.evidence ?? ""}</span>
          </div>
        );
      }))}
    </div>
  );
}

function RowPair({ isOpen, onToggle, main, detail }: { isOpen: boolean; onToggle: () => void; main: React.ReactNode; detail: React.ReactNode }) {
  return (
    <>
      <tr className="cursor-pointer hover:bg-wash" onClick={onToggle} tabIndex={0} aria-expanded={isOpen}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onToggle(); } }}>
        {main}
      </tr>
      {isOpen && <tr>{detail}</tr>}
    </>
  );
}

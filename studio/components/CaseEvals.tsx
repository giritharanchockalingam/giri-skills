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
  const [open, setOpen] = useState<Set<string>>(new Set());
  const toggle = (k: string) => setOpen((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const runs = [...new Set(quality.map((q) => q.run))].sort((a, b) => a - b);
  const cell = (idx: number, mode: "without" | "with", run: number) => quality.find((q) => q.expectedIdx === idx && q.mode === mode && q.run === run);
  const withPass = quality.filter((q) => q.mode === "with").filter((q) => q.pass).length;
  const withTotal = quality.filter((q) => q.mode === "with").length;
  const woPass = quality.filter((q) => q.mode === "without").filter((q) => q.pass).length;
  const woTotal = quality.filter((q) => q.mode === "without").length;
  const routedOk = trigger.filter((t) => t.correct).length;

  return (
    <div className="card">
      <div className="card-head">
        <span className="mono text-[14px] font-medium">{c.id}</span>
        <span className="tag">
          routed {routedOk}/{trigger.length} · without {woPass}/{woTotal} · with {withPass}/{withTotal}
        </span>
      </div>

      <div className="card-pad">
        <div className="eyebrow mb-2">Prompt</div>
        <div className="prompt-block">{c.prompt}</div>
        <div className="eyebrow mt-5 mb-2">Expected</div>
        <ol className="flex flex-col gap-1.5 text-[14px] text-ink-2">
          {c.expected.map((e, i) => (
            <li key={i} className="flex gap-3"><span className="mono shrink-0 text-ink-3">[{i}]</span><span>{e}</span></li>
          ))}
        </ol>
      </div>

      <div className="grid grid-safe gap-6 border-t border-rule-soft px-6 py-5 lg:grid-cols-[minmax(260px,340px)_minmax(0,1fr)]">
        <div>
          <div className="eyebrow mb-2">Router picks · expected <span className="normal-case tracking-normal">{skillName}</span></div>
          <table className="mini">
            <thead><tr><th>Run</th><th>Selected</th><th>Correct</th></tr></thead>
            <tbody>
              {[...trigger].sort((a, b) => a.run - b.run).map((t) => (
                <tr key={t.run}>
                  <td className="mono">{t.run}</td>
                  <td className={`mono ${t.correct === 0 ? "fail" : ""}`}>{t.selected}</td>
                  <td><PassPill pass={t.correct == null ? null : !!t.correct} /></td>
                </tr>
              ))}
              {trigger.length === 0 && <tr><td colSpan={3} className="none">No router rows.</td></tr>}
            </tbody>
          </table>
        </div>

        <div className="min-w-0">
          <div className="eyebrow mb-2">Judge verdicts · click a row for evidence</div>
          <div className="tbl-wrap">
            <table className="mini">
              <thead>
                <tr>
                  <th>#</th><th style={{ width: "50%" }}>Expected</th>
                  {runs.map((r) => <th key={`wo${r}`}>Without r{r}</th>)}
                  {runs.map((r) => <th key={`w${r}`}>With r{r}</th>)}
                </tr>
              </thead>
              <tbody>
                {c.expected.map((e, i) => {
                  const k = String(i);
                  const isOpen = open.has(k);
                  return (
                    <RowPair key={i} isOpen={isOpen} onToggle={() => toggle(k)}
                      main={
                        <>
                          <td className="mono text-ink-3">{i}</td>
                          <td className="ink-2">{e}</td>
                          {runs.map((r) => { const q = cell(i, "without", r); return <td key={`wo${r}`}><PassPill pass={q ? q.pass : null} /></td>; })}
                          {runs.map((r) => { const q = cell(i, "with", r); return <td key={`w${r}`}><PassPill pass={q ? q.pass : null} /></td>; })}
                        </>
                      }
                      detail={
                        <td colSpan={2 + runs.length * 2} className="!pt-0">
                          <div className="subpanel flex flex-col gap-3 text-[13px]">
                            {(["without", "with"] as const).flatMap((mode) => runs.map((r) => {
                              const q = cell(i, mode, r);
                              return (
                                <div key={`${mode}${r}`} className="flex flex-wrap gap-x-4 gap-y-1 sm:flex-nowrap">
                                  <span className="mono w-[96px] shrink-0 text-ink-3">{mode} r{r}</span>
                                  <span className="w-[56px] shrink-0"><PassPill pass={q ? q.pass : null} /></span>
                                  <span className="ink-2">{q?.evidence ?? ""}</span>
                                </div>
                              );
                            }))}
                          </div>
                        </td>
                      }
                    />
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
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

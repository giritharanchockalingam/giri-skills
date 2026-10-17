"use client";
import { useState } from "react";
import type { EvalCase, TriggerRow, QualityRow } from "@/lib/data";

export function CaseEvals({ cases, trigger, quality, skillName }: {
  cases: EvalCase[]; trigger: TriggerRow[]; quality: QualityRow[]; skillName: string;
}) {
  return (
    <div className="flex flex-col gap-4">
      {cases.map((c) => (
        <CaseBlock key={c.id} c={c} trigger={trigger.filter((t) => t.caseId === c.id)} quality={quality.filter((q) => q.caseId === c.id)} skillName={skillName} />
      ))}
      {cases.length === 0 && <div className="muted">no eval cases</div>}
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

  return (
    <div className="panel">
      <div className="border-b border-line px-3 py-2">
        <div className="flex flex-wrap items-baseline gap-3">
          <span className="mono font-semibold">{c.id}</span>
          <span className="mono text-[11px] text-fg-3">
            without {woPass}/{woTotal} · with {withPass}/{withTotal}
          </span>
        </div>
        <p className="mt-1 max-w-[100ch] whitespace-pre-wrap text-fg-2">{c.prompt}</p>
        <ol className="mt-2 list-decimal pl-5 text-[12.5px]">
          {c.expected.map((e, i) => <li key={i} className="text-fg-2"><span className="mono text-fg-3">[{i}]</span> {e}</li>)}
        </ol>
      </div>

      <div className="grid gap-3 p-3 lg:grid-cols-[auto_minmax(0,1fr)]">
        <div>
          <div className="mb-1 text-[10.5px] uppercase tracking-wide text-fg-3">trigger</div>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th className="num">run</th><th>selected</th><th>correct</th></tr></thead>
              <tbody>
                {[...trigger].sort((a, b) => a.run - b.run).map((t) => (
                  <tr key={t.run}>
                    <td className="num">{t.run}</td>
                    <td className={`mono ${t.correct === 0 ? "fail" : ""}`}>{t.selected}</td>
                    <td className={t.correct ? "pass" : "fail"}>{t.correct ? "✓" : "✗"}</td>
                  </tr>
                ))}
                {trigger.length === 0 && <tr><td colSpan={3} className="muted">no trigger rows</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="mt-1 text-[11px] text-fg-3">expected: <span className="mono">{skillName}</span></div>
        </div>

        <div>
          <div className="mb-1 text-[10.5px] uppercase tracking-wide text-fg-3">quality (click a row for evidence)</div>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th className="num">#</th><th className="wrap">expected</th>
                  {runs.map((r) => <th key={`wo${r}`} className="num">without r{r}</th>)}
                  {runs.map((r) => <th key={`w${r}`} className="num">with r{r}</th>)}
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
                          <td className="num mono">{i}</td>
                          <td className="wrap min-w-[280px] text-fg-2">{e}</td>
                          {runs.map((r) => { const q = cell(i, "without", r); return <td key={`wo${r}`} className={`num ${q ? (q.pass ? "pass" : "fail") : "muted"}`}>{q ? (q.pass ? "PASS" : "FAIL") : "—"}</td>; })}
                          {runs.map((r) => { const q = cell(i, "with", r); return <td key={`w${r}`} className={`num ${q ? (q.pass ? "pass" : "fail") : "muted"}`}>{q ? (q.pass ? "PASS" : "FAIL") : "—"}</td>; })}
                        </>
                      }
                      detail={
                        <td colSpan={2 + runs.length * 2}>
                          <table className="w-full text-[12px]">
                            <tbody>
                              {(["without", "with"] as const).flatMap((mode) => runs.map((r) => {
                                const q = cell(i, mode, r);
                                return (
                                  <tr key={`${mode}${r}`}>
                                    <td className="mono w-[110px] py-0.5 pr-2 align-top text-fg-3">{mode} r{r}</td>
                                    <td className={`w-[48px] py-0.5 pr-2 align-top ${q ? (q.pass ? "pass" : "fail") : "muted"}`}>{q ? (q.pass ? "PASS" : "FAIL") : "—"}</td>
                                    <td className="py-0.5 whitespace-normal text-fg-2">{q?.evidence ?? ""}</td>
                                  </tr>
                                );
                              }))}
                            </tbody>
                          </table>
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
      <tr className="clickable" onClick={onToggle} tabIndex={0} aria-expanded={isOpen}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onToggle(); } }}>
        {main}
      </tr>
      {isOpen && <tr className="detail">{detail}</tr>}
    </>
  );
}

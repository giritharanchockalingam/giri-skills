"use client";
import { useState } from "react";
import { mdToHtml } from "@/lib/markdown.mjs";
import type { RunOutput } from "@/lib/factory/db";
import { Deliverables } from "@/components/Deliverables";

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
  const a = document.createElement("a"); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function RunOutputs({ outputs, logs, runJson }: { outputs: RunOutput[]; logs: string; runJson: unknown }) {
  const [viewing, setViewing] = useState<{ path: string; raw: boolean } | null>(null);
  const cur = viewing ? outputs.find((o) => o.path === viewing.path) : null;
  return (
    <>
      <Deliverables files={Object.fromEntries(outputs.map((o) => [o.path, o.content_text]))} />
      <div className="card card-pad">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
          <div className="h3">Output files <span className="muted font-normal">({outputs.length})</span></div>
          {runJson != null && <button type="button" className="btn btn-secondary btn-sm" onClick={() => download("run.json", JSON.stringify(runJson, null, 2))}>Download run.json</button>}
        </div>
        {outputs.length === 0 && <p className="none">No output files were written.</p>}
        <ul className="run-files">{outputs.map((o) => (
          <li key={o.path}><span className="min-w-0"><code className="run-file-name">{o.path}</code> <span className="caption">{o.bytes} B · sha256 {o.sha256.slice(0, 12)}…</span></span>
            <span className="run-file-actions">
              <button type="button" className="btn btn-secondary btn-sm" disabled={o.content_text == null} onClick={() => setViewing(viewing?.path === o.path ? null : { path: o.path, raw: !o.path.endsWith(".md") })}>{viewing?.path === o.path ? "Hide" : o.content_text == null ? "Too large" : "View"}</button>
              <button type="button" className="btn btn-secondary btn-sm" disabled={o.content_text == null} onClick={() => download(o.path.split("/").pop() || o.path, o.content_text ?? "")}>Download</button>
            </span></li>
        ))}</ul>
        {cur && viewing && (
          <div className="run-viewer">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2"><code className="run-file-name">{cur.path}</code>{cur.path.endsWith(".md") && <button type="button" className="btn btn-secondary btn-sm" onClick={() => setViewing({ ...viewing, raw: !viewing.raw })}>{viewing.raw ? "Rendered" : "Raw"}</button>}</div>
            {viewing.raw || !cur.path.endsWith(".md") ? <pre className="run-raw">{cur.content_text ?? "(empty)"}</pre> : <div className="prose run-prose" dangerouslySetInnerHTML={{ __html: mdToHtml(cur.content_text ?? "") }} />}
          </div>
        )}
      </div>
      <div className="card card-pad">
        <details className="disclosure"><summary>Logs <span className="muted font-normal">({logs ? `${logs.length.toLocaleString()} chars` : "empty"})</span></summary>
          <pre className="run-log mt-3">{logs || "(no log output)"}</pre></details>
      </div>
    </>
  );
}

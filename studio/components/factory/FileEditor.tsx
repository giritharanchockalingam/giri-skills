"use client";
/* Resource files of an authored draft (scripts/, assets/, references/) — the files its steps reference. */
import { useState } from "react";
import { ActionForm } from "./ActionForm";
import { saveFile, deleteFile } from "@/app/actions";
import type { FileRow } from "@/lib/factory/db";

export function FileEditor({ versionId, slug, files, editable }: { versionId: string; slug: string; files: Pick<FileRow, "path" | "content" | "sha256" | "updated_at">[]; editable: boolean }) {
  const [sel, setSel] = useState<string | null>(files[0]?.path ?? null);
  const [path, setPath] = useState(files[0]?.path ?? "scripts/");
  const [content, setContent] = useState(files[0]?.content ?? "");
  const pick = (f: (typeof files)[number] | null) => { setSel(f?.path ?? null); setPath(f?.path ?? "scripts/"); setContent(f?.content ?? ""); };
  return (
    <div className="form-grid" style={{ gridTemplateColumns: "minmax(0, 220px) minmax(0, 1fr)" }}>
      <div className="min-w-0">
        <div className="field-label mb-2">Files ({files.length})</div>
        <div className="list">
          {files.map((f) => <button key={f.path} type="button" className="list-row" style={{ cursor: "pointer", textAlign: "left", background: sel === f.path ? "var(--wash)" : undefined, borderRadius: 6, padding: "8px 8px" }} onClick={() => pick(f)}><span className="mono-sm">{f.path}</span></button>)}
          {files.length === 0 && <p className="none">No files yet.</p>}
        </div>
        {editable && <button type="button" className="btn btn-secondary btn-sm mt-3" onClick={() => pick(null)}>New file</button>}
      </div>
      <div className="min-w-0">
        <ActionForm action={saveFile} submit="Save file" hidden={{ version_id: versionId, slug }} disabled={!editable}>
          <div className="field"><label htmlFor="file-path">Path</label><input id="file-path" name="path" className="input" value={path} onChange={(e) => setPath(e.target.value)} disabled={!editable} pattern="(scripts|assets|references)/.+" /><span className="hint">scripts/… (run with <code>python3 scripts/x.py</code>), assets/… (templates), references/… (knowledge)</span></div>
          <div className="field mt-3"><label htmlFor="file-content">Content</label><textarea id="file-content" name="content" className="textarea mono" style={{ minHeight: 260 }} value={content} onChange={(e) => setContent(e.target.value)} disabled={!editable} spellCheck={false} /></div>
        </ActionForm>
        {editable && sel && (
          <ActionForm action={deleteFile} submit="Delete this file" submitClass="btn btn-danger btn-sm" confirm={`Delete ${sel}?`} hidden={{ version_id: versionId, slug, path: sel }} />
        )}
      </div>
    </div>
  );
}

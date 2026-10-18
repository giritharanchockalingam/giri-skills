"use client";
import { useMemo, useState } from "react";
import { Drawer } from "@/components/Drawer";
import { ActionForm } from "./ActionForm";
import { importFromRepo } from "@/app/actions";

export interface Importable { id: string; name: string; domain: string; description: string; imported: boolean }

/** "Import from repo": the 40 wired repository skills (SKILL.md metadata.agent + evals.json) become draft v1 versions. */
export function ImportDrawer({ importable, initialOpen = false }: { importable: Importable[]; initialOpen?: boolean }) {
  const [open, setOpen] = useState(initialOpen);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const list = useMemo(() => { const n = q.toLowerCase(); return importable.filter((s) => !n || s.id.includes(n) || s.description.toLowerCase().includes(n)); }, [importable, q]);
  const toggle = (id: string) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const remaining = importable.filter((s) => !s.imported);
  return (
    <>
      <button type="button" className="btn btn-secondary" onClick={() => setOpen(true)}>Import from repository ({remaining.length} available)</button>
      <Drawer open={open} onClose={() => setOpen(false)} titleId="import-title"
        title={<><div className="eyebrow">Import from repository</div><div className="drawer-title" id="import-title">Repository skills</div><p className="caption mt-2">Each becomes a draft v1 with its declared inputs, scripts, output checks, instructions and evaluation cases. Nothing is published by importing.</p></>}>
        <input className="input" type="search" placeholder="Filter by name or description" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter repository skills" />
        <ActionForm action={importFromRepo} submit={`Import ${sel.size || ""} selected`.replace("  ", " ")} render={() => null}>
          <div className="flex flex-wrap gap-2 mb-3">
            <button type="button" className="chip" onClick={() => setSel(new Set(remaining.map((s) => s.id)))}>Select all not yet imported</button>
            <button type="button" className="chip" onClick={() => setSel(new Set())}>Clear</button>
          </div>
          <div className="list">
            {list.map((s) => (
              <label key={s.id} className="list-row" style={{ cursor: s.imported ? "default" : "pointer" }}>
                <span className="flex items-start gap-3 min-w-0">
                  <input type="checkbox" name="repo_skill" value={s.id} disabled={s.imported} checked={sel.has(s.id)} onChange={() => toggle(s.id)} style={{ width: 18, height: 18, marginTop: 3, accentColor: "var(--flame)" }} />
                  <span className="min-w-0"><span className="name">{s.name}</span> <span className="caption">{s.domain}{s.imported ? " · already imported" : ""}</span>
                    <div className="caption" style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{s.description}</div></span>
                </span>
              </label>
            ))}
            {list.length === 0 && <p className="none">No repository skills match.</p>}
          </div>
        </ActionForm>
      </Drawer>
    </>
  );
}

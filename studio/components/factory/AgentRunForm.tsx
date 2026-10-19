"use client";
/* Inputs for an agent run: file inputs accept a file or pasted text; values are typed. "Fill demo inputs" loads the
 * shipped fictional fixtures (each file says so) so the agent can be tried end to end. */
import { useState } from "react";
import { useRouter } from "next/navigation";
import { humanInput, type AgentInputDecl, type StoredInput } from "@/lib/factory/agents";

const FILE_TYPES = new Set(["csv", "json", "md", "txt", "file"]);
type Demo = Record<string, { kind: "text"; content: string; ext: string; source?: string } | { kind: "value"; value: string }>;

export function AgentRunForm({ versionId, inputs, demo }: { versionId: string; inputs: AgentInputDecl[]; demo: Demo | null }) {
  const router = useRouter();
  const [vals, setVals] = useState<Record<string, { text: string; ext: string; source?: string }>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; details?: string[] } | null>(null);
  const set = (n: string, p: Partial<{ text: string; ext: string; source?: string }>) => setVals((v) => ({ ...v, [n]: { ...(v[n] ?? { text: "", ext: "" }), ...p } }));

  const [own, setOwn] = useState(!demo);
  const demoVals = () => {
    const next: typeof vals = {};
    for (const i of inputs) { const d = demo?.[i.name]; if (!d) continue; next[i.name] = d.kind === "text" ? { text: d.content, ext: d.ext, source: d.source } : { text: d.value, ext: "" }; }
    return next;
  };
  const fillDemo = () => { if (demo) { setVals(demoVals()); setOwn(true); } };
  const submit = (e: React.FormEvent) => { e.preventDefault(); start(vals); };
  const start = async (use: typeof vals) => {
    setBusy(true); setMsg(null);
    const body: Record<string, StoredInput> = {};
    for (const i of inputs) {
      const v = use[i.name]; if (!v || !v.text.trim()) continue;
      body[i.name] = FILE_TYPES.has(i.type) ? { kind: "text", content: v.text, ext: v.ext || (i.type === "file" ? "txt" : i.type) } : { kind: "value", value: v.text.trim() };
    }
    try {
      const res = await fetch("/api/agent-runs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ version_id: versionId, inputs: body }) });
      const j = await res.json();
      if (!res.ok) { setMsg({ text: j.error?.message ?? `HTTP ${res.status}`, details: j.error?.details }); return; }
      router.push(`/agent-runs/${j.run_id}?go=1`);
    } catch (err) { setMsg({ text: (err as Error).message }); } finally { setBusy(false); }
  };
  const status = <div role="status" aria-live="polite">{msg && <div className="notice notice-err">{msg.text}{msg.details && <ul style={{ margin: "6px 0 0 18px", listStyle: "disc" }}>{msg.details.map((d) => <li key={d}>{d}</li>)}</ul>}</div>}</div>;

  return (
    <form onSubmit={submit} className="stack" style={{ maxWidth: 860 }}>
      {demo && (
        <div className="card card-pad">
          <div className="h3" style={{ margin: 0 }}>See it work first</div>
          <p className="caption" style={{ margin: "6px 0 12px" }}>Runs every step on a sample case (a fictional company, labelled as such in each file) and shows you the outcome. One click, nothing to prepare.</p>
          <div className="action-row" style={{ marginTop: 0 }}>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => start(demoVals())} aria-busy={busy}>{busy ? "Starting…" : "Run it on the example"}</button>
            {!own && <button type="button" className="btn btn-secondary" onClick={() => setOwn(true)}>Use my own inputs</button>}
            {own && <button type="button" className="btn btn-secondary btn-sm" onClick={fillDemo}>Load the example into the form</button>}
          </div>
          {!own && status}
        </div>
      )}
      {own && inputs.map((i) => {
        const v = vals[i.name] ?? { text: "", ext: "" };
        return (
          <div key={i.name} className="card card-pad field">
            <label htmlFor={`in-${i.name}`}>{humanInput(i)}{i.required && <span className="agent-req">*</span>} <span className="caption"><code>{i.name}</code> · {i.type}</span></label>
            {v.source && <span className="hint">loaded from {v.source}</span>}
            {FILE_TYPES.has(i.type) ? (
              <>
                <input type="file" aria-label={`Upload ${i.name}`} onChange={async (e) => { const f = e.target.files?.[0]; if (f) set(i.name, { text: await f.text(), ext: f.name.split(".").pop()?.toLowerCase() ?? "", source: f.name }); }} />
                <textarea id={`in-${i.name}`} className="textarea mono" style={{ minHeight: 90 }} placeholder="…or paste the content" value={v.text} onChange={(e) => set(i.name, { text: e.target.value, source: undefined })} />
              </>
            ) : <input id={`in-${i.name}`} className="input" value={v.text} onChange={(e) => set(i.name, { text: e.target.value })} />}
          </div>
        );
      })}
      {own && (<>
        <div className="action-row" style={{ marginTop: 0 }}>
          <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "Starting…" : "Run with these inputs"}</button>
        </div>
        {status}
      </>)}
    </form>
  );
}

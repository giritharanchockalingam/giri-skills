"use client";
/* Inputs for an agent run: file inputs accept a file or pasted text; values are typed. "Fill demo inputs" loads the
 * shipped fictional fixtures (each file says so) so the agent can be tried end to end. */
import { useState } from "react";
import { useRouter } from "next/navigation";
import type { AgentInputDecl, StoredInput } from "@/lib/factory/agents";

const FILE_TYPES = new Set(["csv", "json", "md", "txt", "file"]);
type Demo = Record<string, { kind: "text"; content: string; ext: string; source?: string } | { kind: "value"; value: string }>;

export function AgentRunForm({ versionId, inputs, demo }: { versionId: string; inputs: AgentInputDecl[]; demo: Demo | null }) {
  const router = useRouter();
  const [vals, setVals] = useState<Record<string, { text: string; ext: string; source?: string }>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; details?: string[] } | null>(null);
  const set = (n: string, p: Partial<{ text: string; ext: string; source?: string }>) => setVals((v) => ({ ...v, [n]: { ...(v[n] ?? { text: "", ext: "" }), ...p } }));

  const fillDemo = () => {
    if (!demo) return;
    const next: typeof vals = {};
    for (const i of inputs) { const d = demo[i.name]; if (!d) continue; next[i.name] = d.kind === "text" ? { text: d.content, ext: d.ext, source: d.source } : { text: d.value, ext: "" }; }
    setVals(next);
  };
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setMsg(null);
    const body: Record<string, StoredInput> = {};
    for (const i of inputs) {
      const v = vals[i.name]; if (!v || !v.text.trim()) continue;
      body[i.name] = FILE_TYPES.has(i.type) ? { kind: "text", content: v.text, ext: v.ext || (i.type === "file" ? "txt" : i.type) } : { kind: "value", value: v.text.trim() };
    }
    try {
      const res = await fetch("/api/agent-runs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ version_id: versionId, inputs: body }) });
      const j = await res.json();
      if (!res.ok) { setMsg({ text: j.error?.message ?? `HTTP ${res.status}`, details: j.error?.details }); return; }
      router.push(`/agent-runs/${j.run_id}?go=1`);
    } catch (err) { setMsg({ text: (err as Error).message }); } finally { setBusy(false); }
  };

  return (
    <form onSubmit={submit} className="stack" style={{ maxWidth: 860 }}>
      {demo && <div className="notice notice-info">Try it with the shipped demo inputs (fictional, labelled in each file). <button type="button" className="btn btn-sm btn-secondary" onClick={fillDemo} style={{ marginLeft: 8 }}>Fill demo inputs</button></div>}
      {inputs.map((i) => {
        const v = vals[i.name] ?? { text: "", ext: "" };
        return (
          <div key={i.name} className="card card-pad field">
            <label htmlFor={`in-${i.name}`}><code>{i.name}</code>{i.required && <span className="agent-req">*</span>} <span className="caption">{i.type}</span></label>
            {i.from && <span className="hint">{i.from}</span>}
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
      <div className="action-row" style={{ marginTop: 0 }}>
        <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "Starting…" : "Run agent"}</button>
      </div>
      <div role="status" aria-live="polite">{msg && <div className="notice notice-err">{msg.text}{msg.details && <ul style={{ margin: "6px 0 0 18px", listStyle: "disc" }}>{msg.details.map((d) => <li key={d}>{d}</li>)}</ul>}</div>}</div>
    </form>
  );
}

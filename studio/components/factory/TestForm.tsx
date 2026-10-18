"use client";
/* "Test skill": a form generated from the manifest's inputs, executed server-side through POST /api/runs and
 * persisted as a run. Validation happens on the server before execution; results are read from the stored run. */
import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Manifest, InputSpec } from "@/lib/factory/manifest";
import { TEXT_INPUT_TYPES } from "@/lib/factory/manifest";

type Draft = { text: string; fileName: string | null; value: string; checked: boolean; assume: string };
const isText = (t: string) => (TEXT_INPUT_TYPES as readonly string[]).includes(t);
const extOf = (name: string | null, type: string) => name?.match(/\.([A-Za-z0-9]+)$/)?.[1]?.toLowerCase() ?? (type === "file" ? "txt" : type);

export function TestForm({ versionId, manifest, runtimeOk, runtimeReason, keyPresent, slug }: {
  versionId: string; manifest: Manifest; runtimeOk: boolean; runtimeReason: string | null; keyPresent: boolean; slug: string;
}) {
  const router = useRouter();
  const inputs = [...manifest.inputs].sort((a, b) => Number(b.required) - Number(a.required));
  const [drafts, setDrafts] = useState<Record<string, Draft>>(() => Object.fromEntries(inputs.map((i) => [i.name, { text: "", fileName: null, value: "", checked: false, assume: "" }])));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string; details?: unknown } | null>(null);
  const set = (n: string, p: Partial<Draft>) => setDrafts((d) => ({ ...d, [n]: { ...d[n], ...p } }));
  const needsLlm = manifest.run.some((s) => s.kind === "llm");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setMsg(null);
    const body: { version_id: string; inputs: Record<string, unknown>; assumptions: Record<string, string> } = { version_id: versionId, inputs: {}, assumptions: {} };
    for (const i of inputs) {
      const d = drafts[i.name];
      if (isText(i.type)) { if (d.text.trim()) body.inputs[i.name] = { kind: "text", content: d.text, ext: extOf(d.fileName, i.type) }; }
      else if (i.type === "flag") { if (d.checked) body.inputs[i.name] = true; }
      else if (i.type === "path" || i.type === "dir") { /* path: pinned under the run folder by the server; dir: not supported over HTTP */ }
      else if (d.value.trim()) body.inputs[i.name] = d.value;
      if (!(i.name in body.inputs) && d.assume.trim()) body.assumptions[i.name] = d.assume;
    }
    try {
      const res = await fetch("/api/runs", { method: "POST", headers: { "content-type": "application/json", "idempotency-key": crypto.randomUUID() }, body: JSON.stringify(body) });
      const j = await res.json();
      if (!res.ok) { setMsg({ ok: false, text: j.error?.message ?? `HTTP ${res.status}`, details: j.error?.details }); return; }
      router.push(`/runs/${j.run_id}?from=test&slug=${encodeURIComponent(slug)}`);
    } catch (err) { setMsg({ ok: false, text: (err as Error).message }); }
    finally { setBusy(false); }
  };

  return (
    <form onSubmit={submit} className="stack">
      {!runtimeOk && <div className="notice notice-err">Runtime unavailable: {runtimeReason}</div>}
      {needsLlm && !keyPresent && <div className="notice notice-hold">No key on the server for provider “{manifest.model_config.provider}”: scripts run, llm steps are skipped and recorded — checks on their outputs will fail.</div>}
      {manifest.run.length === 0 && <div className="notice notice-hold">No steps yet — add one under Instructions.</div>}
      <div className="run-inputs">
        {inputs.map((i) => <Field key={i.name} i={i} d={drafts[i.name]} set={(p) => set(i.name, p)} />)}
        {inputs.length === 0 && <p className="none">This skill declares no inputs.</p>}
      </div>
      <div className="action-row" style={{ marginTop: 4 }}>
        <button type="submit" className="btn btn-primary" disabled={busy || !runtimeOk || manifest.run.length === 0}>{busy ? "Running…" : "Test skill"}</button>
        <span className="caption">Server run · {manifest.limits.timeout_s}s limit · recorded under Activity</span>
      </div>
      <div role="status" aria-live="polite">
        {msg && <div className={`notice ${msg.ok ? "notice-ok" : "notice-err"}`}>{msg.text}{Array.isArray(msg.details) && <ul style={{ margin: "6px 0 0 18px", listStyle: "disc" }}>{(msg.details as { path: string; message: string }[]).map((p, k) => <li key={k}><code>{p.path}</code> {p.message}</li>)}</ul>}</div>}
      </div>
    </form>
  );
}

function Field({ i, d, set }: { i: InputSpec; d: Draft; set: (p: Partial<Draft>) => void }) {
  const id = `in-${i.name}`;
  return (
    <div className="run-input">
      <div className="run-input-head">
        <label htmlFor={id}><code>{i.name}</code>{i.required && <span className="agent-req" title="required"> *</span>}<span className="muted"> · {i.type}</span></label>
        {i.from && <div className="caption">{i.from}</div>}
      </div>
      {isText(i.type) && (
        <>
          <div className="run-file-row"><input id={id} type="file" className="run-file" onChange={(e) => { const f = e.target.files?.[0]; if (f) f.text().then((t) => set({ text: t, fileName: f.name })); }} /></div>
          {d.fileName && <div className="caption">loaded <code>{d.fileName}</code></div>}
          <textarea className="run-textarea" value={d.text} placeholder={`…or paste the ${i.type} content here`} spellCheck={false} onChange={(e) => set({ text: e.target.value })} />
        </>
      )}
      {i.type === "flag" && <label className="run-check"><input id={id} type="checkbox" checked={d.checked} onChange={(e) => set({ checked: e.target.checked })} /> set <code>{i.flag || `--${i.name.replace(/_/g, "-")}`}</code></label>}
      {i.type === "path" && <div className="caption" id={id}>Output folder — created inside this run&apos;s folder as <code>{`{out}/${i.name}`}</code>; its files are collected as outputs.</div>}
      {i.type === "dir" && <div className="run-note" id={id}>A directory input cannot be supplied over HTTP. Use an evaluation case with a fixture folder, or run in the browser.</div>}
      {!isText(i.type) && !["flag", "path", "dir"].includes(i.type) && (
        <input id={id} className="input run-input-text" value={d.value} placeholder={i.default != null ? `default: ${i.default}` : ""} onChange={(e) => set({ value: e.target.value })} />
      )}
      {i.type !== "path" && (
        <details className="run-assume"><summary className="caption">Assume instead{d.assume.trim() && <> — <code>{i.name}={d.assume}</code></>}</summary>
          <label className="run-field mt-2"><span className="caption">Used only when the input above is empty; recorded as an assumption and labelled <code>[ASSUMED]</code> in the outputs.</span>
            <input className="input run-input-text" value={d.assume} placeholder="value to assume" onChange={(e) => set({ assume: e.target.value })} /></label>
        </details>
      )}
    </div>
  );
}

"use client";
/* Draft manifest editor. Structured fields for the parts people read (purpose, instructions, model, limits, release
 * criteria, tools) and JSON for the parts that are schemas (inputs, outputs, run steps). Validation runs live with
 * the same validateManifest() the server uses; Save submits the assembled JSON to saveManifest(). */
import { useMemo, useState } from "react";
import { validateManifest, MODELS, MAX_TIMEOUT_S, type Manifest, type Problem } from "@/lib/factory/manifest";
import { ActionForm } from "./ActionForm";
import { saveManifest } from "@/app/actions";

const pretty = (v: unknown) => JSON.stringify(v, null, 2);

export function ManifestEditor({ versionId, slug, manifest, editable }: { versionId: string; slug: string; manifest: Manifest; editable: boolean }) {
  const [m, setM] = useState<Manifest>(manifest);
  const [inputsJson, setInputsJson] = useState(pretty(manifest.inputs));
  const [outputsJson, setOutputsJson] = useState(pretty(manifest.outputs));
  const [runJson, setRunJson] = useState(pretty(manifest.run));
  const [changeNote, setChangeNote] = useState("");

  const assembled = useMemo<{ json: string; problems: Problem[] }>(() => {
    const parse = (label: string, s: string): { v: unknown; p: Problem | null } => { try { return { v: JSON.parse(s), p: null }; } catch (e) { return { v: [], p: { path: label, message: `invalid JSON: ${(e as Error).message}` } }; } };
    const i = parse("inputs", inputsJson), o = parse("outputs", outputsJson), r = parse("run", runJson);
    const candidate = { ...m, inputs: i.v, outputs: o.v, run: r.v };
    const problems = [i.p, o.p, r.p].filter((x): x is Problem => !!x);
    const v = validateManifest(candidate);
    if (!v.ok) problems.push(...v.problems);
    return { json: JSON.stringify(v.ok ? v.manifest : candidate), problems };
  }, [m, inputsJson, outputsJson, runJson]);

  const set = <K extends keyof Manifest>(k: K, v: Manifest[K]) => setM((x) => ({ ...x, [k]: v }));
  const dis = !editable;

  return (
    <ActionForm action={saveManifest} submit="Save draft" disabled={dis || assembled.problems.length > 0} hidden={{ version_id: versionId, slug, manifest: assembled.json, change_note: changeNote }}>
      {!editable && <div className="notice notice-hold mb-4">This version is not a draft — its manifest is immutable. Approved versions can be reopened for editing from the Release view (the approval then goes stale on the first edit); published ones need a new draft.</div>}
      <div className="form-grid form-grid-2">
        <div className="field span-2"><label htmlFor="purpose">Purpose</label><textarea id="purpose" className="textarea" style={{ minHeight: 72 }} value={m.purpose} onChange={(e) => set("purpose", e.target.value)} disabled={dis} /></div>
        <div className="field"><label htmlFor="intended_users">Intended users</label><textarea id="intended_users" className="textarea" style={{ minHeight: 64 }} value={m.intended_users} onChange={(e) => set("intended_users", e.target.value)} disabled={dis} /></div>
        <div className="field"><label htmlFor="usage_guidance">When to use it</label><textarea id="usage_guidance" className="textarea" style={{ minHeight: 64 }} value={m.usage_guidance} onChange={(e) => set("usage_guidance", e.target.value)} disabled={dis} /></div>

        <div className="field span-2">
          <label htmlFor="instructions">Instructions (Markdown)</label>
          <span className="hint">What the skill does and how. For llm steps this is context the model follows; for authored skills it becomes the SKILL.md body the runner reads.</span>
          <textarea id="instructions" className="textarea mono" style={{ minHeight: 200 }} value={m.instructions_md} onChange={(e) => set("instructions_md", e.target.value)} disabled={dis} spellCheck={false} />
        </div>

        <div className="field">
          <label htmlFor="inputs">Inputs (JSON)</label>
          <span className="hint">{`[{"name","type","required","from","default","flag","schema"}] — type: csv json md txt file sql dir path string args flag`}</span>
          <textarea id="inputs" className="textarea mono" style={{ minHeight: 180 }} value={inputsJson} onChange={(e) => setInputsJson(e.target.value)} disabled={dis} spellCheck={false} />
        </div>
        <div className="field">
          <label htmlFor="outputs">Outputs (JSON)</label>
          <span className="hint">{`[{"path":"{out}/file","checks":["exists","json","sections:[\\"A\\"]"],"schema":null}]`}</span>
          <textarea id="outputs" className="textarea mono" style={{ minHeight: 180 }} value={outputsJson} onChange={(e) => setOutputsJson(e.target.value)} disabled={dis} spellCheck={false} />
        </div>
        <div className="field span-2">
          <label htmlFor="run">Steps (JSON)</label>
          <span className="hint">{`script: {"step","kind":"script","cmd":"python3 scripts/x.py {input} --out {out}/f","stdout"?,"expect_exit"?}  ·  llm: {"step","kind":"llm","template":"assets/t.md","context":["{out}/f"],"out":"{out}/memo.md"}  ·  {name} substitutes an input, [ … {opt} … ] drops when optional input is absent`}</span>
          <textarea id="run" className="textarea mono" style={{ minHeight: 140 }} value={runJson} onChange={(e) => setRunJson(e.target.value)} disabled={dis} spellCheck={false} />
        </div>

        <fieldset className="field"><legend className="field-label">Allowed tools</legend>
          {(["script", "llm"] as const).map((t) => <label key={t} className="check-row"><input type="checkbox" checked={m.allowed_tools.includes(t)} disabled={dis} onChange={(e) => set("allowed_tools", e.target.checked ? [...new Set([...m.allowed_tools, t])] : m.allowed_tools.filter((x) => x !== t))} /> {t}</label>)}
          <span className="hint">A step whose kind is not allowed fails validation. The workspace policy can restrict further.</span>
        </fieldset>
        <div className="field"><label htmlFor="connections">Connections</label><input id="connections" className="input" value={m.connections.join(", ")} disabled={dis} onChange={(e) => set("connections", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} /><span className="hint">Names of workspace connections (Administration → Connections). “anthropic” is added automatically for the Anthropic provider.</span></div>

        <div className="field"><label htmlFor="provider">Model provider</label>
          <select id="provider" className="select" value={m.model_config.provider} disabled={dis} onChange={(e) => set("model_config", { ...m.model_config, provider: e.target.value as Manifest["model_config"]["provider"] })}><option value="none">none — deterministic only</option><option value="anthropic">anthropic</option></select></div>
        <div className="field"><label htmlFor="model">Model</label>
          <select id="model" className="select" value={m.model_config.model} disabled={dis || m.model_config.provider === "none"} onChange={(e) => set("model_config", { ...m.model_config, model: e.target.value })}>{MODELS.map((x) => <option key={x}>{x}</option>)}{!MODELS.includes(m.model_config.model as (typeof MODELS)[number]) && <option>{m.model_config.model}</option>}</select></div>
        <div className="field"><label htmlFor="temp">Temperature</label><input id="temp" className="input" type="number" min={0} max={1} step={0.1} value={m.model_config.temperature} disabled={dis} onChange={(e) => set("model_config", { ...m.model_config, temperature: Number(e.target.value) })} /></div>
        <div className="field"><label htmlFor="mtok">Max tokens per call</label><input id="mtok" className="input" type="number" min={1} max={32000} value={m.model_config.max_tokens} disabled={dis} onChange={(e) => set("model_config", { ...m.model_config, max_tokens: Number(e.target.value) })} /></div>

        <div className="field"><label htmlFor="timeout">Deadline (seconds, ≤ {MAX_TIMEOUT_S})</label><input id="timeout" className="input" type="number" min={1} max={MAX_TIMEOUT_S} value={m.limits.timeout_s} disabled={dis} onChange={(e) => set("limits", { ...m.limits, timeout_s: Number(e.target.value) })} /></div>
        <div className="field"><label htmlFor="retries">Retries (0–2, provider errors only)</label><input id="retries" className="input" type="number" min={0} max={2} value={m.limits.max_retries} disabled={dis} onChange={(e) => set("limits", { ...m.limits, max_retries: Number(e.target.value) })} /></div>
        <div className="field"><label htmlFor="ltok">Token limit per run</label><input id="ltok" className="input" type="number" min={1} value={m.limits.max_tokens} disabled={dis} onChange={(e) => set("limits", { ...m.limits, max_tokens: Number(e.target.value) })} /></div>
        <div className="field"><label htmlFor="cost">Cost limit (USD, optional)</label><input id="cost" className="input" type="number" min={0} step={0.01} value={m.limits.max_cost_usd ?? ""} disabled={dis} onChange={(e) => set("limits", { ...m.limits, max_cost_usd: e.target.value === "" ? null : Number(e.target.value) })} /></div>

        <div className="field"><label htmlFor="minrate">Minimum evaluation pass rate (0 = no gate)</label><input id="minrate" className="input" type="number" min={0} max={1} step={0.05} value={m.release_criteria.min_eval_pass_rate} disabled={dis} onChange={(e) => set("release_criteria", { ...m.release_criteria, min_eval_pass_rate: Number(e.target.value) })} /></div>
        <div className="field"><span className="field-label">Approval</span><label className="check-row"><input type="checkbox" checked={m.release_criteria.require_approval} disabled={dis} onChange={(e) => set("release_criteria", { ...m.release_criteria, require_approval: e.target.checked })} /> A reviewer must approve this exact version before it can be published</label></div>

        <div className="field span-2"><label htmlFor="note">Change note</label><input id="note" className="input" value={changeNote} maxLength={500} disabled={dis} onChange={(e) => setChangeNote(e.target.value)} placeholder="What changed and why" /></div>
      </div>

      <div className="mt-4" role="status" aria-live="polite">
        {assembled.problems.length > 0 ? (
          <div className="notice notice-err"><b>{assembled.problems.length} problem{assembled.problems.length === 1 ? "" : "s"} — fix before saving:</b>
            <ul style={{ margin: "6px 0 0 18px", listStyle: "disc" }}>{assembled.problems.map((p, k) => <li key={k}><code>{p.path || "manifest"}</code> {p.message}</li>)}</ul></div>
        ) : <div className="notice notice-ok">Manifest is valid.</div>}
      </div>
    </ActionForm>
  );
}

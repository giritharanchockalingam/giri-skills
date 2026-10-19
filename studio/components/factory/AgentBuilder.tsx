"use client";
/* Agent Builder: compose an agent from catalog skills. Adding a skill auto-wires its inputs (earlier outputs first,
 * else a new agent input); every wire can be changed. Validation runs live with the same rules as the runner. */
import { useMemo, useState } from "react";
import {
  type AgentSpec, type AgentStepSpec, type CatalogSkill, type SkillStep, type AgentInputDecl,
  validateAgentSpec, autoWire, newStepId, unusedInputs, isSkill, isCompose, isApproval, fileOutputs, parseRef,
} from "@/lib/factory/agents";
import { ActionForm } from "./ActionForm";
import { saveAgentDraft } from "@/app/agentActions";

interface Stage { id: string; n?: number; name: string }

export function AgentBuilder({ initial, versionId, catalog, stages, editable }: {
  initial: AgentSpec; versionId: string; catalog: CatalogSkill[]; stages: Stage[]; editable: boolean;
}) {
  const cat = useMemo(() => new Map(catalog.map((c) => [c.id, c])), [catalog]);
  const [spec, setSpec] = useState<AgentSpec>(() => ({ ...initial, inputs: initial.inputs ?? [], steps: initial.steps ?? [], outputs: initial.outputs ?? [] }));
  const [picker, setPicker] = useState(false);
  const problems = useMemo(() => validateAgentSpec(spec, cat), [spec, cat]);
  const dirty = JSON.stringify(spec) !== JSON.stringify(initial);

  const update = (fn: (s: AgentSpec) => AgentSpec) => setSpec((s) => fn(structuredClone(s)));
  const setStep = (i: number, step: AgentStepSpec) => update((s) => { s.steps[i] = step; return s; });

  const addSkill = (c: CatalogSkill) => update((s) => {
    const w = autoWire(s, c, cat);
    s.inputs.push(...w.newAgentInputs);
    s.steps.push({ id: newStepId(s, c.id), skill: c.id, inputs: w.inputs });
    return s;
  });
  const addApproval = () => update((s) => { s.steps.push({ id: newStepId(s, "approval"), approval: { role: "Reviewer", note: "" } }); return s; });
  const addCompose = () => update((s) => { s.steps.push({ id: newStepId(s, "compose"), compose: { out: "facts.csv", format: "kv-csv", rows: {} } }); return s; });
  const move = (i: number, d: -1 | 1) => update((s) => { const j = i + d; if (j < 0 || j >= s.steps.length) return s; [s.steps[i], s.steps[j]] = [s.steps[j], s.steps[i]]; return s; });
  // removing a step also drops the deliverables that pointed at its files (they could no longer be produced or unticked)
  const remove = (i: number) => update((s) => {
    const [gone] = s.steps.splice(i, 1);
    if (gone) s.outputs = (s.outputs ?? []).filter((ref) => { const r = parseRef(ref); return !(r?.kind === "step" && r.step === gone.id); });
    return s;
  });
  const dropUnused = () => update((s) => { const u = new Set(unusedInputs(s)); s.inputs = s.inputs.filter((i) => !u.has(i.name)); return s; });

  // every file an earlier step writes, for wiring dropdowns and the outputs list
  const filesBefore = (idx: number) => spec.steps.slice(0, idx).flatMap((s) =>
    isSkill(s) ? fileOutputs(cat.get(s.skill) ?? { outputs: [] } as unknown as CatalogSkill).map((f) => ({ step: s.id, file: f }))
    : isCompose(s) ? [{ step: s.id, file: s.compose.out }] : []);
  const allFiles = filesBefore(spec.steps.length);

  return (
    <div className="agent-builder">
      <div className="ab-main stack">
        <div className="card card-pad stack-sm">
          <div className="field"><label htmlFor="ab-desc">What this agent does</label>
            <textarea id="ab-desc" className="textarea" style={{ minHeight: 64 }} value={spec.description} disabled={!editable}
              onChange={(e) => update((s) => { s.description = e.target.value; return s; })} /></div>
          <label className="check-row"><input type="checkbox" checked={spec.config?.provider === "none"} disabled={!editable}
            onChange={(e) => update((s) => { s.config = { ...(s.config ?? {}), provider: e.target.checked ? "none" : "auto" }; return s; })} />
            Scripts only (skip model-written steps). Otherwise each skill uses the workspace&apos;s configured model.</label>
        </div>

        <ol className="ab-steps">
          {spec.steps.map((step, i) => (
            <li key={step.id + i} className="card ab-step">
              <div className="ab-step-head">
                <span className="ab-n">{i + 1}</span>
                <input className="input ab-id" aria-label="Step id" value={step.id} disabled={!editable}
                  onChange={(e) => setStep(i, { ...step, id: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") })} />
                <span className={`pill pill-sm ${isSkill(step) ? "pill-deep" : isApproval(step) ? "pill-hold" : "pill-none"}`}>{isSkill(step) ? "skill" : isApproval(step) ? "approval" : "compose"}</span>
                {isSkill(step) && <span className="caption">{step.skill}{cat.get(step.skill)?.stage ? ` · ${stages.find((s) => s.id === cat.get(step.skill)!.stage)?.name ?? ""}` : ""}</span>}
                {editable && <span className="ab-tools">
                  <button type="button" className="btn btn-sm" onClick={() => move(i, -1)} disabled={i === 0} aria-label="Move up">↑</button>
                  <button type="button" className="btn btn-sm" onClick={() => move(i, 1)} disabled={i === spec.steps.length - 1} aria-label="Move down">↓</button>
                  <button type="button" className="btn btn-sm btn-danger" onClick={() => remove(i)} aria-label={`Remove ${step.id}`}>Remove</button>
                </span>}
              </div>
              {isSkill(step) && <SkillWiring step={step} skill={cat.get(step.skill)} spec={spec} files={filesBefore(i)} editable={editable}
                onChange={(st, newInputs) => update((s) => { s.steps[i] = st; for (const n of newInputs) if (!s.inputs.some((x) => x.name === n.name)) s.inputs.push(n); return s; })} />}
              {isApproval(step) && (
                <div className="ab-grid">
                  <div className="field"><label>Approver role</label><input className="input" value={step.approval.role} disabled={!editable} onChange={(e) => setStep(i, { ...step, approval: { ...step.approval, role: e.target.value } })} /></div>
                  <div className="field"><label>What they check</label><input className="input" value={step.approval.note ?? ""} disabled={!editable} onChange={(e) => setStep(i, { ...step, approval: { ...step.approval, note: e.target.value } })} /></div>
                </div>
              )}
              {isCompose(step) && <ComposeEditor step={step} files={filesBefore(i)} spec={spec} editable={editable} onChange={(st) => setStep(i, st)} />}
            </li>
          ))}
          {spec.steps.length === 0 && <li className="card card-pad none">No steps yet. Add a skill to start; its inputs wire themselves.</li>}
        </ol>

        {editable && (
          <div className="action-row" style={{ marginTop: 0 }}>
            <button type="button" className="btn btn-primary" onClick={() => setPicker(true)}>Add skill</button>
            <button type="button" className="btn btn-secondary" onClick={addApproval}>Add approval</button>
            <button type="button" className="btn btn-secondary" onClick={addCompose}>Add compose</button>
          </div>
        )}
        {picker && <SkillPicker catalog={catalog} stages={stages} onPick={(c) => { addSkill(c); setPicker(false); }} onClose={() => setPicker(false)} />}
      </div>

      <aside className="ab-side stack">
        <div className="card card-pad">
          <div className="h3">{problems.length ? <span className="fail">{problems.length} problem{problems.length === 1 ? "" : "s"}</span> : <span className="pass">Runnable</span>}</div>
          {problems.length > 0 && <ul className="ab-problems">{problems.slice(0, 12).map((p) => <li key={p}>{p}</li>)}</ul>}
          {editable && (
            <ActionForm action={saveAgentDraft} submit={dirty ? "Save draft" : "Saved"} disabled={!dirty} hidden={{ version_id: versionId, spec: JSON.stringify(spec) }} />
          )}
        </div>
        <div className="card card-pad">
          <div className="h3">Agent inputs <span className="muted font-normal">({spec.inputs.length})</span></div>
          <p className="caption">Asked for when the agent runs. Created by wiring; edit the wording or make one optional.</p>
          <ul className="ab-inputs">
            {spec.inputs.map((inp, k) => (
              <li key={inp.name}>
                <code>{inp.name}</code> <span className="caption">{inp.type}</span>
                <label className="check-row" style={{ display: "inline-flex", marginLeft: 8 }}><input type="checkbox" checked={inp.required} disabled={!editable}
                  onChange={(e) => update((s) => { s.inputs[k] = { ...s.inputs[k], required: e.target.checked }; return s; })} /> required</label>
                {inp.from && <div className="caption">{inp.from}</div>}
              </li>
            ))}
          </ul>
          {editable && unusedInputs(spec).length > 0 && <button type="button" className="btn btn-sm" onClick={dropUnused}>Remove {unusedInputs(spec).length} unused</button>}
        </div>
        <div className="card card-pad">
          <div className="h3">Deliverables</div>
          <p className="caption">Files shown first on the run page.</p>
          <ul className="ab-inputs">
            {allFiles.map((f) => { const ref = `$steps.${f.step}:${f.file}`; const on = spec.outputs?.includes(ref) ?? false; return (
              <li key={ref}><label className="check-row"><input type="checkbox" checked={on} disabled={!editable}
                onChange={(e) => update((s) => { s.outputs = e.target.checked ? [...(s.outputs ?? []), ref] : (s.outputs ?? []).filter((x) => x !== ref); return s; })} />
                <span className="mono-sm">{f.step}/{f.file}</span></label></li>); })}
            {allFiles.length === 0 && <li className="none">Add steps first.</li>}
          </ul>
        </div>
      </aside>
    </div>
  );
}

const TYPE_EXT: Record<string, string[]> = { csv: ["csv"], json: ["json"], md: ["md"], txt: ["txt", "md"], file: ["csv", "json", "jsonl", "md", "txt"] };

function SkillWiring({ step, skill, spec, files, editable, onChange }: {
  step: SkillStep; skill: CatalogSkill | undefined; spec: AgentSpec; files: { step: string; file: string }[]; editable: boolean;
  onChange: (s: SkillStep, newInputs: AgentInputDecl[]) => void;
}) {
  if (!skill) return <p className="notice notice-err">Skill {step.skill} is not in this deployment.</p>;
  return (
    <div className="tablewrap"><table className="mini ab-wiring"><thead><tr><th>Input</th><th>Comes from</th></tr></thead><tbody>
      {skill.inputs.map((inp) => {
        const cur = step.inputs[inp.name] ?? "";
        const p = cur ? parseRef(cur) : null;
        const ok = TYPE_EXT[inp.type];
        const fileOpts = files.filter((f) => !ok || ok.includes(f.file.split(".").pop() ?? ""));
        const literal = p?.kind === "literal";
        const set = (v: string, add: AgentInputDecl[] = []) => {
          const inputs = { ...step.inputs };
          if (v === "") delete inputs[inp.name]; else inputs[inp.name] = v;
          onChange({ ...step, inputs }, add);
        };
        return (
          <tr key={inp.name}>
            <td><code>{inp.name}</code>{inp.required && <span className="agent-req">*</span>} <span className="caption">{inp.type}</span><div className="caption ab-from">{inp.from}</div></td>
            <td>
              <select className="select" disabled={!editable} value={literal ? "__literal" : cur}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v === "__literal") set(" ");
                  else if (v === "__new") set(`$in.${inp.name}`, [{ name: inp.name, type: inp.type, required: inp.required, from: inp.from }]);
                  else set(v);
                }}>
                <option value="">{inp.required ? "— choose a source —" : "— not used —"}</option>
                <optgroup label="Agent input">
                  {spec.inputs.map((a) => <option key={a.name} value={`$in.${a.name}`}>asked at run time: {a.name}</option>)}
                  {!spec.inputs.some((a) => a.name === inp.name) && <option value="__new">new agent input: {inp.name}</option>}
                </optgroup>
                {fileOpts.length > 0 && <optgroup label="Earlier step output">{fileOpts.map((f) => <option key={f.step + f.file} value={`$steps.${f.step}:${f.file}`}>{f.step} → {f.file}</option>)}</optgroup>}
                <option value="__literal">fixed value…</option>
              </select>
              {literal && <input className="input" style={{ marginTop: 6 }} disabled={!editable} value={cur.trim()} placeholder="value" onChange={(e) => set(e.target.value || " ")} />}
            </td>
          </tr>
        );
      })}
      <tr><td colSpan={2}>
        <label className="check-row"><input type="checkbox" checked={!!step.gate} disabled={!editable} onChange={(e) => onChange({ ...step, gate: e.target.checked || undefined }, [])} />
          Gate — if this skill says &quot;no&quot; (exit 1), the agent stops as <b>blocked</b>, not failed</label>
      </td></tr>
    </tbody></table></div>
  );
}

function ComposeEditor({ step, files, spec, editable, onChange }: {
  step: Extract<AgentStepSpec, { compose: unknown }>; files: { step: string; file: string }[]; spec: AgentSpec; editable: boolean;
  onChange: (s: Extract<AgentStepSpec, { compose: unknown }>) => void;
}) {
  const c = step.compose;
  const jsonFiles = files.filter((f) => f.file.endsWith(".json"));
  const rows = Object.entries(c.rows);
  const set = (patch: Partial<typeof c>) => onChange({ ...step, compose: { ...c, ...patch } });
  return (
    <div className="stack-sm">
      <div className="ab-grid">
        <div className="field"><label>Writes</label><input className="input" value={c.out} disabled={!editable} onChange={(e) => set({ out: e.target.value.replace(/[^\w.-]/g, "") })} /></div>
        <div className="field"><label>Format</label><select className="select" value={c.format} disabled={!editable} onChange={(e) => set({ format: e.target.value as "kv-csv" | "json" })}><option value="kv-csv">key,value CSV</option><option value="json">JSON</option></select></div>
        <div className="field"><label>Add rows from an input (optional)</label>
          <select className="select" value={c.include ?? ""} disabled={!editable} onChange={(e) => set({ include: e.target.value || undefined })}>
            <option value="">— none —</option>{spec.inputs.map((a) => <option key={a.name} value={`$in.${a.name}`}>{a.name}</option>)}
          </select></div>
      </div>
      <table className="mini"><thead><tr><th>Key</th><th>Value from</th><th /></tr></thead><tbody>
        {rows.map(([k, v]) => (
          <tr key={k}>
            <td><code>{k}</code></td>
            <td><input className="input mono-sm" value={v} disabled={!editable} placeholder="$steps.<id>:<file>#<key> or a fixed value"
              onChange={(e) => set({ rows: { ...c.rows, [k]: e.target.value } })} /></td>
            <td>{editable && <button type="button" className="btn btn-sm" onClick={() => { const r = { ...c.rows }; delete r[k]; set({ rows: r }); }}>×</button>}</td>
          </tr>
        ))}
      </tbody></table>
      {editable && <AddRow jsonFiles={jsonFiles} onAdd={(k, v) => set({ rows: { ...c.rows, [k]: v } })} />}
    </div>
  );
}

function AddRow({ jsonFiles, onAdd }: { jsonFiles: { step: string; file: string }[]; onAdd: (k: string, v: string) => void }) {
  const [k, setK] = useState(""); const [src, setSrc] = useState(""); const [key, setKey] = useState("");
  const value = src ? `${src}#${key}` : key;
  return (
    <div className="ab-grid">
      <input className="input" placeholder="key, e.g. eval_pass_rate" value={k} onChange={(e) => setK(e.target.value.replace(/[^\w-]/g, ""))} aria-label="Row key" />
      <select className="select" value={src} onChange={(e) => setSrc(e.target.value)} aria-label="Source file">
        <option value="">fixed value</option>{jsonFiles.map((f) => <option key={f.step + f.file} value={`$steps.${f.step}:${f.file}`}>{f.step} → {f.file}</option>)}
      </select>
      <input className="input" placeholder={src ? "json key, e.g. overall.pass_rate" : "value"} value={key} onChange={(e) => setKey(e.target.value)} aria-label="Key or value" />
      <button type="button" className="btn btn-sm btn-secondary" disabled={!k || !key} onClick={() => { onAdd(k, value); setK(""); setKey(""); }}>Add row</button>
    </div>
  );
}

function SkillPicker({ catalog, stages, onPick, onClose }: { catalog: CatalogSkill[]; stages: Stage[]; onPick: (c: CatalogSkill) => void; onClose: () => void }) {
  const [q, setQ] = useState(""); const [stage, setStage] = useState("all");
  const n = q.trim().toLowerCase();
  const list = catalog.filter((c) => (stage === "all" || c.stage === stage) && (!n || c.id.includes(n) || c.description.toLowerCase().includes(n)));
  return (
    <div className="card card-pad stack-sm ab-picker" role="dialog" aria-label="Add a skill">
      <div className="ab-grid">
        <input className="input" autoFocus placeholder="Search skills" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search skills" />
        <select className="select" value={stage} onChange={(e) => setStage(e.target.value)} aria-label="Stage">
          <option value="all">All stages</option>{stages.map((s) => <option key={s.id} value={s.id}>{s.n ? `${s.n} ` : ""}{s.name}</option>)}
        </select>
        <button type="button" className="btn btn-sm" onClick={onClose}>Close</button>
      </div>
      <ul className="ab-pick-list">
        {list.map((c) => (
          <li key={c.id}><button type="button" className="ab-pick" onClick={() => onPick(c)}>
            <b>{c.name}</b> <span className="caption">{stages.find((s) => s.id === c.stage)?.name ?? ""}</span>
            <span className="caption ab-pick-desc">{c.description.replace(/^Use when /i, "")}</span>
          </button></li>
        ))}
        {list.length === 0 && <li className="none">No skill matches.</li>}
      </ul>
    </div>
  );
}

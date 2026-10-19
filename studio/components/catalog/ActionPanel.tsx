"use client";
/* Self-service action on one repository: pick a skill, fill its form (folders come from the repository itself), run.
 * Under workspace policy the request may wait for a reviewer's approval; the result links to the run. */
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import type { ActionField } from "@/lib/actions/plan";

interface SkillOpt { slug: string; name: string; repo_skill: string | null; uses_model: boolean; fields: ActionField[] }
interface Loaded { applicable: string[]; skills: SkillOpt[]; folders: string[]; folders_error: string | null }
interface Result { ok: boolean; status?: string; action_id?: string; run_id?: string | null; message: string }

export function ActionPanel({ entityId, repo, approvalRule }: { entityId: string; repo: string; approvalRule: "none" | "model_steps" | "always" }) {
  const [data, setData] = useState<Loaded | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [slug, setSlug] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    let live = true;
    fetch(`/api/catalog/${entityId}/actions`).then(async (r) => {
      const j = await r.json();
      if (!live) return;
      if (!r.ok) { setLoadErr(j?.error?.message ?? `HTTP ${r.status}`); return; }
      setData(j as Loaded);
      const first = (j as Loaded).skills[0];
      if (first) setSlug(first.slug);
    }).catch((e) => live && setLoadErr(String(e)));
    return () => { live = false; };
  }, [entityId]);

  const skill = useMemo(() => data?.skills.find((s) => s.slug === slug) ?? null, [data, slug]);
  useEffect(() => {
    if (!skill) return;
    setValues(Object.fromEntries(skill.fields.map((f) => [f.name, f.kind === "folder" ? f.suggested : f.defaultValue ?? ""])));
    setResult(null);
  }, [skill]);
  const needsApproval = skill ? approvalRule === "always" || (approvalRule === "model_steps" && skill.uses_model) : false;

  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (!skill) return;
    setBusy(true); setResult(null);
    const inputs = Object.fromEntries(skill.fields.filter((f) => values[f.name]?.trim()).map((f) => [f.name, f.kind === "folder" ? { folder: values[f.name] } : { text: values[f.name] }]));
    try {
      const r = await fetch(`/api/catalog/${entityId}/actions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ skill: skill.slug, inputs, reason }) });
      const j = await r.json();
      setResult(r.status === 400 || r.status === 401 ? { ok: false, message: j?.error?.message ?? `HTTP ${r.status}` } : (j as Result));
    } catch (err) { setResult({ ok: false, message: String(err) }); }
    setBusy(false);
  }

  if (loadErr) return <p className="caption ink-rust">Could not load actions: {loadErr}</p>;
  if (!data) return <p className="caption">Loading the skills that can run on {repo}…</p>;
  if (!data.skills.length) return <p className="none">No workspace skill takes a folder yet, so none can run on a repository.</p>;

  return (
    <form onSubmit={run} className="auto-form action-form">
      <div className="field"><label htmlFor="act-skill">Skill</label>
        <select id="act-skill" className="select" value={slug} onChange={(e) => setSlug(e.target.value)}>
          {data.skills.map((s) => <option key={s.slug} value={s.slug}>{s.name}{s.repo_skill && data.applicable.includes(s.repo_skill) ? " — applies to this repository" : ""}{s.uses_model ? " · uses a model" : ""}</option>)}
        </select></div>
      {skill?.fields.map((f) => (
        <div className="field" key={f.name}>
          <label htmlFor={`act-${f.name}`}>{f.name}{f.required ? "" : " (optional)"}</label>
          {f.kind === "folder" ? (data.folders.length ? (
            <select id={`act-${f.name}`} className="select" value={values[f.name] ?? "."} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}>
              {!data.folders.includes(values[f.name] ?? ".") && <option value={values[f.name]}>{values[f.name]}</option>}
              {data.folders.map((d) => <option key={d} value={d}>{d === "." ? "(whole repository)" : d}</option>)}
            </select>) : <span className="caption ink-rust">The repository&apos;s folders could not be read{data.folders_error ? `: ${data.folders_error}` : ""}.</span>)
            : f.multiline ? <textarea id={`act-${f.name}`} className="input" rows={3} value={values[f.name] ?? ""} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })} />
              : <input id={`act-${f.name}`} className="input" value={values[f.name] ?? ""} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })} />}
          <span className="hint">{f.help}</span>
        </div>))}
      <div className="field"><label htmlFor="act-reason">Why (optional, shown to the approver)</label><input id="act-reason" className="input" maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} /></div>
      <div className="flex flex-wrap items-center gap-3">
        <button className="btn btn-primary btn-sm" type="submit" disabled={busy || !skill}>{busy ? "Running…" : needsApproval ? "Request approval" : `Run on ${repo.split("/")[1]}`}</button>
        <span className="caption">{needsApproval ? "Workspace policy: a reviewer approves this first." : "Reads the repository's files at the current commit. Nothing is written to GitHub."}</span>
      </div>
      {result && (
        <p role="status" className={`notice ${result.ok ? (result.status === "pending_approval" ? "notice-info" : "notice-ok") : "notice-err"}`} style={{ marginTop: 12 }}>
          {result.message}{" "}
          {result.run_id && <Link className="link" href={`/runs/${result.run_id}`}>Open the run</Link>}
          {result.status === "pending_approval" && <Link className="link" href="/inbox">Inbox</Link>}
        </p>)}
    </form>
  );
}

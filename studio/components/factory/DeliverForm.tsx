"use client";
/* The Deliver form: pipeline (filtered by mode), repository (catalog repos the workspace knows, or a checkout path),
 * ref, the request in the requester's words, and where it runs. Submits to the startDelivery server action. */
import { useMemo, useState } from "react";
import { ActionForm } from "./ActionForm";
import { startDelivery } from "@/app/deliverActions";

export interface PipelineOption { name: string; title: string; version: string; mode: "brownfield" | "greenfield"; description: string; stages: { id: string; role: string }[]; allowed: boolean }
export interface RepoOption { key: string; title: string }

export function DeliverForm({ pipelines, repos, githubConfigured }: { pipelines: PipelineOption[]; repos: RepoOption[]; githubConfigured: boolean }) {
  const [mode, setMode] = useState<"brownfield" | "greenfield">("brownfield");
  const inMode = useMemo(() => pipelines.filter((p) => p.mode === mode), [pipelines, mode]);
  const [pipeline, setPipeline] = useState<string>(inMode[0]?.name ?? "");
  const chosen = inMode.find((p) => p.name === pipeline) ?? inMode[0] ?? null;
  const switchMode = (m: "brownfield" | "greenfield") => { setMode(m); setPipeline(pipelines.find((p) => p.mode === m)?.name ?? ""); };
  if (!pipelines.length) return <div className="notice notice-info">No pipeline templates are shipped yet (pipelines/*.json in the library). Run <code>npm run ingest</code> after adding one.</div>;
  return (
    <ActionForm action={startDelivery} submit="Start delivery" className="card card-pad stack-sm" hidden={{ pipeline: chosen?.name ?? "" }}>
      <div className="form-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
        <div className="field">
          <label htmlFor="dl-mode">Mode</label>
          <select id="dl-mode" className="select" value={mode} onChange={(e) => switchMode(e.target.value as "brownfield" | "greenfield")}>
            <option value="brownfield">Brownfield — a change on an existing repository</option>
            <option value="greenfield">Greenfield — a new application from a brief</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="dl-pipeline">Pipeline</label>
          <select id="dl-pipeline" className="select" value={chosen?.name ?? ""} onChange={(e) => setPipeline(e.target.value)}>
            {inMode.map((p) => <option key={p.name} value={p.name} disabled={!p.allowed}>{p.title} · v{p.version}{p.allowed ? "" : " (not open to your roles)"}</option>)}
          </select>
          {chosen && <span className="hint">{chosen.description} Stages: {chosen.stages.map((s) => `${s.id} (${s.role})`).join(" → ")}.</span>}
        </div>
        <div className="field">
          <label htmlFor="dl-repo">Repository</label>
          <input id="dl-repo" name="repo" className="input" list="dl-repos" required placeholder={mode === "greenfield" ? "owner/new-app or a directory to create" : "owner/name from the catalog"} />
          <datalist id="dl-repos">{repos.map((r) => <option key={r.key} value={r.key}>{r.title}</option>)}</datalist>
          <span className="hint">{repos.length ? `${repos.length} repositories in the catalog.` : "No repositories in the catalog yet: connect GitHub under Platform → Repositories, or type one."}</span>
        </div>
        <div className="field">
          <label htmlFor="dl-ref">Branch or commit</label>
          <input id="dl-ref" name="ref" className="input" placeholder="default branch" />
        </div>
        <div className="field">
          <label htmlFor="dl-executor">Runs on</label>
          <select id="dl-executor" name="executor" className="select" defaultValue={githubConfigured ? "github-actions" : "ide"}>
            <option value="github-actions">GitHub Actions (delivery.yml in the library){githubConfigured ? "" : " — not configured"}</option>
            <option value="ide">My IDE (I run scripts/deliver.py and post evidence)</option>
          </select>
          {!githubConfigured && <span className="hint">DELIVERY_GITHUB_TOKEN is not set on the server: a GitHub Actions run stays queued until it is.</span>}
        </div>
      </div>
      <div className="field">
        <label htmlFor="dl-request">Request</label>
        <textarea id="dl-request" name="request" className="textarea" required minLength={4} placeholder="What should be delivered, in your own words. Acceptance criteria help." />
      </div>
    </ActionForm>
  );
}

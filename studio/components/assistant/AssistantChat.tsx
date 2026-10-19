"use client";
/* Assistant conversation: the question goes to /api/assistant with the recent turns; the answer is shown with the
 * evidence it rests on (which lookups ran, what they found, links to the records) and its token cost. */
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { mdToHtml } from "@/lib/markdown.mjs";

interface Evidence { tool: string; ok: boolean; summary: string; links: { title: string; href: string }[] }
interface Msg { role: "user" | "assistant"; content: string; evidence?: Evidence[]; meta?: string; error?: boolean }

const TOOL_LABEL: Record<string, string> = {
  search_catalog: "Searched the catalog", get_scorecard: "Read a scorecard", find_skill: "Searched the skills library",
  list_automation_runs: "Read automation runs", insights_summary: "Read Insights", list_initiatives: "Read initiatives",
  delivery_metrics: "Read delivery metrics", list_ai_assets: "Read AI assets", search_services_and_databases: "Searched services and databases",
};
/** The conversation survives navigation within this tab (sessionStorage); it is never sent anywhere but /api/assistant. */
const KEY = "sf-assistant-thread-v1";
const load = (): Msg[] => { try { const v = JSON.parse(sessionStorage.getItem(KEY) ?? "[]"); return Array.isArray(v) ? v.slice(-40) : []; } catch { return []; } };
const save = (m: Msg[]) => { try { sessionStorage.setItem(KEY, JSON.stringify(m.slice(-40))); } catch { /* private mode: in memory only */ } };

export function AssistantChat({ starters }: { starters: string[] }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const [loaded, setLoaded] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => { setMsgs(load()); setLoaded(true); }, []);
  useEffect(() => { if (loaded) save(msgs); }, [msgs, loaded]);
  useEffect(() => { if (!busy) { setElapsed(0); return; } const t0 = Date.now(); const id = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 1000); return () => clearInterval(id); }, [busy]);

  async function send(q: string) {
    const question = q.trim();
    if (!question || busy) return;
    const history = [...msgs.filter((m) => !m.error).map(({ role, content }) => ({ role, content })), { role: "user" as const, content: question }];
    setMsgs((m) => [...m, { role: "user", content: question }]);
    setDraft(""); setBusy(true);
    try {
      const res = await fetch("/api/assistant", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: history }) });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) setMsgs((m) => [...m, { role: "assistant", content: j?.error?.message ?? `The assistant failed (${res.status}).`, error: true }]);
      else {
        const u = j.usage ?? {};
        const meta = [`${j.model}`, `${(u.prompt ?? 0) + (u.completion ?? 0)} tokens`, u.cost_usd != null ? `$${Number(u.cost_usd).toFixed(4)}` : null, j.note, j.warning].filter(Boolean).join(" · ");
        setMsgs((m) => [...m, { role: "assistant", content: j.answer, evidence: j.evidence, meta }]);
      }
    } catch {
      setMsgs((m) => [...m, { role: "assistant", content: "Could not reach the server. Check your connection and try again.", error: true }]);
    } finally {
      setBusy(false);
      requestAnimationFrame(() => endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }));
    }
  }

  return (
    <div className="ask">
      {msgs.length === 0 && (
        <div className="ask-starters" aria-label="Example questions">
          {starters.map((s) => <button key={s} type="button" className="chip" onClick={() => send(s)}>{s}</button>)}
        </div>
      )}
      <ol className="ask-log" aria-live="polite">
        {msgs.map((m, i) => (
          <li key={i} className={`ask-msg ask-${m.role}${m.error ? " ask-error" : ""}`}>
            {m.role === "user" ? <p className="ask-q">{m.content}</p> : <>
              <div className="prose ask-a" dangerouslySetInnerHTML={{ __html: mdToHtml(m.content) }} />
              {!!m.evidence?.length && (
                <details className="ask-evidence">
                  <summary>Based on {m.evidence.length} lookup{m.evidence.length > 1 ? "s" : ""}</summary>
                  <ul>{m.evidence.map((e, j) => (
                    <li key={j}><span aria-hidden="true">{e.ok ? "✓" : "✕"}</span> {TOOL_LABEL[e.tool] ?? e.tool}: {e.summary}
                      {e.links.length > 0 && <span className="caption"> — {e.links.slice(0, 6).map((l, k) => (
                        <span key={l.href}>{k > 0 && ", "}{l.href.startsWith("/") ? <Link className="link" href={l.href}>{l.title}</Link> : <a className="link" href={l.href} target="_blank" rel="noreferrer">{l.title}</a>}</span>))}</span>}
                    </li>))}</ul>
                </details>)}
              {m.meta && <p className="caption ask-meta">{m.meta}</p>}
            </>}
          </li>))}
        {busy && <li className="ask-msg ask-assistant"><p className="caption" role="status">Looking it up in your workspace… {elapsed > 2 ? `${elapsed}s` : ""}</p></li>}
      </ol>
      <div ref={endRef} />
      <form className="ask-form" onSubmit={(e) => { e.preventDefault(); send(draft); }}>
        <label htmlFor="ask-input" className="sr-only">Ask about your catalog, scorecards, automations, insights or skills</label>
        <textarea id="ask-input" className="input" rows={2} maxLength={4000} value={draft} disabled={busy}
          placeholder="Ask about your repositories, scorecards, automations, insights or skills…"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(draft); } }} />
        <div className="ask-actions">
          {msgs.length > 0 && <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => setMsgs([])}>New conversation</button>}
          <button type="submit" className="btn btn-primary btn-sm" disabled={busy || !draft.trim()}>{busy ? "Asking…" : "Ask"}</button>
        </div>
      </form>
    </div>
  );
}

"use client";
/* A file row you can open: click to preview its text in place (first 40 KB), or open the raw file. Files come from the
 * skill bundle served at /runtime/repo/skills/<id>/… (read-only; the same files the runtime uses). */
import { useState } from "react";

const MAX = 40_000;
export function FilePreview({ href, label }: { href: string; label: string }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function toggle() {
    const next = !open; setOpen(next);
    if (!next || text != null || err) return;
    try {
      const r = await fetch(href);
      if (!r.ok) { setErr(`Could not load the file (HTTP ${r.status}).`); return; }
      const t = await r.text();
      setText(t.length > MAX ? `${t.slice(0, MAX)}\n… (preview cut at 40 KB; open the raw file for the rest)` : t);
    } catch (e) { setErr(String(e)); }
  }
  return (
    <li className="file-row">
      <button type="button" className="link file-row-name" aria-expanded={open} onClick={toggle}>{label}</button>
      {" "}<a className="caption link" href={href} target="_blank" rel="noreferrer">raw</a>
      {open && (err ? <p className="caption ink-rust">{err}</p> : <pre className="file-row-pre">{text ?? "Loading…"}</pre>)}
    </li>
  );
}

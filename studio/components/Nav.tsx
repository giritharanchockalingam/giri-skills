"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { createBrowserSupabase } from "@/lib/supabase/client";
import type { Session } from "@supabase/supabase-js";
import { supabaseConfigured } from "@/lib/supabase/env";
import { SECTIONS, sectionOf } from "@/lib/nav";

const TOP = SECTIONS.filter((x) => x.id !== "admin");
const ADMIN = SECTIONS.find((x) => x.id === "admin")!;

export function Nav() {
  const path = usePathname();
  const [email, setEmail] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => { setOpen(false); }, [path]);
  useEffect(() => {
    document.body.dataset.navOpen = open ? "true" : "false";
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  useEffect(() => {
    if (!supabaseConfigured()) return;
    const sb = createBrowserSupabase();
    sb.auth.getUser().then(({ data }: { data: { user: { email?: string } | null } }) => setEmail(data.user?.email ?? null));
    const { data: sub } = sb.auth.onAuthStateChange((_e: string, s: Session | null) => setEmail(s?.user?.email ?? null));
    return () => sub.subscription.unsubscribe();
  }, []);
  const current = sectionOf(path);
  const active = (id: string) => current?.id === id;
  if (path === "/login") return null;
  return (
    <header className="topbar">
      <div className="wrap">
        <Link href="/" className="brand" aria-label="Skills Factory home">
          <span className="brand-mark" aria-hidden="true">G</span>
          <span className="brand-name">Skills Factory</span>
          <span className="brand-sub">· giri-skills</span>
        </Link>
        <nav className="topnav" aria-label="Areas">
          {TOP.map((l) => <Link key={l.id} href={l.href} aria-current={active(l.id) ? "page" : undefined} title={l.hint}>{l.label}</Link>)}
        </nav>
        <button type="button" className="nav-toggle" aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open} aria-controls="nav-sheet" onClick={() => setOpen((o) => !o)}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">{open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}</svg>
        </button>
        <div className="user">
          <Link href="/glossary" className="btn btn-icon nav-help" aria-label="Glossary: the words this portal uses" title="Glossary">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10" /><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3" /><path d="M12 17h.01" /></svg>
          </Link>
          <Link href={ADMIN.href} className={`btn btn-icon nav-admin${active("admin") ? " is-on" : ""}`} aria-label="Admin: members, keys, policies, audit log" title="Admin" aria-current={active("admin") ? "page" : undefined}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></svg>
          </Link>
          {email && <Link href="/admin#account" className="btn btn-icon" aria-label={`Account and workspace (${email})`} title={email}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="8" r="4" /><path d="M4 20c0-4 4-6 8-6s8 2 8 6" /></svg></Link>}
        </div>
      </div>
      <nav id="nav-sheet" className="nav-sheet" data-open={open} aria-label="Areas (menu)" hidden={!open}>
        {SECTIONS.map((l) => (
          <div key={l.id} className="nav-sheet-group">
            <Link href={l.href} aria-current={active(l.id) ? "page" : undefined} onClick={() => setOpen(false)}>
              <span>{l.label}</span><span className="nav-hint">{l.hint}</span>
            </Link>
            {l.pages.length > 0 && <div className="nav-sheet-pages">{l.pages.map((pg) => <Link key={pg.href} href={pg.href} onClick={() => setOpen(false)}>{pg.label}</Link>)}</div>}
          </div>
        ))}
      </nav>
    </header>
  );
}

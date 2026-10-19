"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { createBrowserSupabase } from "@/lib/supabase/client";
import type { Session } from "@supabase/supabase-js";
import { supabaseConfigured } from "@/lib/supabase/env";

const links: { href: string; label: string; short?: string; hint?: string; match: string[] }[] = [
  { href: "/", label: "Home", hint: "What do you need done?", match: ["/"] },
  { href: "/catalog", label: "Catalog", hint: "Your repositories and scorecards", match: ["/catalog"] },
  { href: "/insights", label: "Insights", hint: "Usage, spend and ROI", match: ["/insights"] },
  { href: "/automations", label: "Automations", hint: "Run on GitHub events", match: ["/automations"] },
  { href: "/assistant", label: "Assistant", hint: "Ask your workspace", match: ["/assistant"] },
  { href: "/roles", label: "Roles & teams", hint: "Roles and talent pools", match: ["/roles", "/pools"] },
  { href: "/agents", label: "Playbooks", hint: "Skills chained into agents", match: ["/agents", "/agent-runs/"] },
  { href: "/repo/", label: "Library", hint: "Every skill", match: ["/repo", "/upstream/"] },
  { href: "/connect", label: "Connect", hint: "API and MCP", match: ["/connect"] },
  { href: "/admin", label: "Admin", hint: "Members, keys, pipeline", match: ["/admin", "/pipeline", "/skills/", "/evaluations", "/evals/", "/findings/", "/activity", "/runs/"] },
];

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
  const active = (l: (typeof links)[number]) => l.match.some((m) => (m === "/" ? path === "/" : path.startsWith(m)));
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
          {links.map((l) => (
            <Link key={l.href} href={l.href} aria-current={active(l) ? "page" : undefined}>
              <span className="only-desktop">{l.label}</span><span className="only-mobile">{l.short ?? l.label}</span>
            </Link>
          ))}
        </nav>
        <button type="button" className="nav-toggle" aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open} aria-controls="nav-sheet" onClick={() => setOpen((o) => !o)}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">{open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}</svg>
        </button>
        <div className="user">
          {email && <Link href="/admin#account" className="btn btn-icon" aria-label={`Account and workspace (${email})`} title={email}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="8" r="4" /><path d="M4 20c0-4 4-6 8-6s8 2 8 6" /></svg></Link>}
        </div>
      </div>
      <nav id="nav-sheet" className="nav-sheet" data-open={open} aria-label="Areas (menu)" hidden={!open}>
        {links.map((l) => (
          <Link key={l.href} href={l.href} aria-current={active(l) ? "page" : undefined} onClick={() => setOpen(false)}>
            <span>{l.label}</span>{l.hint && <span className="nav-hint">{l.hint}</span>}
          </Link>
        ))}
      </nav>
    </header>
  );
}

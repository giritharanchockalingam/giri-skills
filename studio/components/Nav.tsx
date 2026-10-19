"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { createBrowserSupabase } from "@/lib/supabase/client";
import type { Session } from "@supabase/supabase-js";
import { supabaseConfigured } from "@/lib/supabase/env";

const links = [
  { href: "/overview", label: "Overview", match: ["/overview"] },
  { href: "/", label: "Skills", match: ["/", "/skills/", "/repo/", "/upstream/"] },
  { href: "/agents", label: "Agents", match: ["/agents", "/agent-runs/"] },
  { href: "/roles", label: "Roles", match: ["/roles"] },
  { href: "/pools", label: "Talent pools", short: "Pools", match: ["/pools"] },
  { href: "/evaluations", label: "Evaluations", match: ["/evaluations", "/evals/", "/findings/"] },
  { href: "/activity", label: "Activity", match: ["/activity", "/runs/"] },
  { href: "/admin", label: "Administration", short: "Admin", match: ["/admin"] },
];

export function Nav() {
  const path = usePathname();
  const [email, setEmail] = useState<string | null>(null);
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
        <Link href="/overview" className="brand" aria-label="Skills Factory home">
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
        <div className="user">
          {email && <span className="user-chip" title={email}>{email}</span>}
          {email && <Link href="/admin#account" className="btn btn-icon" aria-label="Account and workspace"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="8" r="4" /><path d="M4 20c0-4 4-6 8-6s8 2 8 6" /></svg></Link>}
        </div>
      </div>
    </header>
  );
}

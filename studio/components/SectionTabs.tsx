"use client";
/* The pages inside the current section, as tabs under the top bar (Catalog: repositories, services, databases, AI
 * assets, initiatives, integrations; Skills: library, publish pipeline, evaluations, roles, teams, runs, reference). */
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { sectionOf } from "@/lib/nav";

export function SectionTabs() {
  const path = usePathname();
  const q = useSearchParams();
  const s = sectionOf(path);
  if (!s || !s.pages.length || path === "/login") return null;
  const query = new URLSearchParams(q.toString());
  return (
    <div className="section-tabs">
      <nav className="wrap subnav" aria-label={`${s.label} pages`}>
        {s.pages.map((pg) => <Link key={pg.href} href={pg.href} aria-current={pg.match(path, query) ? "page" : undefined}>{pg.label}</Link>)}
      </nav>
    </div>
  );
}

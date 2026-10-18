"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Meta } from "@/lib/data";

const links = [
  { href: "/", label: "Skills" },
  { href: "/evals/", label: "Evals" },
  { href: "/findings/", label: "Findings" },
  { href: "/upstream/", label: "Upstream" },
];

export function Nav({ meta }: { meta: Meta }) {
  const path = usePathname();
  const active = (href: string) => (href === "/" ? path === "/" || path.startsWith("/skills/") : path.startsWith(href));
  return (
    <header className="topbar">
      <div className="wrap">
        <Link href="/" className="brand" aria-label="giri-skills home">
          <span className="brand-mark" aria-hidden="true">G</span>
          <span className="brand-name">giri-skills</span>
          <span className="brand-sub">· skills factory</span>
        </Link>
        <nav className="topnav" aria-label="Views">
          {links.map((l) => (
            <Link key={l.href} href={l.href} aria-current={active(l.href) ? "page" : undefined}>
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="topmeta" title={`Results: ${meta.resultsDir}`}>
          {meta.model} · {meta.runs} runs · {meta.date} · {meta.spend}
        </div>
      </div>
    </header>
  );
}

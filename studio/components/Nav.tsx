"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Meta } from "@/lib/data";

const links = [
  { href: "/", label: "Skills" },
  { href: "/evals/", label: "Evals" },
  { href: "/findings/", label: "Findings" },
];

export function Nav({ meta }: { meta: Meta }) {
  const path = usePathname();
  const active = (href: string) => (href === "/" ? path === "/" || path.startsWith("/skills/") : path.startsWith(href));
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-bg-2">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2">
        <Link href="/" className="mono text-[13px] font-semibold text-fg hover:no-underline">giri-skills</Link>
        <nav className="flex gap-1" aria-label="Views">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              aria-current={active(l.href) ? "page" : undefined}
              className={`rounded px-2 py-0.5 text-[12.5px] hover:no-underline ${active(l.href) ? "bg-bg-3 font-semibold text-fg" : "text-fg-2 hover:text-fg"}`}
            >
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="mono ml-auto text-[11px] text-fg-3" title={`results: ${meta.resultsDir}`}>
          {meta.provider}/{meta.model} · runs={meta.runs} · seed={meta.seed} · {meta.date} · spend {meta.spend} (est.)
        </div>
      </div>
    </header>
  );
}

"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

export interface TabDef { seg: string; label: string; count?: number }
interface Props { base: string; tabs: TabDef[]; keep?: string[]; label?: string }

/** Sticky, URL-addressable tab bar for a detail page: each tab is a sub-route under `base` (seg "" = the base itself).
 *  Query params named in `keep` (the selected version, ?v=) travel with the navigation; pages that keep none stay
 *  statically renderable (no useSearchParams). Scrolls horizontally on narrow screens. */
export function TabBar(props: Props) {
  return props.keep && props.keep.length > 0 ? <WithParams {...props} keep={props.keep} /> : <Bar {...props} query="" />;
}

function WithParams(props: Props & { keep: string[] }) {
  const params = useSearchParams();
  const query = props.keep.map((k) => (params.get(k) ? `${k}=${encodeURIComponent(params.get(k) as string)}` : "")).filter(Boolean).join("&");
  return <Bar {...props} query={query} />;
}

function Bar({ base, tabs, label = "Views", query }: Props & { query: string }) {
  const path = usePathname().replace(/\/$/, "");
  return (
    <nav className="subnav tabbar" aria-label={label}>
      {tabs.map((t) => {
        const href = `${base}${t.seg ? `/${t.seg}` : ""}/${query ? `?${query}` : ""}`;
        const current = t.seg ? path === `${base}/${t.seg}` : path === base;
        return (
          <Link key={t.seg} href={href} aria-current={current ? "page" : undefined}>
            {t.label}{t.count != null && <span className="tab-count">{t.count}</span>}
          </Link>
        );
      })}
    </nav>
  );
}

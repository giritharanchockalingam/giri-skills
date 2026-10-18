"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

const views = [
  { seg: "", label: "Summary" }, { seg: "authoring", label: "Authoring" }, { seg: "test", label: "Test" },
  { seg: "evaluations", label: "Evaluations" }, { seg: "release", label: "Release" }, { seg: "activity", label: "Activity" },
];

/** The coherent views of one skill; the selected version (?v=) travels with the navigation. */
export function SkillSubNav({ slug }: { slug: string }) {
  const path = usePathname().replace(/\/$/, "");
  const v = useSearchParams().get("v");
  const base = `/skills/${slug}`;
  return (
    <nav className="subnav" aria-label="Skill views">
      {views.map((x) => {
        const href = `${base}${x.seg ? `/${x.seg}` : ""}${v ? `?v=${v}` : ""}`;
        const current = x.seg ? path === `${base}/${x.seg}` : path === base;
        return <Link key={x.seg} href={href} aria-current={current ? "page" : undefined}>{x.label}</Link>;
      })}
    </nav>
  );
}

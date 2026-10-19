"use client";
/* Starting point (new / existing) and role filter for the lifecycle view. State lives in the URL so views are shareable. */
import { usePathname, useRouter, useSearchParams } from "next/navigation";

export function LifecycleFilters({ roles }: { roles: { slug: string; title: string }[] }) {
  const router = useRouter();
  const path = usePathname();
  const q = useSearchParams();
  const start = q.get("start") === "existing" ? "existing" : "new";
  const set = (k: string, v: string | null) => {
    const n = new URLSearchParams(q.toString());
    if (v) n.set(k, v); else n.delete(k);
    router.replace(`${path}?${n.toString()}`, { scroll: false });
  };
  return (
    <div className="lc-filters">
      <div className="lc-seg" role="radiogroup" aria-label="Starting point">
        <button type="button" role="radio" aria-checked={start === "new"} className={start === "new" ? "on" : ""} onClick={() => set("start", "new")}>
          Starting new<span>nothing built yet</span>
        </button>
        <button type="button" role="radio" aria-checked={start === "existing"} className={start === "existing" ? "on" : ""} onClick={() => set("start", "existing")}>
          Improving what exists<span>you have a system, repo or documents</span>
        </button>
      </div>
      <label className="lc-role">
        <span className="caption">Show skills for</span>
        <select className="select" value={q.get("role") ?? ""} onChange={(e) => set("role", e.target.value || null)} aria-label="Role">
          <option value="">every role</option>
          {roles.map((r) => <option key={r.slug} value={r.slug}>{r.title}</option>)}
        </select>
      </label>
    </div>
  );
}

import Link from "next/link";
import { VersionPill } from "./Pills";
import type { VersionRow } from "@/lib/factory/db";

/** Which version this view is showing, with a switch to the others (the selection travels in ?v=). */
export function VersionBar({ slug, view, versions, current, right }: { slug: string; view: string; versions: VersionRow[]; current: VersionRow; right?: React.ReactNode }) {
  const base = `/skills/${slug}${view ? `/${view}` : ""}`;
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 mb-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="h3">v{current.version}</span>
        <VersionPill status={current.status} />
        <span className="caption">{current.source.kind === "repo" ? `from repository ${current.source.repo_skill}` : "authored"} · manifest {current.manifest_hash.slice(0, 12)}…</span>
        {versions.length > 1 && (
          <span className="caption flex flex-wrap gap-x-2" aria-label="Other versions">
            {versions.map((x) => x.id === current.id ? null : <Link key={x.id} href={`${base}?v=${x.version}`} className="link">v{x.version} ({x.status.replace("_", " ")})</Link>)}
          </span>
        )}
      </div>
      {right}
    </div>
  );
}

/* Library drift: a repo-sourced version is pinned to the library files it was reviewed with (sha256 in source.content_sha).
 * When the library changes, a version past draft can no longer run (the runtime refuses: see pins.ts) and a draft's
 * contract may be out of date. Pure: the deployed pin is passed in. */
import type { VersionSource } from "./db.ts";

/** "blocked": past draft and its pinned files are gone — it cannot run until a new version is published.
 *  "library_updated": a draft whose library files changed since it was created (contract may be stale).
 *  "current": pinned to the deployed files. "n/a": authored here or never pinned. */
export type Drift = "current" | "library_updated" | "blocked" | "n/a";

export function driftOf(source: VersionSource | null | undefined, status: string | null | undefined, deployedPin: string | null): Drift {
  if (!source || source.kind !== "repo") return "n/a";
  if (!deployedPin) return status && status !== "draft" ? "blocked" : "library_updated";   // skill removed from the library
  if (!source.content_sha) return "n/a";
  if (source.content_sha === deployedPin) return "current";
  return !status || status === "draft" ? "library_updated" : "blocked";
}

/** What a caller depends on: inputs (name, type, required), run steps and declared outputs. Instructions and wording are
 *  excluded, so a workspace's own edits to the text never count as drift. */
type ContractLike = { inputs?: { name: string; type?: string; required?: boolean }[]; run?: { step?: string; cmd?: string; template?: string }[]; outputs?: { path: string; checks?: unknown[] }[] } | null | undefined;
export const contractKey = (m: ContractLike): string | null => !m ? null : JSON.stringify({
  i: (m.inputs ?? []).map((x) => [x.name, x.type ?? "string", !!x.required]),
  r: (m.run ?? []).map((x) => [x.step ?? "", x.cmd ?? x.template ?? ""]),
  o: (m.outputs ?? []).map((x) => [x.path, x.checks ?? []]),
});

/** The skill-level answer: a live version that cannot run outranks everything; otherwise the newest version's state. */
export function skillDrift(versions: { source: VersionSource; status: string; version: number; contract?: string | null }[], pinOf: (repoSkill?: string) => string | null, libraryContract?: string | null, draftCasesStale = false): Drift {
  const live = versions.find((v) => v.status === "published");
  if (live && driftOf(live.source, live.status, pinOf(live.source.repo_skill)) === "blocked") return "blocked";
  const newest = [...versions].sort((a, b) => b.version - a.version)[0];
  if (!newest) return "n/a";
  const d = driftOf(newest.source, newest.status, pinOf(newest.source.repo_skill));
  if (d === "blocked" && newest.status === "superseded") return "current";
  // same files, older contract (e.g. the library added an input after import): callers cannot use what the library offers
  if ((d === "current" || d === "n/a") && newest.source.kind === "repo" && libraryContract && newest.contract && newest.contract !== libraryContract) return "library_updated";
  // same files, but the draft's copy of the library's test cases is older (it would be graded against the old checks)
  if (d === "current" && newest.status === "draft" && draftCasesStale) return "library_updated";
  // a library draft imported before pinning: updating pins it to the deployed files and brings its cases current
  if (d === "n/a" && newest.status === "draft" && newest.source.kind === "repo" && !newest.source.content_sha && pinOf(newest.source.repo_skill)) return "library_updated";
  return d;
}

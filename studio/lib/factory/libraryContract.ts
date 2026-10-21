/* The executable contract the library currently offers for a repo skill (null when it has none). Server-side. */
import { manifestFromRepoSkill, casesFromRepoSkill, type RepoSkill } from "./import";
import { contractKey } from "./drift";
import { skills as repoSkills } from "@/lib/data";

const cache = new Map<string, string | null>();
export function libraryContract(repoSkill: string | undefined): string | null {
  if (!repoSkill) return null;
  if (!cache.has(repoSkill)) {
    const s = (repoSkills as unknown as RepoSkill[]).find((x) => x.id === repoSkill);
    const m = s ? manifestFromRepoSkill(s) : null;
    cache.set(repoSkill, m && m.ok ? contractKey(m.manifest) : null);
  }
  return cache.get(repoSkill)!;
}

/** Key-order-independent JSON (jsonb reorders object keys). */
const canon = (v: unknown): string => Array.isArray(v) ? `[${v.map(canon).join(",")}]`
  : v && typeof v === "object" ? `{${Object.keys(v as object).sort().map((k) => `${JSON.stringify(k)}:${canon((v as Record<string, unknown>)[k])}`).join(",")}}`
  : JSON.stringify(v ?? null);

/** True when a draft's copy of the library's evaluation cases differs from the library's (a case missing, or its inputs
 *  or checks changed): the evaluation would grade the library's files against an old contract. Cases the workspace
 *  added under other names are not compared. */
export function libraryCasesStale(repoSkill: string | undefined, rows: { name: string; inputs: unknown; checks: unknown }[]): boolean {
  if (!repoSkill) return false;
  const s = (repoSkills as unknown as RepoSkill[]).find((x) => x.id === repoSkill);
  if (!s) return false;
  const have = new Map(rows.map((r) => [r.name, r]));
  return casesFromRepoSkill(s).some((c) => {
    const r = have.get(c.name);
    return !r || canon(r.inputs) !== canon(c.inputs) || canon(r.checks) !== canon(c.checks);
  });
}

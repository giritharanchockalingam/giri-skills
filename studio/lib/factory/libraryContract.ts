/* The executable contract the library currently offers for a repo skill (null when it has none). Server-side. */
import { manifestFromRepoSkill, type RepoSkill } from "./import";
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

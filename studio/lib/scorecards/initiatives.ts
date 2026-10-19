/* Initiative progress, computed from the live scorecard (never stored, so it cannot drift). Pure. */
import { levelOf, factsOf, atLeast, type Level, type LevelResult } from "./levels";
import type { EntityFacts } from "./checks";

export interface ScopeEntity { id: string; key: string; properties: { stack?: { id: string }[]; counts?: { migrations: number; files: number } } }
export interface RepoProgress { key: string; id: string | null; met: boolean; result: LevelResult | null; note?: string }
export interface Progress { repos: RepoProgress[]; met: number; total: number; pct: number; daysLeft: number; overdue: boolean }

export function progressOf(
  ini: { target_level: Level; repos: string[]; due_on: string; status?: string },
  entities: ScopeEntity[],
  latest: Map<string, { check_id: string; verdict: string }[]>,
  today: Date = new Date(),
): Progress {
  const byKey = new Map(entities.map((e) => [e.key.toLowerCase(), e]));
  const scoped: RepoProgress[] = [];
  const add = (e: ScopeEntity) => {
    const result = levelOf(factsOf(e.properties) as EntityFacts, latest.get(e.id) ?? []);
    scoped.push({ key: e.key, id: e.id, met: atLeast(result.level, ini.target_level), result,
      note: result.level === "n/a" ? "no check applies, so no level can be reached" : undefined });
  };
  if (ini.repos.length) {
    for (const k of ini.repos) { const e = byKey.get(k.toLowerCase()); if (e) add(e); else scoped.push({ key: k, id: null, met: false, result: null, note: "not in the catalog" }); }
  } else {
    for (const e of entities) { const r = levelOf(factsOf(e.properties) as EntityFacts, latest.get(e.id) ?? []); if (r.level !== "n/a") add(e); }
  }
  scoped.sort((a, b) => Number(a.met) - Number(b.met) || a.key.localeCompare(b.key));
  const met = scoped.filter((r) => r.met).length;
  const due = new Date(`${ini.due_on}T23:59:59Z`);
  const daysLeft = Math.ceil((due.getTime() - today.getTime()) / 86_400_000);
  return { repos: scoped, met, total: scoped.length, pct: scoped.length ? Math.round((met / scoped.length) * 100) : 0, daysLeft, overdue: daysLeft < 0 && met < scoped.length };
}

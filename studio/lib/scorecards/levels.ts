/* Scorecard levels (Port-style): a repository's level follows from its latest verdicts on the checks that apply to it.
 * Pure (no I/O) so the catalog, repository pages, initiatives and the assistant all compute the same answer.
 *   Bronze — every applicable check has a verdict (none missing, none errored): the repository is measured.
 *   Silver — Bronze, and no check fails (warnings allowed).
 *   Gold   — every applicable check passes.
 * A repository no check applies to has no level ("not applicable") — never a made-up one. */
import { checksFor, CHECKS, type EntityFacts } from "./checks";

export const LEVELS = ["bronze", "silver", "gold"] as const;
export type Level = (typeof LEVELS)[number];
export type LevelOrNone = Level | "none" | "n/a";
export const LEVEL_LABEL: Record<LevelOrNone, string> = { gold: "Gold", silver: "Silver", bronze: "Bronze", none: "Below bronze", "n/a": "No checks apply" };
export const LEVEL_RULE: Record<Level, string> = {
  bronze: "every applicable check has run without error",
  silver: "no applicable check fails",
  gold: "every applicable check passes",
};

export interface LatestVerdict { check_id: string; verdict: string; summary?: string }
export interface Blocker { check_id: string; title: string; verdict: string | null; reason: string }
export interface LevelResult { level: LevelOrNone; applicable: string[]; next: Level | null; blockers: Blocker[] }

const rank = (l: LevelOrNone) => (l === "gold" ? 3 : l === "silver" ? 2 : l === "bronze" ? 1 : 0);
export const atLeast = (have: LevelOrNone, want: Level) => have !== "n/a" && rank(have) >= rank(want);
const titleOf = (id: string) => CHECKS.find((c) => c.id === id)?.title.split(" (")[0] ?? id;

/** Which rules a verdict breaks for a level (null verdict = never scored). */
function breaks(level: Level, verdict: string | null): string | null {
  if (verdict === null) return "not scored yet";
  if (verdict === "error" || verdict === "skipped") return "the last run did not finish";
  if (level === "bronze") return null;
  if (verdict === "fail") return "fails";
  if (level === "silver") return null;
  return verdict === "pass" ? null : "has warnings";
}

export function levelOf(facts: EntityFacts, latest: LatestVerdict[]): LevelResult {
  const applicable = checksFor(facts).map((c) => c.id);
  if (!applicable.length) return { level: "n/a", applicable, next: null, blockers: [] };
  const v = (id: string) => latest.find((r) => r.check_id === id)?.verdict ?? null;
  const blockersFor = (l: Level): Blocker[] => applicable.flatMap((id) => {
    const reason = breaks(l, v(id));
    return reason ? [{ check_id: id, title: titleOf(id), verdict: v(id), reason }] : [];
  });
  let level: LevelOrNone = "none";
  for (const l of LEVELS) { if (blockersFor(l).length) break; level = l; }
  const next: Level | null = level === "gold" ? null : (LEVELS as readonly Level[])[rank(level)];
  return { level, applicable, next, blockers: next ? blockersFor(next) : [] };
}

/** Facts for levelOf from a catalog entity's stored properties (the same derivation the scorecard engine uses). */
export const factsOf = (p: { stack?: { id: string }[]; counts?: { migrations: number; files: number } }): EntityFacts =>
  ({ stackIds: (p.stack ?? []).map((s) => s.id), counts: p.counts ?? { migrations: 0, files: 0 } });

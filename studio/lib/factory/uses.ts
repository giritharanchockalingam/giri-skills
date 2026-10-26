/* Validation of a skill-use report (POST /api/v1/uses). Pure: no I/O, unit-tested. */
export interface SkillUse { slug: string; version: number; sha256?: string; event: "loaded" | "blocked"; integrity: "verified" | "modified" | "unknown"; session?: string }

const EVENTS = ["loaded", "blocked"] as const;
const INTEGRITY = ["verified", "modified", "unknown"] as const;

/** The report, or a one-line reason it is refused. */
export function parseUse(b: Record<string, unknown>): SkillUse | string {
  const slug = b.slug, version = b.version, sha = b.sha256, event = b.event, integrity = b.integrity, session = b.session;
  if (typeof slug !== "string" || !/^[a-z0-9-]{1,80}$/.test(slug)) return "slug must be a skill slug (lowercase letters, digits, dashes).";
  if (typeof version !== "number" || !Number.isInteger(version) || version < 1) return "version must be a positive integer.";
  if (sha !== undefined && sha !== null && (typeof sha !== "string" || !/^[0-9a-f]{64}$/.test(sha))) return "sha256 must be 64 hex characters.";
  if (!EVENTS.includes(event as never)) return `event must be one of ${EVENTS.join(", ")}.`;
  if (!INTEGRITY.includes(integrity as never)) return `integrity must be one of ${INTEGRITY.join(", ")}.`;
  if (session !== undefined && session !== null && (typeof session !== "string" || !/^[A-Za-z0-9._:-]{1,128}$/.test(session))) return "session must be an opaque id (≤128 letters, digits, . _ : -).";
  if (typeof session === "string" && /^sf_live_/.test(session)) return "session looks like an API key — refusing to store it.";
  return { slug, version, sha256: typeof sha === "string" ? sha : undefined, event: event as SkillUse["event"], integrity: integrity as SkillUse["integrity"], session: typeof session === "string" ? session : undefined };
}

/** A recorded use as the skill's Activity page reads it (RLS: workspace members). */
export interface SkillUseRow { id: string; created_at: string; event: "loaded" | "blocked"; integrity: "verified" | "modified" | "unknown"; currency: "current" | "stale" | "unpublished" }

/** Plain words for one use. */
export function skillUseLabels(u: Pick<SkillUseRow, "event" | "integrity" | "currency">): { result: string; files: string; currency: string } {
  return {
    result: u.event === "loaded" ? "Loaded" : "Blocked",
    files: u.integrity === "verified" ? "Approved files" : u.integrity === "modified" ? "Changed after approval" : "Not in the approved list",
    currency: u.currency === "current" ? "Current published version" : u.currency === "stale" ? "Older version (plugin not updated)" : "Skill no longer published",
  };
}

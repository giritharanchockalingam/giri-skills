/* Who can run which skill when "Restrict skills by job role" is on. Mirrors the database rule (sf_run_access in
 * 0019_sf_role_access.sql) so the Admin preview shows exactly what the database will enforce:
 *   - authors, reviewers and admins are never restricted (they test before release);
 *   - a consumer or an API key may run a published skill when one of its assigned, PUBLISHED job roles lists the
 *     skill by library id or by workspace slug. Pure; unit-tested. */

export type Access = "consumer" | "author" | "reviewer" | "admin";
export interface Holder { kind: "user" | "key"; id: string; label: string; access: Access | "key" }
export interface JobRole { id: string; slug: string; name: string; skills: string[]; playbooks: string[] }
export interface PublishedSkill { slug: string; title: string; repoSkill: string | null }
export interface Assignment { id: string; talent_id: string; user_id: string | null; api_key_id: string | null }

export const isRestricted = (h: Holder) => h.access === "consumer" || h.access === "key";
export const skillKeys = (s: PublishedSkill) => [s.repoSkill, s.slug].filter((x): x is string => !!x);
export const roleCovers = (r: JobRole, s: PublishedSkill) => skillKeys(s).some((k) => r.skills.includes(k));
const holds = (a: Assignment, h: Holder) => (h.kind === "user" ? a.user_id === h.id : a.api_key_id === h.id);

export interface HolderAccess { holder: Holder; roles: JobRole[]; skills: PublishedSkill[] }
export interface AccessPreview {
  restricted: HolderAccess[];        // consumers and keys, with what they could run if the switch is on
  withoutRole: Holder[];             // would be able to run nothing
  uncovered: PublishedSkill[];       // published skills no job role lists: only builders could run them
}

export function accessPreview(input: { holders: Holder[]; roles: JobRole[]; skills: PublishedSkill[]; assignments: Assignment[] }): AccessPreview {
  const byId = new Map(input.roles.map((r) => [r.id, r]));
  const restricted = input.holders.filter(isRestricted).map((holder) => {
    const roles = input.assignments.filter((a) => holds(a, holder)).map((a) => byId.get(a.talent_id)).filter((r): r is JobRole => !!r);
    return { holder, roles, skills: input.skills.filter((s) => roles.some((r) => roleCovers(r, s))) };
  });
  return {
    restricted,
    withoutRole: restricted.filter((h) => h.roles.length === 0).map((h) => h.holder),
    uncovered: input.skills.filter((s) => !input.roles.some((r) => roleCovers(r, s))),
  };
}

/** "user:<uuid>" | "key:<uuid>" from the assign form. */
export function parseHolder(v: string): { kind: "user" | "key"; id: string } | null {
  const m = /^(user|key):([0-9a-f-]{36})$/i.exec(v.trim());
  return m ? { kind: m[1].toLowerCase() as "user" | "key", id: m[2].toLowerCase() } : null;
}

/** Skill keys (library ids and workspace slugs) the given user may run through their job roles. */
export function allowedKeysFor(userId: string, roles: JobRole[], assignments: Assignment[]): Set<string> {
  const mine = new Set(assignments.filter((a) => a.user_id === userId).map((a) => a.talent_id));
  return new Set(roles.filter((r) => mine.has(r.id)).flatMap((r) => r.skills));
}
/** Published job roles that list this skill (library id or slug): what a person can ask for. */
export const rolesCovering = (roles: JobRole[], keys: string[]) => roles.filter((r) => keys.some((k) => r.skills.includes(k)));

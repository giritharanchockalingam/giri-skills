/* The audit log for people: who (an email or a key name, not a UUID), what it touched (a skill title, a version,
 * a run with its link), and details with ids and hashes shortened (the full value stays in the tooltip). Pure. */
export interface AuditIn { actor_kind: string; actor_id: string | null; entity_type: string; entity_id: string | null; details: Record<string, unknown> | null }
export interface AuditLookups { me: string; users: Map<string, string>; keys: Map<string, string>; skills: Map<string, string>; versions: Map<string, string> }
export interface Cell { text: string; title?: string; href?: string }

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const HASH = /^[0-9a-f]{32,}$/i;
export const shortValue = (v: string): Cell => (UUID.test(v) || HASH.test(v) ? { text: v.slice(0, 8), title: v } : v.length > 60 ? { text: `${v.slice(0, 57)}…`, title: v } : { text: v });

export function auditActor(a: AuditIn, l: AuditLookups): Cell {
  if (!a.actor_id) return { text: a.actor_kind === "system" ? "system" : "—" };
  if (a.actor_kind === "api_key") return { text: `key ${l.keys.get(a.actor_id) ?? a.actor_id.slice(0, 8)}`, title: a.actor_id };
  if (a.actor_id === l.me) return { text: "you", title: l.users.get(a.actor_id) };
  return { text: l.users.get(a.actor_id) ?? `member ${a.actor_id.slice(0, 8)}`, title: a.actor_id };
}

export function auditEntity(a: AuditIn, l: AuditLookups): Cell {
  const id = a.entity_id ?? "";
  const t = a.entity_type.replace(/_/g, " ");
  if (!id) return { text: t };
  if (a.entity_type === "skill") return { text: `skill ${l.skills.get(id) ?? id}`, title: id };
  if (a.entity_type === "version") return { text: l.versions.get(id) ?? `version ${id.slice(0, 8)}`, title: id };
  if (a.entity_type === "run") return { text: `run ${id.slice(0, 8)}`, title: id, href: `/runs/${id}` };
  if (a.entity_type === "api_key") return { text: `key ${l.keys.get(id) ?? id.slice(0, 8)}`, title: id };
  if (a.entity_type === "workspace") return { text: "workspace" };
  const s = shortValue(id);
  return { text: `${t} ${s.text}`, title: s.title };
}

export function auditDetails(a: AuditIn, l: AuditLookups): { key: string; cell: Cell }[] {
  return Object.entries(a.details ?? {}).filter(([, v]) => v != null && v !== "" && typeof v !== "object").slice(0, 4).map(([k, v]) => {
    const s = String(v);
    const named = UUID.test(s) ? l.users.get(s) ?? l.skills.get(s) ?? l.versions.get(s) ?? l.keys.get(s) : undefined;
    return { key: k.replace(/_/g, " "), cell: named ? { text: named, title: s } : shortValue(s) };
  });
}

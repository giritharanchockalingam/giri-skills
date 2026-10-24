/* Reconcile (spec §6.3): the factory's published/retired skills versus Port's copy, one line per difference with the
 * reason. Counts are read, never assumed; a difference is reported as what it is (pending, failed, hash drift, edited in
 * Port, missing, unknown-in-factory). This is the WP1 acceptance check and the data behind Integrations → Port. */
import type { SupabaseClient } from "@supabase/supabase-js";
import { PortClient, portConfig } from "./client";
import { BLUEPRINT_ID, portId } from "./map";
import { MAX_ATTEMPTS } from "./outbox";

export type Mismatch = { slug: string; reason: "sync-pending" | "sync-failed" | "dead-lettered" | "missing-in-port" | "hash-drift" | "status-drift" | "edited-in-port" | "unknown-in-factory"; detail: string };
export interface ReconcileReport {
  checkedAt: string; configured: boolean; error?: string;
  factory: { published: number; retired: number };
  port: { published: number; retired: number; total: number; truncated: boolean };
  outbox: { pending: number; failing: number; deadLettered: number };
  matched: number;
  mismatches: Mismatch[];
}

type FactoryRow = { id: string; slug: string; status: "published" | "retired"; version: number; manifest_hash: string };

/** `sb` may be a session client (members read their workspace) or the service role; Port is read with the server's credentials. */
export async function reconcilePort(sb: SupabaseClient, workspaceId: string, f: typeof fetch = fetch, now: Date = new Date()): Promise<ReconcileReport> {
  const report: ReconcileReport = { checkedAt: now.toISOString(), configured: true, factory: { published: 0, retired: 0 }, port: { published: 0, retired: 0, total: 0, truncated: false }, outbox: { pending: 0, failing: 0, deadLettered: 0 }, matched: 0, mismatches: [] };
  const cfg = portConfig(process.env);
  if (!cfg.ok) { report.configured = false; report.error = `Port is not configured: set ${cfg.missing.join(" and ")}`; return report; }

  // factory truth: each published/retired skill at the version Port should hold
  const { data: skills, error } = await sb.from("sf_skills").select("id, slug, status").eq("workspace_id", workspaceId).in("status", ["published", "retired"]);
  if (error) { report.error = error.message; return report; }
  const ids = (skills ?? []).map((s) => s.id);
  const { data: versions } = ids.length ? await sb.from("sf_skill_versions").select("skill_id, version, status, manifest_hash").in("skill_id", ids) : { data: [] };
  const factory: FactoryRow[] = [];
  for (const s of skills ?? []) {
    const vs = ((versions ?? []) as { skill_id: string; version: number; status: string; manifest_hash: string }[]).filter((v) => v.skill_id === s.id);
    const live = s.status === "published" ? vs.find((v) => v.status === "published") : vs.filter((v) => v.status === "retired").sort((a, b) => b.version - a.version)[0];
    if (live) factory.push({ id: s.id, slug: s.slug, status: s.status as FactoryRow["status"], version: live.version, manifest_hash: live.manifest_hash });
  }
  report.factory.published = factory.filter((r) => r.status === "published").length;
  report.factory.retired = factory.filter((r) => r.status === "retired").length;

  // outbox state per skill
  const { data: outbox } = await sb.from("sf_port_outbox").select("skill_slug, attempts, last_error, processed_at").eq("workspace_id", workspaceId).is("processed_at", null);
  const pendingBySlug = new Map<string, { attempts: number; last_error: string | null }>();
  for (const o of (outbox ?? []) as { skill_slug: string; attempts: number; last_error: string | null }[]) {
    const prev = pendingBySlug.get(o.skill_slug);
    if (!prev || o.attempts > prev.attempts) pendingBySlug.set(o.skill_slug, { attempts: o.attempts, last_error: o.last_error });
  }
  for (const p of pendingBySlug.values()) { if (p.attempts >= MAX_ATTEMPTS) report.outbox.deadLettered++; else if (p.attempts > 0) report.outbox.failing++; else report.outbox.pending++; }

  // Port's copy
  const port = new PortClient(cfg, f);
  let entities: Record<string, unknown>[];
  try { const r = await port.listEntities(BLUEPRINT_ID); entities = r.entities; report.port.truncated = r.truncated; } catch (e) { report.error = (e as Error).message; return report; }
  const inPort = new Map<string, Record<string, unknown>>();
  for (const e of entities) {
    const props = (e.properties ?? {}) as Record<string, unknown>;
    inPort.set(String(e.identifier), props);
    if (props.sf_status === "retired") report.port.retired++; else if (props.sf_status === "published") report.port.published++;
  }
  report.port.total = entities.length;

  const { data: links } = await sb.from("sf_port_links").select("skill_id, last_synced_hash, last_synced_status, last_synced_version").eq("workspace_id", workspaceId);
  const linkOf = new Map(((links ?? []) as { skill_id: string; last_synced_hash: string | null; last_synced_status: string | null; last_synced_version: number | null }[]).map((l) => [l.skill_id, l]));

  const seen = new Set<string>();
  for (const r of factory) {
    const id = portId(r.slug);
    seen.add(id);
    const props = inPort.get(id);
    const pend = pendingBySlug.get(r.slug);
    if (!props) {
      report.mismatches.push({ slug: r.slug, reason: pend ? (pend.attempts >= MAX_ATTEMPTS ? "dead-lettered" : pend.attempts > 0 ? "sync-failed" : "sync-pending") : "missing-in-port", detail: pend?.last_error ?? "no entity in Port" });
      continue;
    }
    if (props.sf_content_hash !== r.manifest_hash) {
      const reason: Mismatch["reason"] = pend ? (pend.attempts >= MAX_ATTEMPTS ? "dead-lettered" : pend.attempts > 0 ? "sync-failed" : "sync-pending") : "hash-drift";
      report.mismatches.push({ slug: r.slug, reason, detail: `factory v${r.version} ${r.manifest_hash.slice(0, 12)}… vs Port ${String(props.sf_content_hash ?? "—").slice(0, 12)}…${pend?.last_error ? ` — ${pend.last_error}` : ""}` });
      continue;
    }
    if (props.sf_status !== r.status) {
      report.mismatches.push({ slug: r.slug, reason: pend ? "sync-pending" : "status-drift", detail: `factory ${r.status} vs Port ${String(props.sf_status ?? "—")}` });
      continue;
    }
    // same hash and status: did someone edit a factory-owned property in Port? (spec §6.4 — flagged, overwritten on next sync)
    const link = linkOf.get(r.id);
    const edited = editedInPort(props, { version: String(r.version), slug: r.slug, status: r.status });
    if (edited.length) { report.mismatches.push({ slug: r.slug, reason: "edited-in-port", detail: `${edited.join(", ")} differ from the factory — will be overwritten on next sync` }); continue; }
    if (link && link.last_synced_hash && link.last_synced_hash !== r.manifest_hash) { report.mismatches.push({ slug: r.slug, reason: "sync-pending", detail: "Port matches but the link record is behind; next sync refreshes it" }); continue; }
    report.matched++;
  }
  for (const id of inPort.keys()) if (!seen.has(id)) report.mismatches.push({ slug: id, reason: "unknown-in-factory", detail: "entity in Port has no published or retired skill behind it" });
  return report;
}

/** sf_ properties whose value Port holds differently from what the factory would sync for this exact version. Only the
 *  properties that are a pure function of (slug, version, status) can be checked without the full load; the hash was
 *  already compared. */
function editedInPort(props: Record<string, unknown>, want: { version: string; slug: string; status: string }): string[] {
  const out: string[] = [];
  if (props.sf_version !== undefined && props.sf_version !== want.version) out.push("sf_version");
  if (props.sf_skill_slug !== undefined && props.sf_skill_slug !== want.slug) out.push("sf_skill_slug");
  if (props.sf_status !== undefined && props.sf_status !== want.status) out.push("sf_status");
  if (want.status === "retired" && props.sf_mcp_tool) out.push("sf_mcp_tool");
  return out;
}

export function reconcileText(r: ReconcileReport): string {
  const lines = [`Port reconcile @ ${r.checkedAt}`];
  if (!r.configured || r.error) { lines.push(`ERROR: ${r.error ?? "not configured"}`); return lines.join("\n"); }
  lines.push(`factory: published=${r.factory.published} retired=${r.factory.retired}`, `port:    published=${r.port.published} retired=${r.port.retired} total=${r.port.total}${r.port.truncated ? " (truncated)" : ""}`, `outbox:  pending=${r.outbox.pending} failing=${r.outbox.failing} dead-lettered=${r.outbox.deadLettered}`, `matched (hash+status): ${r.matched} of ${r.factory.published + r.factory.retired}`, `published-in-factory == published-in-port: ${r.factory.published === r.port.published ? "YES" : "NO"}`, `hash match on all: ${r.mismatches.length === 0 ? "YES" : "NO"}`);
  for (const m of r.mismatches) lines.push(`  - ${m.slug}: ${m.reason} — ${m.detail}`);
  return lines.join("\n");
}

/* Sync one provider into the catalog: upsert its entities, mark the ones it no longer reports archived (never deleted),
 * replace the relations it asserts, log the sync with counts or the error. Runs as the signed-in author/admin (RLS). */
import type { SupabaseClient } from "@supabase/supabase-js";
import { mapVercel, mapSupabase, type EntityRow, type RelationSpec } from "./map";
import { readVercel, readSupabase, vercelConfig, supabaseConfig } from "./fetch";
import { PortClient, portConfig } from "./port/client";
import { mapPortCatalog, skipBlueprint, type ComponentRow, type PortBlueprint, type PortEntity, type PortRelation } from "./port/catalog";

/** Port: read every non-system blueprint's entities and land them as components; Port's relations become catalog
 *  relations ("related"), attached to existing entries where Port describes the same thing (a scanned repository). */
async function syncPort(sb: SupabaseClient, ws: string) {
  const c = portConfig(process.env);
  if (!c.ok) throw new Error(`not configured: set ${c.missing.join(", ")} in the deployment`);
  const port = new PortClient(c);
  const blueprints = (await port.listBlueprints()) as unknown as PortBlueprint[];
  const entities = new Map<string, PortEntity[]>();
  const problems: string[] = [];
  for (const b of blueprints.filter((x) => x.identifier && !skipBlueprint(x.identifier))) {
    try {
      const r = await port.listEntities(b.identifier);
      entities.set(b.identifier, r.entities as unknown as PortEntity[]);
      if (r.truncated) problems.push(`${b.title ?? b.identifier}: more than 2,000 entities; the rest were not read`);
    } catch (e) { problems.push((e as Error).message); }
  }
  const { data: repos } = await sb.from("sf_catalog_entities").select("key").eq("workspace_id", ws).eq("kind", "repository").eq("archived", false);
  const mapped = mapPortCatalog({ blueprints, entities, nativeRepoKeys: new Set(((repos ?? []) as { key: string }[]).map((r) => r.key.toLowerCase())), fallbackUrl: process.env.PORT_APP_URL?.trim() || "https://app.port.io" });
  await upsertEntities(sb, ws, "component", "port", mapped.components);
  const rel = await replacePortRelations(sb, ws, mapped.relations);
  return { types: entities.size, components: mapped.components.length, aliases: mapped.aliases, relations: rel.written, unresolved: rel.unresolved, problems };
}

async function replacePortRelations(sb: SupabaseClient, ws: string, specs: PortRelation[]): Promise<{ written: number; unresolved: number }> {
  const { data } = await sb.from("sf_catalog_entities").select("id, kind, key").eq("workspace_id", ws).eq("archived", false);
  const id = new Map(((data ?? []) as { id: string; kind: string; key: string }[]).map((e) => [`${e.kind}:${e.key.toLowerCase()}`, e.id]));
  await sb.from("sf_catalog_relations").delete().eq("workspace_id", ws).eq("source", "port");
  const seen = new Set<string>();
  let unresolved = 0;
  const rows = specs.flatMap((s) => {
    const from = id.get(`${s.from.kind}:${s.from.key.toLowerCase()}`), to = id.get(`${s.to.kind}:${s.to.key.toLowerCase()}`);
    if (!from || !to || from === to) { unresolved++; return []; }
    const k = `${from}>${to}`;
    if (seen.has(k)) return [];
    seen.add(k);
    return [{ workspace_id: ws, from_id: from, to_id: to, type: "related", evidence: s.evidence.slice(0, 500), source: "port" }];
  });
  for (let i = 0; i < rows.length; i += 500) { const { error } = await sb.from("sf_catalog_relations").insert(rows.slice(i, i + 500)); if (error) throw new Error(error.message); }
  return { written: rows.length, unresolved };
}

export type Provider = "vercel" | "supabase" | "port";
export interface IntegrationSync { ok: boolean; message: string; entities: number; relations: number; problems: string[] }

async function upsertEntities(sb: SupabaseClient, ws: string, kind: "service" | "database" | "component", source: Provider, rows: (EntityRow | ComponentRow)[]) {
  const now = new Date().toISOString();
  if (rows.length) {
    const { error } = await sb.from("sf_catalog_entities").upsert(rows.map((r) => ({ workspace_id: ws, installation_id: null, synced_at: now, ...r })), { onConflict: "workspace_id,kind,key" });
    if (error) throw new Error(error.message);
  }
  const keep = new Set(rows.map((r) => r.key));
  const { data: existing } = await sb.from("sf_catalog_entities").select("id, key, properties").eq("workspace_id", ws).eq("kind", kind).eq("source", source).eq("archived", false);
  for (const g of (existing ?? []).filter((e) => !keep.has(e.key)))
    await sb.from("sf_catalog_entities").update({ archived: true, properties: { ...(g.properties as object), gone_from_provider_at: now } }).eq("id", g.id);
}

/** Resolve relation ends by (kind, key) and replace this provider's relations from the given services. */
async function replaceRelations(sb: SupabaseClient, ws: string, source: Provider, specs: RelationSpec[]): Promise<{ written: number; unresolved: string[] }> {
  const { data } = await sb.from("sf_catalog_entities").select("id, kind, key").eq("workspace_id", ws).eq("archived", false);
  const id = new Map(((data ?? []) as { id: string; kind: string; key: string }[]).map((e) => [`${e.kind}:${e.key.toLowerCase()}`, e.id]));
  const { data: all } = await sb.from("sf_catalog_entities").select("id").eq("workspace_id", ws).eq("kind", "service").eq("source", source);
  const ids = ((all ?? []) as { id: string }[]).map((x) => x.id);
  if (ids.length) await sb.from("sf_catalog_relations").delete().eq("workspace_id", ws).eq("source", source).in("from_id", ids);
  const unresolved: string[] = [];
  const rows = specs.flatMap((s) => {
    const from = id.get(`service:${s.from.key.toLowerCase()}`), to = id.get(`${s.to.kind}:${s.to.key.toLowerCase()}`);
    if (!from || !to) { unresolved.push(`${s.from.key} → ${s.to.key} (${s.to.kind} not in the catalog)`); return []; }
    return [{ workspace_id: ws, from_id: from, to_id: to, type: s.type, evidence: s.evidence.slice(0, 500), source }];
  });
  if (rows.length) { const { error } = await sb.from("sf_catalog_relations").insert(rows); if (error) throw new Error(error.message); }
  return { written: rows.length, unresolved };
}

export async function syncProvider(sb: SupabaseClient, ws: string, userId: string, provider: Provider): Promise<IntegrationSync> {
  const { data: log } = await sb.from("sf_catalog_syncs").insert({ workspace_id: ws, provider, started_by: userId }).select("id").single();
  const finish = (patch: Record<string, unknown>) => log ? sb.from("sf_catalog_syncs").update({ ...patch, finished_at: new Date().toISOString() }).eq("id", log.id) : Promise.resolve();
  try {
    if (provider === "vercel") {
      const c = vercelConfig();
      if (!c.ok) throw new Error(`not configured: set ${c.missing.join(", ")} in the deployment`);
      const v = await readVercel(c);
      const { entities, relations } = mapVercel(v.team, v.projects, v.deploys, v.envs);
      await upsertEntities(sb, ws, "service", "vercel", entities);
      const rel = await replaceRelations(sb, ws, "vercel", relations);
      const problems = [...v.problems, ...rel.unresolved.map((u) => `relation skipped: ${u}`), ...(v.truncated ? ["more than 1,000 projects: the rest were not read"] : [])];
      await finish({ status: "succeeded", counts: { services: entities.length, relations: rel.written, skipped: rel.unresolved.length, problems: v.problems.length } });
      return { ok: true, message: `${entities.length} services, ${rel.written} relations${rel.unresolved.length ? ` (${rel.unresolved.length} skipped: other end not in the catalog)` : ""}.`, entities: entities.length, relations: rel.written, problems };
    }
    if (provider === "port") {
      const r = await syncPort(sb, ws);
      await finish({ status: "succeeded", counts: { types: r.types, components: r.components, aliases: r.aliases, relations: r.relations } });
      return { ok: true, message: `${r.components} components from ${r.types} types, ${r.relations} relations${r.aliases ? `; ${r.aliases} matched entries already in the catalog` : ""}.`, entities: r.components, relations: r.relations, problems: r.problems };
    }
    const c = supabaseConfig();
    if (!c.ok) throw new Error(`not configured: set ${c.missing.join(", ")} in the deployment`);
    const dbs = mapSupabase(await readSupabase(c));
    await upsertEntities(sb, ws, "database", "supabase", dbs);
    await finish({ status: "succeeded", counts: { databases: dbs.length } });
    return { ok: true, message: `${dbs.length} databases.`, entities: dbs.length, relations: 0, problems: [] };
  } catch (e) {
    const msg = (e as Error).message;
    await finish({ status: "failed", error: msg.slice(0, 1000) });
    return { ok: false, message: msg, entities: 0, relations: 0, problems: [] };
  }
}

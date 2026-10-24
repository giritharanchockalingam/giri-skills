/* port-sync worker (spec §5.1): drains sf_port_outbox with the service-role client. State-based, not event-based —
 * each row is a ping that a skill's release state changed; the worker reads the skill's *current* state and upserts
 * it, so replays and reordering are safe. Failures back off (2^attempts minutes, 5 attempts) and are kept with the
 * error text; after the 5th they are dead-lettered and surface on Integrations → Port. Nothing is dropped silently
 * and nothing is faked: a row only becomes processed after Port acknowledged the upsert. */
import type { SupabaseClient } from "@supabase/supabase-js";
import { PortClient, portConfig } from "./client";
import { BLUEPRINT_ID, skillEntity } from "./map";
import { ensureSkillBlueprint, loadSkillsForPort } from "./sync";

export const MAX_ATTEMPTS = 5;
export const backoffMs = (attempt: number) => Math.min(2 ** attempt, 64) * 60_000;

export interface OutboxRow { id: string; workspace_id: string; skill_id: string; skill_slug: string; event_type: "publish" | "retire"; payload: Record<string, unknown>; attempts: number; last_error: string | null; next_attempt_at: string; processed_at: string | null; created_at: string }
export interface DrainResult { configured: boolean; picked: number; synced: number; failed: number; deadLettered: number; problems: string[] }

/** `registryRepo` is `<owner>/<repo>` of the repository Port's Skills registry scanned (the factory's own library). */
export async function drainPortOutbox(admin: SupabaseClient, opts: { portalBase: string; limit?: number; f?: typeof fetch; now?: Date; registryRepo?: string | null }): Promise<DrainResult> {
  const now = opts.now ?? new Date();
  const out: DrainResult = { configured: true, picked: 0, synced: 0, failed: 0, deadLettered: 0, problems: [] };
  const cfg = portConfig(process.env);
  if (!cfg.ok) { out.configured = false; out.problems.push(`Port is not configured: set ${cfg.missing.join(" and ")}`); return out; }
  const { data, error } = await admin.from("sf_port_outbox").select("*").is("processed_at", null).lt("attempts", MAX_ATTEMPTS).lte("next_attempt_at", now.toISOString()).order("created_at").limit(opts.limit ?? 50);
  if (error) { out.problems.push(error.message); return out; }
  const rows = (data ?? []) as OutboxRow[];
  out.picked = rows.length;
  if (!rows.length) return out;

  const port = new PortClient(cfg, opts.f);
  try { await ensureSkillBlueprint(port); } catch (e) {
    // the blueprint is a precondition for every row: record the failure on each and stop
    for (const r of rows) await markFailed(admin, r, (e as Error).message, now, out);
    return out;
  }

  // one upsert per skill per workspace, newest state wins; every row for that skill is settled together
  const byWorkspace = new Map<string, OutboxRow[]>();
  for (const r of rows) byWorkspace.set(r.workspace_id, [...(byWorkspace.get(r.workspace_id) ?? []), r]);
  for (const [ws, wsRows] of byWorkspace) {
    const owners = await ownerEmails(admin, ws);
    const slugs = [...new Set(wsRows.map((r) => r.skill_slug))];
    const loaded = await loadSkillsForPort(admin, ws, { slugs, owners, registryRepo: opts.registryRepo });
    if (loaded.error) { for (const r of wsRows) await markFailed(admin, r, loaded.error, now, out); continue; }
    const bySlug = new Map(loaded.rows.map((r) => [r.slug, r]));
    for (const slug of slugs) {
      const group = wsRows.filter((r) => r.skill_slug === slug);
      const skill = bySlug.get(slug);
      if (!skill) { for (const r of group) await markFailed(admin, r, "skill is neither published nor retired any more (drafts do not sync)", now, out); continue; }
      const entity = skillEntity(skill, opts.portalBase, now.toISOString());
      try {
        await port.upsertEntity(BLUEPRINT_ID, entity);
        const { error: linkErr } = await admin.from("sf_port_links").upsert({ workspace_id: ws, skill_id: group[0].skill_id, port_blueprint: BLUEPRINT_ID, port_entity_id: entity.identifier, last_synced_hash: skill.manifest_hash, last_synced_version: skill.version, last_synced_status: skill.status ?? "published", last_synced_at: now.toISOString(), last_error: null }, { onConflict: "workspace_id,skill_id" });
        if (linkErr) throw new Error(`sf_port_links: ${linkErr.message}`);
        const { error: doneErr } = await admin.from("sf_port_outbox").update({ processed_at: now.toISOString(), last_error: null }).in("id", group.map((r) => r.id));
        if (doneErr) throw new Error(`sf_port_outbox: ${doneErr.message}`);
        out.synced += group.length;
      } catch (e) {
        for (const r of group) await markFailed(admin, r, (e as Error).message, now, out);
        await admin.from("sf_port_links").upsert({ workspace_id: ws, skill_id: group[0].skill_id, port_blueprint: BLUEPRINT_ID, port_entity_id: entity.identifier, last_error: (e as Error).message }, { onConflict: "workspace_id,skill_id" });
      }
    }
  }
  return out;
}

async function markFailed(admin: SupabaseClient, r: OutboxRow, message: string, now: Date, out: DrainResult) {
  const attempts = r.attempts + 1;
  const dead = attempts >= MAX_ATTEMPTS;
  await admin.from("sf_port_outbox").update({ attempts, last_error: message.slice(0, 1000), next_attempt_at: new Date(now.getTime() + backoffMs(attempts)).toISOString() }).eq("id", r.id);
  out.failed++;
  if (dead) out.deadLettered++;
  out.problems.push(`${r.skill_slug} (${r.event_type}, attempt ${attempts}${dead ? ", dead-lettered" : ""}): ${message}`);
}

async function ownerEmails(admin: SupabaseClient, ws: string): Promise<Map<string, string>> {
  const { data } = await admin.rpc("sf_port_skill_owners", { p_workspace: ws });
  return new Map(((data ?? []) as { skill_id: string; email: string }[]).map((o) => [o.skill_id, o.email]));
}

/** Dead-lettered rows (attempts exhausted, never processed) — what Integrations → Port lists as "needs attention". */
export async function deadLetters(sb: SupabaseClient, workspaceId: string): Promise<OutboxRow[]> {
  const { data } = await sb.from("sf_port_outbox").select("*").eq("workspace_id", workspaceId).is("processed_at", null).gte("attempts", MAX_ATTEMPTS).order("created_at", { ascending: false }).limit(100);
  return (data ?? []) as OutboxRow[];
}

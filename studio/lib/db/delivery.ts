/* Data access for delivery metrics: the latest snapshot per repository (RLS-scoped). */
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Delivery } from "@/lib/insights/delivery";

export interface DeliveryRow { entity_id: string; key: string; computed_at: string; notes: string[]; d30: Delivery; d90: Delivery }

export async function loadDelivery(sb: SupabaseClient, ws: string, entityId?: string): Promise<DeliveryRow[]> {
  let q = sb.from("sf_delivery_latest").select("entity_id, computed_at, notes, metrics").eq("workspace_id", ws);
  if (entityId) q = q.eq("entity_id", entityId);
  const [{ data }, { data: ents }] = await Promise.all([q, sb.from("sf_catalog_entities").select("id, key, archived").eq("workspace_id", ws).eq("kind", "repository")]);
  const key = new Map(((ents ?? []) as { id: string; key: string; archived: boolean }[]).filter((e) => !e.archived).map((e) => [e.id, e.key]));
  return ((data ?? []) as { entity_id: string; computed_at: string; notes: string[]; metrics: { d30: Delivery; d90: Delivery } }[])
    .filter((r) => key.has(r.entity_id))
    .map((r) => ({ entity_id: r.entity_id, key: key.get(r.entity_id)!, computed_at: r.computed_at, notes: r.notes ?? [], d30: r.metrics.d30, d90: r.metrics.d90 }))
    .sort((a, b) => a.key.localeCompare(b.key));
}

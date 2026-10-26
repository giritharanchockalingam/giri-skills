// fictional fixture — order service: named columns, paginated reads, batched lookups (perf-review-runner evals)
import { createClient } from "@/lib/supabase/server";

export type Order = { id: string; status: string; total: number };

export async function listOrders({ page }: { page: number }): Promise<Order[]> {
  const supabase = createClient();
  const { data } = await supabase
    .from("orders")
    .select("id, status, total")
    .order("created_at", { ascending: false })
    .range(page * 50, page * 50 + 49);
  return data ?? [];
}

export async function getOrder(id: string): Promise<Order | null> {
  const supabase = createClient();
  const { data } = await supabase.from("orders").select("id, status, total").eq("id", id).single();
  return data;
}

export async function getOrderStats(): Promise<{ count: number }> {
  const supabase = createClient();
  const { count } = await supabase.from("orders").select("id", { count: "exact", head: true });
  return { count: count ?? 0 };
}

export async function getItemsForOrders(orderIds: string[]) {
  const supabase = createClient();
  const { data } = await supabase.from("order_items").select("order_id, sku, qty").in("order_id", orderIds).limit(1000);
  return data ?? [];
}

export async function notifyAll(orderIds: string[], send: (id: string) => Promise<void>) {
  await Promise.all(orderIds.map((id) => send(id)));
}

// fictional fixture — order service with sequential awaits and an unbounded select * (perf-review-runner evals)
import { createClient } from "@/lib/supabase/server";

export async function listAllOrders() {
  const supabase = createClient();
  const { data } = await supabase.from("orders").select("*").order("created_at");
  return data ?? [];
}

export async function notifyAll(orderIds: string[], send: (id: string) => Promise<void>) {
  for (const id of orderIds) {
    await send(id);
  }
}

export async function totalsByCustomer(customerIds: string[]) {
  const supabase = createClient();
  return Promise.all(
    customerIds.map(async (id) => {
      const { data } = await supabase.from("orders").select("total").eq("customer_id", id).limit(500);
      return { id, total: (data ?? []).reduce((s, o) => s + o.total, 0) };
    }),
  );
}

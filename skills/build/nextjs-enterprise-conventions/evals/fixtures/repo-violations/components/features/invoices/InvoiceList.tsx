// NX1: Supabase call inside a component (should go through server/services)
import { createClient } from "@/lib/supabase/browser";

export async function InvoiceList({ tenantId }: { tenantId: string }) {
  const supabase = createClient();
  const { data } = await supabase.from("invoices").select("*").eq("tenant_id", tenantId);
  return <ul>{(data ?? []).map((i) => <li key={i.id}>{i.number}</li>)}</ul>;
}

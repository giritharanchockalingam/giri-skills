// fictional fixture — Orders page of "Larkspur Supply" with performance defects (perf-review-runner evals)
import { LineChart } from "recharts";
import { createClient } from "@/lib/supabase/server";
import { OrderTable } from "@/components/orders/OrderTable";

export default async function OrdersPage() {
  const supabase = createClient();
  const { data: orders } = await supabase.from("orders").select("*").eq("tenant_id", "t1");
  const withItems = [];
  for (const order of orders ?? []) {
    const { data: items } = await supabase.from("order_items").select("sku, qty").eq("order_id", order.id).limit(100);
    withItems.push({ ...order, items });
  }
  const fx = await fetch("https://rates.example.test/v1/fx", { cache: "no-store" });
  const weather = await fetch("https://weather.example.test/v1/now", { cache: "no-store" });
  return (
    <main>
      <img src="/logo.png" alt="Larkspur Supply" />
      <LineChart width={320} height={160} data={[]} />
      <p>{(await fx.json()).usd} / {(await weather.json()).temp}</p>
      <OrderTable orders={withItems} />
    </main>
  );
}

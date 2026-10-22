// fictional fixture — Orders page of "Larkspur Supply" (perf-review-runner evals); server component
import Image from "next/image";
import { listOrders, getOrderStats } from "@/server/services/order-service";
import { OrderTable } from "@/components/orders/OrderTable";

export default async function OrdersPage() {
  const [orders, stats] = await Promise.all([listOrders({ page: 0 }), getOrderStats()]);
  const rates = await fetch("https://rates.example.test/v1/fx", { next: { revalidate: 300 } });
  const fx = await rates.json();
  return (
    <main>
      <Image src="/logo.png" alt="Larkspur Supply" width={120} height={32} />
      <p>{stats.count} orders · FX {fx.usd}</p>
      <OrderTable orders={orders} />
    </main>
  );
}

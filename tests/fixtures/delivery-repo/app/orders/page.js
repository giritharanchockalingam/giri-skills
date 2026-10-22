import { listOrders } from "@/lib/orders";
import { OrderTable } from "@/components/OrderTable";

export default async function OrdersPage() {
  const orders = await listOrders({ limit: 50 });
  return (
    <main>
      <h1>Orders</h1>
      <OrderTable orders={orders} />
    </main>
  );
}

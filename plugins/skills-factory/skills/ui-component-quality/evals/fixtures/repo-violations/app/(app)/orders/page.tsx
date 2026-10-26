// Fictional fixture (ui-component-quality evals): server page; the help card is mouse-only.
import { listOrders } from "@/server/services/order-service";
import { OrderTable } from "@/components/features/orders/OrderTable";

export default async function OrdersPage() {
  const orders = await listOrders();
  return (
    <main className="p-4">
      <span onClick={() => console.info("open help")}>Need help with orders?</span>
      <OrderTable orders={orders} isLoading={false} onDelete={() => undefined} onOpen={() => undefined} />
    </main>
  );
}

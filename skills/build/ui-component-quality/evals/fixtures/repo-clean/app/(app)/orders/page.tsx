// Fictional fixture (ui-component-quality evals): server page that passes data down; one keyboard-accessible card.
import Image from "next/image";
import Link from "next/link";
import { listOrders } from "@/server/services/order-service";
import { OrderTable } from "@/components/features/orders/OrderTable";

export default async function OrdersPage() {
  const orders = await listOrders();
  return (
    <main className="w-full max-w-full p-4">
      <Image src="/logo.svg" alt="Northwind Supply" width={120} height={32} />
      <div
        role="button"
        tabIndex={0}
        onClick={() => console.info("open help")}
        onKeyDown={(e) => e.key === "Enter" && console.info("open help")}
      >
        Need help with orders?
      </div>
      <Link href="/orders/new">New order</Link>
      <OrderTable orders={orders} isLoading={false} onDelete={() => undefined} />
    </main>
  );
}

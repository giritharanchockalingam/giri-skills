// Fictional fixture (ui-component-quality evals): async detail view with loading, error and empty states.
"use client"; // reason: client-side query with cache

import { useQuery } from "@tanstack/react-query";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchOrder } from "@/lib/api/orders";

export function OrderDetail({ orderId }: { orderId: string }) {
  const { data, isLoading, error } = useQuery({ queryKey: ["order", orderId], queryFn: () => fetchOrder(orderId) });

  if (isLoading) return <Skeleton className="h-24 w-full" />;
  if (error) return <p role="alert">Could not load order {orderId}.</p>;
  if (!data || data.lines.length === 0) return <p>This order has no lines.</p>;

  return (
    <article className="max-w-full">
      <h2>Order {data.number}</h2>
      <ul>
        {data.lines.map((line) => (
          <li key={line.sku} className="line">{line.sku} × {line.qty}</li>
        ))}
      </ul>
    </article>
  );
}

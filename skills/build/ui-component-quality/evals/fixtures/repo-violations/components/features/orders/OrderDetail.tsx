// Fictional fixture (ui-component-quality evals): async detail view that renders nothing while loading and injects HTML.
"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchOrder } from "@/lib/api/orders";

export function OrderDetail({ orderId }: { orderId: string }) {
  const { data } = useQuery({ queryKey: ["order", orderId], queryFn: () => fetchOrder(orderId) });
  return (
    <article style={{ width: 800 }}>
      <h2>Order {data?.number}</h2>
      <div dangerouslySetInnerHTML={{ __html: data?.notesHtml ?? "" }} />
    </article>
  );
}

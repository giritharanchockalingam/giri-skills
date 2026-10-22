// Fictional fixture (ui-component-quality evals): a compliant order table for "Northwind Supply", a made-up B2B shop.
"use client"; // reason: row selection and the search box are interactive

import { useState } from "react";
import { IconButton } from "@/components/ui/IconButton";
import { TrashIcon } from "@/components/ui/icons";
import type { Order } from "@/lib/types/order";

type OrderTableProps = {
  orders: Order[];
  isLoading: boolean;
  onDelete: (id: string) => void;
};

export function OrderTable({ orders, isLoading, onDelete }: OrderTableProps) {
  const [query, setQuery] = useState("");

  if (isLoading) {
    return <div role="status" aria-busy="true">Loading orders…</div>;
  }
  if (orders.length === 0) {
    return <p className="text-muted">No orders yet. Create the first one from the Orders menu.</p>;
  }
  return (
    <section className="w-full lg:w-[960px]">
      <label htmlFor="order-search">Search orders</label>
      <input id="order-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} />
      <table className="w-full">
        <tbody>
          {orders.map((order) => (
            <tr key={order.id} className="row">
              <td>{order.number}</td>
              <td className={order.paid ? "text-green-700" : "text-red-700"}>
                {order.paid ? "Paid" : "Overdue"}
              </td>
              <td>
                <IconButton label={`Delete order ${order.number}`} onClick={() => onDelete(order.id)}>
                  <TrashIcon />
                </IconButton>
                <button type="button" aria-label={`Archive order ${order.number}`}>
                  <TrashIcon />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

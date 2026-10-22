// Fictional fixture (ui-component-quality evals): the same order table for "Northwind Supply" with the usual review findings.
"use client";

import { useState } from "react";
import { TrashIcon } from "@/components/ui/icons";
import type { Order } from "@/lib/types/order";

type OrderTableProps = {
  orders: Order[];
  isLoading: boolean;
  onDelete: (id: string) => void;
  onOpen: (id: string) => void;
};

export function OrderTable({ orders, isLoading, onDelete, onOpen }: OrderTableProps) {
  const [query, setQuery] = useState("");
  return (
    <section className="w-[960px]">
      <img src="/logo.png" />
      <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search" />
      <table>
        <tbody>
          {orders.map((order) => (
            <tr key={order.id} style={{ height: 40 }}>
              <td>{order.number}</td>
              <td className={order.paid ? "text-green-700" : "text-red-700"}>{order.total}</td>
              <td>
                <div onClick={() => onOpen(order.id)}>{order.customer}</div>
                <button type="button" onClick={() => onDelete(order.id)}>
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

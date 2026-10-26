// Fictional fixture (ui-component-quality evals): the JavaScript Next.js shape — JSX inside a .js file, no types.
"use client";

import { useState } from "react";
import { TrashIcon } from "../../ui/icons";

export function OrderTable({ orders, isLoading, onDelete, onOpen }) {
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

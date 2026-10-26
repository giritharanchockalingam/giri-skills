"use client";
// fictional fixture — client table: derived rows memoised, no fetching (perf-review-runner evals)
import { useMemo, useState } from "react";
import type { Order } from "@/server/services/order-service";

export function OrderTable({ orders }: { orders: Order[] }) {
  const [query, setQuery] = useState("");
  const rows = useMemo(
    () => orders.filter((o) => o.status.includes(query)).sort((a, b) => b.total - a.total),
    [orders, query],
  );
  return (
    <div>
      <input value={query} onChange={(e) => setQuery(e.target.value)} />
      <ul>{rows.map((o) => <li key={o.id}>{o.id} — {o.total}</li>)}</ul>
    </div>
  );
}

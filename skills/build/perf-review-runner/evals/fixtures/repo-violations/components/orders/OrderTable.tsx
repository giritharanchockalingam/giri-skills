"use client";
// fictional fixture — client table that fetches after mount and re-sorts on every render (perf-review-runner evals)
import { useEffect, useState } from "react";

type Order = { id: string; status: string; total: number; items: unknown[] };

export function OrderTable({ orders }: { orders: Order[] }) {
  const [query, setQuery] = useState("");
  const [notes, setNotes] = useState<string[]>([]);
  useEffect(() => {
    fetch("/api/notes").then((r) => r.json()).then(setNotes);
  }, []);
  const rows = orders.filter((o) => o.status.includes(query)).sort((a, b) => b.total - a.total);
  return (
    <div>
      <input value={query} onChange={(e) => setQuery(e.target.value)} />
      <ul>{rows.map((o) => <li key={o.id}>{o.id} — {o.total} ({notes.length} notes)</li>)}</ul>
    </div>
  );
}

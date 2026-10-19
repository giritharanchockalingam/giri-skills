"use client";
/* Table standard: click a column header to sort (again to reverse); keyboard-accessible; aria-sort set. Nulls last. */
import { useMemo, useState } from "react";

type Key = string | number | null | undefined;
export function useSortable<T>(rows: T[], cols: Record<string, (r: T) => Key>, initial?: { key: string; dir: "asc" | "desc" }) {
  const [sort, setSort] = useState(initial ?? null);
  const sorted = useMemo(() => {
    if (!sort || !cols[sort.key]) return rows;
    const get = cols[sort.key], m = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const x = get(a), y = get(b);
      if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
      return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true })) * m;
    });
  }, [rows, sort, cols]);
  const th = (key: string, label: React.ReactNode, props: React.ThHTMLAttributes<HTMLTableCellElement> = {}) => {
    const on = sort?.key === key;
    const flip = () => setSort(on ? { key, dir: sort!.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" });
    return (
      <th {...props} className={`${props.className ?? ""} sortable`.trim()} aria-sort={on ? (sort!.dir === "asc" ? "ascending" : "descending") : "none"}
        tabIndex={0} onClick={flip} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flip(); } }}>
        {label}{on && <span className="sort-ind" aria-hidden="true">{sort!.dir === "asc" ? "▲" : "▼"}</span>}
      </th>
    );
  };
  return { sorted, th };
}

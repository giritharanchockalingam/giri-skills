import type { Verdict } from "@/lib/data";

export function VerdictBadge({ v }: { v: Verdict | null | undefined }) {
  return <span className={`badge badge-${v ?? "none"}`}>{v ?? "n/a"}</span>;
}

export function Lift({ n, digits = 2 }: { n: number | null | undefined; digits?: number }) {
  if (n == null) return <span className="muted">—</span>;
  const cls = n < 0 ? "lift-neg" : n >= 0.2 ? "lift-pos" : "";
  return <span className={`mono ${cls}`}>{(n > 0 ? "+" : "") + n.toFixed(digits)}</span>;
}

import type { Verdict } from "@/lib/data";

export function VerdictBadge({ v }: { v: Verdict | null | undefined }) {
  return <span className={`badge badge-${v ?? "none"}`}>{v ?? "n/a"}</span>;
}

/** Lift number: ≥ +0.2 sage, < 0 rust, else ink. Keeps the sign. */
export function Lift({ n, digits = 2 }: { n: number | null | undefined; digits?: number }) {
  if (n == null) return <span className="muted">—</span>;
  const cls = n < 0 ? "num-neg" : n >= 0.2 ? "num-pos" : "";
  return <span className={`mono ${cls}`}>{(n > 0 ? "+" : "") + n.toFixed(digits)}</span>;
}

/** Trigger accuracy: < 0.8 rust. */
export function Trig({ n }: { n: number | null | undefined }) {
  if (n == null) return <span className="muted">—</span>;
  return <span className={`mono ${n < 0.8 ? "num-neg" : ""}`}>{n.toFixed(2)}</span>;
}

export function PassPill({ pass }: { pass: boolean | null | undefined }) {
  if (pass == null) return <span className="pill-na">—</span>;
  return <span className={pass ? "pill-pass" : "pill-fail"}>{pass ? "pass" : "fail"}</span>;
}

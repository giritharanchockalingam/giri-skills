import type { Verdict, AgentVerdict, UpstreamSkill } from "@/lib/data";
import { licenseLabel } from "@/lib/data";
import { verdictInfo, agentVerdictInfo } from "@/lib/verdict";

/** Verdict pill with a human label; the raw code and rule live in the tooltip. */
export function VerdictBadge({ v, small }: { v: Verdict | null | undefined; small?: boolean }) {
  const info = verdictInfo(v);
  return (
    <span className={`pill pill-${info.tone} ${small ? "pill-sm" : ""}`} title={v ? `${v} — ${info.explanation}` : info.explanation}>
      {info.label}
    </span>
  );
}

/** Agent run pill: Works (sage) / Partial (amber) / Broken (rust); a dash when no agent cases ran. */
export function AgentBadge({ v, small }: { v: AgentVerdict | null | undefined; small?: boolean }) {
  const info = agentVerdictInfo(v);
  if (!v) return <span className="muted" title={info.explanation}>—</span>;
  return <span className={`pill pill-${info.tone} ${small ? "pill-sm" : ""}`} title={info.explanation}>{info.label}</span>;
}

/** Lift number: ≥ +0.2 sage, < 0 rust, else ink. Keeps the sign. */
export function Lift({ n, digits = 2 }: { n: number | null | undefined; digits?: number }) {
  if (n == null) return <span className="muted">—</span>;
  const cls = n < 0 ? "num-neg" : n >= 0.2 ? "num-pos" : "";
  return <span className={`stat-num ${cls}`}>{(n > 0 ? "+" : "") + n.toFixed(digits)}</span>;
}

/** Trigger accuracy: < 0.8 rust. */
export function Trig({ n }: { n: number | null | undefined }) {
  if (n == null) return <span className="muted">—</span>;
  return <span className={`stat-num ${n < 0.8 ? "num-neg" : ""}`}>{n.toFixed(2)}</span>;
}

export function PassPill({ pass }: { pass: boolean | null | undefined }) {
  if (pass == null) return <span className="na-pill">n/a</span>;
  return <span className={pass ? "pass-pill" : "fail-pill"}>{pass ? "Pass" : "Fail"}</span>;
}

/** License pill for upstream skills: sage for MIT / Apache-2.0, amber for Anthropic source-available. Full license text in the tooltip. */
export function LicensePill({ u, small }: { u: Pick<UpstreamSkill, "license" | "licenseKind">; small?: boolean }) {
  const tone = u.licenseKind === "source-available" ? "hold" : "sage";
  return <span className={`pill pill-${tone} ${small ? "pill-sm" : ""}`} title={u.license}>{licenseLabel(u)}</span>;
}

import type { Gate } from "@/lib/factory/release";

/** compact: one line per gate (label · met/not met · short reason). Default: full sentence for the Release page. */
export function GateList({ gates, compact = false }: { gates: Gate[]; compact?: boolean }) {
  return (
    <div>
      {gates.map((g) => (
        <div key={g.key} className="gate">
          <span className={`gate-dot ${g.tone}`} aria-hidden="true" />
          <span className="gate-title">{g.label} <span className={g.met ? "pass" : "fail"} style={{ fontWeight: 500 }}>· {g.met ? "met" : "not met"}</span></span>
          <span className="gate-detail">{compact ? g.short : g.detail}</span>
        </div>
      ))}
    </div>
  );
}

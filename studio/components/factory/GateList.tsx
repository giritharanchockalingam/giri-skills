import type { Gate } from "@/lib/factory/release";

export function GateList({ gates }: { gates: Gate[] }) {
  return (
    <div>
      {gates.map((g) => (
        <div key={g.key} className="gate">
          <span className={`gate-dot ${g.tone}`} aria-hidden="true" />
          <span className="gate-title">{g.label} <span className={g.met ? "pass" : "fail"} style={{ fontWeight: 500 }}>· {g.met ? "met" : "not met"}</span></span>
          <span className="gate-detail">{g.detail}</span>
        </div>
      ))}
    </div>
  );
}

import type { AgentCase } from "@/lib/data";
import { PassPill } from "./Badge";

/** Agent eval cases: one collapsed block per case; open it for every check with pass/fail and the evidence line. */
export function AgentCases({ cases, emptyText = "No agent cases ran for this skill." }: { cases: AgentCase[]; emptyText?: string }) {
  if (cases.length === 0) return <p className="none mt-3">{emptyText}</p>;
  return (
    <div className="agent-cases">
      {cases.map((c) => (
        <details key={c.caseId} className="agent-case">
          <summary>
            <span className="caret" aria-hidden="true">▶</span>
            <span className="agent-case-id">{c.caseId}</span>
            <span className={`agent-case-count ${c.passed < c.total ? "fail" : ""}`}>{c.passed} of {c.total} checks passed</span>
          </summary>
          <ul className="agent-checks">
            {c.checks.map((k, i) => (
              <li key={i}>
                <PassPill pass={k.pass} />
                <div className="min-w-0">
                  <div className="agent-check">{k.check}</div>
                  {k.evidence && <div className="agent-evidence">{k.evidence}</div>}
                </div>
              </li>
            ))}
          </ul>
        </details>
      ))}
    </div>
  );
}

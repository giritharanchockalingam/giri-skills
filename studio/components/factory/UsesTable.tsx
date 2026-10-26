/* Loads of this version in Claude Code, as the governed plugin's hook reported them (sf_skill_uses). Server component. */
import { LocalTime } from "@/components/LocalTime";
import { skillUseLabels, type SkillUseRow } from "@/lib/factory/uses";

export function UsesTable({ uses, version }: { uses: SkillUseRow[]; version: number }) {
  return (
    <div className="card">
      <h2 className="h3">Used in Claude Code</h2>
      <p className="caption">Each time the governed plugin loaded v{version}: whether its files still matched the approved hash, and whether it was the current published version.</p>
      {uses.length === 0 ? <div className="empty"><div className="none">No uses reported yet.</div><p className="caption">Install the plugin in Claude Code (<code>/plugin marketplace add giritharanchockalingam/giri-skills</code>, then <code>/plugin install skills-factory@giri-skills</code>) and give it an API key to report uses.</p></div> : (
        <div className="tablewrap"><table className="tbl">
          <thead><tr><th>When</th><th>Result</th><th>Files</th><th>Version</th></tr></thead>
          <tbody>{uses.map((u) => { const l = skillUseLabels(u); return (
            <tr key={u.id}><td><LocalTime iso={u.created_at} /></td><td>{l.result}</td><td className={u.integrity === "verified" ? "" : "muted"}>{l.files}</td><td className="muted">{l.currency}</td></tr>
          ); })}</tbody>
        </table></div>
      )}
    </div>
  );
}

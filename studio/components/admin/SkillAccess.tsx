/* Administration · "Who can run which skills": the switch, a preview computed with the same rule the database
 * enforces (lib/access.ts ↔ sf_run_access), who holds which job role, and assigning or removing one. Server component. */
import Link from "next/link";
import { ActionForm } from "@/components/factory/ActionForm";
import { setSkillsByRole, assignRole, unassignRole } from "@/app/accessActions";
import { accessPreview, isRestricted, type Holder } from "@/lib/access";
import type { AccessData } from "@/lib/db/access";

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export function SkillAccess({ data, holders, admin }: { data: AccessData; holders: Holder[]; admin: boolean }) {
  const p = accessPreview({ holders, roles: data.roles, skills: data.skills, assignments: data.assignments });
  const runOnly = p.restricted.filter((r) => r.holder.kind === "user"), keys = p.restricted.filter((r) => r.holder.kind === "key");
  const noRoleUsers = p.withoutRole.filter((h) => h.kind === "user").length, noRoleKeys = p.withoutRole.filter((h) => h.kind === "key").length;
  const rolesOf = new Map(p.restricted.map((r) => [`${r.holder.kind}:${r.holder.id}`, r]));
  const roleName = new Map(data.roles.map((r) => [r.id, r.name]));
  const assignmentsOf = (h: Holder) => data.assignments.filter((a) => (h.kind === "user" ? a.user_id === h.id : a.api_key_id === h.id));
  const impact = `${plural(noRoleUsers, "person", "people")} with run-only access and ${plural(noRoleKeys, "API key")} hold no job role and could run nothing; ${plural(p.uncovered.length, "published skill")} ${p.uncovered.length === 1 ? "is" : "are"} in no job role.`;

  return (
    <div className="stack">
      <div className="card card-pad">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="h3" style={{ margin: 0 }}>Restrict skills by job role <span className={`pill pill-sm ${data.enabled ? "pill-sage" : "pill-none"}`}>{data.enabled ? "On" : "Off"}</span></div>
            <p className="caption" style={{ margin: "4px 0 0" }}>
              {data.enabled ? "People with run-only access and API keys run only the skills in their job roles. Authors, reviewers and admins are not restricted: they test skills before release."
                : "Off: every member and API key can run every published skill. When on, people with run-only access and API keys run only the skills in their job roles; authors, reviewers and admins stay unrestricted."}
            </p>
          </div>
          {admin && <ActionForm action={setSkillsByRole} hidden={{ enabled: data.enabled ? "off" : "on" }} submit={data.enabled ? "Turn off" : "Turn on"}
            submitClass={data.enabled ? "btn btn-secondary btn-sm" : "btn btn-primary btn-sm"}
            confirm={data.enabled ? "Turn off? Every member and key will be able to run every published skill." : `Turn on? ${impact}`} />}
        </div>
        <p className={`notice ${p.withoutRole.length || p.uncovered.length ? "notice-hold" : "notice-ok"} mt-3`} style={{ marginBottom: 0 }}>
          {data.enabled ? "Now: " : "If turned on: "}{runOnly.length - noRoleUsers} of {runOnly.length} {runOnly.length === 1 ? "person" : "people"} with run-only access and {keys.length - noRoleKeys} of {keys.length} API {keys.length === 1 ? "key" : "keys"} can run skills through a job role. {impact}
        </p>
        {p.uncovered.length > 0 && <details className="mt-2"><summary className="caption">Skills in no job role ({p.uncovered.length})</summary>
          <p className="caption">{p.uncovered.map((s) => s.title).join(" · ")}. Add them to a job role on <Link className="link" href="/roles">Roles</Link>, or only authors, reviewers and admins can run them while the switch is on.</p></details>}
      </div>

      <div className="card card-pad">
        <div className="h3 mb-2">Who holds which job role</div>
        <div className="tablewrap"><table className="mini"><thead><tr><th>Member or API key</th><th>Access</th><th>Job roles</th><th>Can run</th></tr></thead>
          <tbody>{holders.map((h) => {
            const r = rolesOf.get(`${h.kind}:${h.id}`);
            return (
              <tr key={`${h.kind}:${h.id}`}>
                <td>{h.label}</td>
                <td className="caption">{h.kind === "key" ? "API key" : h.access === "consumer" ? "run only" : h.access}</td>
                <td>{assignmentsOf(h).length === 0 ? <span className="caption">—</span> : assignmentsOf(h).map((a) => (
                  <span key={a.id} className="chip chip-sm" style={{ marginRight: 6 }}>{roleName.get(a.talent_id) ?? "unpublished role"}
                    {admin && <ActionForm action={unassignRole} hidden={{ id: a.id }} submit="×" submitClass="link caption" confirm={`Remove ${roleName.get(a.talent_id) ?? "this role"} from ${h.label}?`} />}</span>))}</td>
                <td className="caption">{!isRestricted(h) ? "everything (not restricted)" : !data.enabled ? "everything while off" : r && r.skills.length ? plural(r.skills.length, "skill") : <span className="ink-rust">nothing</span>}</td>
              </tr>);
          })}</tbody></table></div>
        {admin && (data.roles.length === 0
          ? <p className="caption mt-3">No published job roles yet. Create and publish one on <Link className="link" href="/roles">Roles</Link>; drafts grant nothing.</p>
          : <div className="mt-4"><ActionForm action={assignRole} submit="Assign job role">
              <div className="form-grid form-grid-2">
                <div className="field"><label htmlFor="ar-holder">Member or API key</label>
                  <select id="ar-holder" name="holder" className="select" required defaultValue="">
                    <option value="" disabled>Choose…</option>
                    {holders.filter(isRestricted).map((h) => <option key={`${h.kind}:${h.id}`} value={`${h.kind}:${h.id}`}>{h.label}{h.kind === "key" ? " (API key)" : ""}</option>)}
                  </select></div>
                <div className="field"><label htmlFor="ar-role">Job role (published)</label>
                  <select id="ar-role" name="talent_id" className="select" required defaultValue="">
                    <option value="" disabled>Choose…</option>
                    {data.roles.map((r) => <option key={r.id} value={r.id}>{r.name} ({plural(data.skills.filter((s) => [s.repoSkill, s.slug].some((k) => k && r.skills.includes(k))).length, "published skill")})</option>)}
                  </select></div>
              </div>
            </ActionForm>
            <p className="caption mt-2">Only people with run-only access and API keys are listed: authors, reviewers and admins are never restricted.</p></div>)}
      </div>
    </div>
  );
}

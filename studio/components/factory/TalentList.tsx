/* Server component: the list + "new" form shared by /roles and /pools. */
import Link from "next/link";
import { requireWorkspace } from "@/lib/factory/db";
import { can } from "@/lib/factory/roles";
import { ActionForm } from "@/components/factory/ActionForm";
import { createTalent } from "@/app/talentActions";
import { ROLE_TEMPLATES, POOL_TEMPLATES, skillMap } from "@/lib/factory/talentData";
import { listTalent, listTalentVersionSummaries } from "@/lib/db/talent";
import type { RoleSpec, PoolSpec } from "@/lib/factory/talent";
import { STAGES } from "@/lib/data";

export async function TalentList({ kind }: { kind: "role" | "pool" }) {
  const ctx = await requireWorkspace();
  const rows = await listTalent(ctx.supabase, ctx.workspace.id, kind);
  const versions = await listTalentVersionSummaries(ctx.supabase, rows.map((r) => r.id));
  const sm = skillMap();
  const base = kind === "role" ? "/roles" : "/pools";
  const templates = kind === "role" ? ROLE_TEMPLATES : POOL_TEMPLATES;
  const have = new Set(rows.map((r) => r.based_on).filter(Boolean));

  return (
    <div className="stack">
      <div className="card">
        <div className="tbl-scroll"><table className="tbl"><thead><tr>
          <th>{kind === "role" ? "Role" : "Pool"}</th><th>{kind === "role" ? "Skills" : "Team"}</th><th>{kind === "role" ? "Stages" : "Playbooks"}</th><th>Version</th><th>Based on</th>
        </tr></thead><tbody>
          {rows.map((r) => {
            const v = versions.find((x) => x.talent_id === r.id);
            const spec = v?.spec;
            const stages = kind === "role" ? new Set((spec?.skills ?? []).map((s) => sm.get(s)?.stage).filter(Boolean)).size : 0;
            return (
              <tr key={r.id}>
                <td><Link href={`${base}/${r.slug}`} className="link"><b>{r.name}</b></Link><div className="caption">{r.description}</div></td>
                <td>{kind === "role" ? spec?.skills?.length ?? 0 : `${spec?.members?.length ?? 0} roles`}</td>
                <td>{kind === "role" ? `${stages} of ${STAGES.length}` : (spec?.playbooks ?? []).join(", ") || "—"}</td>
                <td>{v ? <>v{v.version} <span className="caption">{v.status}</span></> : "—"}</td>
                <td className="caption">{r.based_on ?? "blank"}</td>
              </tr>
            );
          })}
          {rows.length === 0 && <tr><td colSpan={5} className="none">None yet. Start from a template below.</td></tr>}
        </tbody></table></div>
      </div>

      {can(ctx.role, "talent.edit") && (
        <div className="card card-pad" style={{ maxWidth: 720 }}>
          <div className="h3">New {kind === "role" ? "role" : "talent pool"}</div>
          {kind === "pool" && <p className="caption">Starting from a template also adds its roles (and their playbooks) to this workspace if they are not here yet.</p>}
          <ActionForm action={createTalent} submit={`Create ${kind}`} hidden={{ kind }}>
            <div className="ab-grid">
              <div className="field"><label htmlFor="nt-name">Name</label><input id="nt-name" name="name" className="input" required maxLength={160} placeholder={kind === "role" ? "e.g. Retail AI Architect" : "e.g. Northwind delivery pod"} /></div>
              <div className="field"><label htmlFor="nt-tpl">Start from</label>
                <select id="nt-tpl" name="template" className="select" defaultValue="">
                  <option value="">Blank</option>
                  {templates.map((t) => <option key={t.name} value={t.name}>{t.title}</option>)}
                </select></div>
            </div>
          </ActionForm>
        </div>
      )}

      <section className="section">
        <div className="h3 mb-2">Templates</div>
        <div className="tbl-scroll"><table className="tbl"><thead><tr><th>Template</th><th>{kind === "role" ? "Default skills" : "Roles"}</th><th>Playbooks</th><th /></tr></thead><tbody>
          {templates.map((t) => (
            <tr key={t.name}>
              <td><b>{t.title}</b><div className="caption">{t.description}</div></td>
              <td className="caption">{kind === "role" ? (t as RoleSpec).skills.map((s) => sm.get(s)?.name ?? s).join(", ") : (t as PoolSpec).members.map((m) => m.label ? `${m.label} (${m.role})` : m.role).join(", ")}</td>
              <td className="caption">{t.playbooks.join(", ") || "—"}</td>
              <td className="caption">{have.has(t.name) ? "in use" : ""}</td>
            </tr>
          ))}
        </tbody></table></div>
      </section>
    </div>
  );
}

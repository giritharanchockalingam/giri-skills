import { skillTitle } from "@/lib/names";
/* Server component: the list + "new" form shared by /roles and /teams. */
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
  const base = kind === "role" ? "/roles" : "/teams";
  const templates = kind === "role" ? ROLE_TEMPLATES : POOL_TEMPLATES;
  const have = new Set(rows.map((r) => r.based_on).filter(Boolean));
  const { data: held } = kind === "role" ? await ctx.supabase.from("sf_role_assignments").select("talent_id, user_id").eq("workspace_id", ctx.workspace.id) : { data: [] };
  const holders = (id: string) => { const h = ((held ?? []) as { talent_id: string; user_id: string | null }[]).filter((a) => a.talent_id === id); const p = h.filter((a) => a.user_id).length; return { people: p, keys: h.length - p }; };

  return (
    <div className="stack">
      <div className="card">
        <div className="tbl-scroll"><div className="tablewrap"><table className="tbl"><thead><tr>
          <th>{kind === "role" ? "Role" : "Team"}</th><th>{kind === "role" ? "Skills" : "Members"}</th><th title={kind === "role" ? "AI development lifecycle stages this role\u2019s skills cover" : undefined}>{kind === "role" ? "Lifecycle stages covered" : "Playbooks"}</th><th>Version</th>{kind === "role" && <th title="People and API keys this job role is assigned to (Administration › Who can run which skills)">Held by</th>}<th>Based on</th>
        </tr></thead><tbody>
          {rows.map((r) => {
            const v = versions.find((x) => x.talent_id === r.id);
            const spec = v?.spec;
            // the lifecycle stages this role's skills belong to, named in lifecycle order
            const have = kind === "role" ? new Set((spec?.skills ?? []).map((s) => sm.get(s)?.stage).filter(Boolean)) : new Set();
            const stageNames = STAGES.filter((st) => have.has(st.id)).map((st) => st.name);
            return (
              <tr key={r.id}>
                <td><Link href={`${base}/${r.slug}`} className="link"><b>{r.name}</b></Link><div className="caption">{r.description}</div></td>
                <td>{kind === "role" ? spec?.skills?.length ?? 0 : `${spec?.members?.length ?? 0} roles`}</td>
                <td>{kind === "role"
                  ? (stageNames.length ? <><span>{stageNames.join(", ")}</span><div className="caption">{stageNames.length} of the {STAGES.length} lifecycle stages</div></> : <span className="muted">—</span>)
                  : (spec?.playbooks ?? []).map(skillTitle).join(", ") || "—"}</td>
                <td>{v ? <>v{v.version} <span className="caption">{v.status}</span></> : "—"}</td>
                {kind === "role" && <td className="caption">{(() => { const h = holders(r.id); return h.people + h.keys ? `${h.people} ${h.people === 1 ? "person" : "people"}${h.keys ? `, ${h.keys} key${h.keys === 1 ? "" : "s"}` : ""}` : "nobody"; })()}</td>}
                <td className="caption">{r.based_on ?? "blank"}</td>
              </tr>
            );
          })}
          {rows.length === 0 && <tr><td colSpan={kind === "role" ? 6 : 5} className="none">None yet. Start from a template below.</td></tr>}
        </tbody></table></div></div>
      </div>

      {can(ctx.role, "talent.edit") && (
        <div className="card card-pad" style={{ maxWidth: 720 }}>
          <div className="h3">New {kind === "role" ? "role" : "team"}</div>
          {kind === "pool" && <p className="caption">Starting from a template also adds its roles (and their playbooks) to this workspace if they are not here yet.</p>}
          <ActionForm action={createTalent} submit={kind === "role" ? "Create job role" : "Create team"} hidden={{ kind }}>
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
        <div className="tbl-scroll"><div className="tablewrap"><table className="tbl"><thead><tr><th>Template</th><th>{kind === "role" ? "Default skills" : "Roles"}</th><th>Playbooks</th><th>In this workspace</th></tr></thead><tbody>
          {templates.map((t) => (
            <tr key={t.name}>
              <td><b>{t.title}</b><div className="caption">{t.description}</div></td>
              <td className="caption">{kind === "role" ? (t as RoleSpec).skills.map((s) => sm.get(s)?.name ?? s).join(", ") : (t as PoolSpec).members.map((m) => m.label ? `${m.label} (${m.role})` : m.role).join(", ")}</td>
              <td className="caption">{t.playbooks.join(", ") || "—"}</td>
              <td className="caption">{have.has(t.name) ? "in use" : "—"}</td>
            </tr>
          ))}
        </tbody></table></div></div>
      </section>
    </div>
  );
}

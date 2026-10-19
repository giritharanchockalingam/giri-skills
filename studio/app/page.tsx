import Link from "next/link";
import { getContext, type WsCtx } from "@/lib/factory/db";
import { createWorkspace, selectWorkspace } from "@/app/actions";
import { ActionForm } from "@/components/factory/ActionForm";
import { PageHead } from "@/components/PageHead";
import { TaskBox } from "@/components/factory/TaskBox";
import { roleGroups, tryHref } from "@/lib/frontdoor";
import { skills as repoSkills, STAGES, SHELVES } from "@/lib/data";

export const metadata = { title: "Home · Skills Factory" };
export const dynamic = "force-dynamic";

/** The front door: start from the work (a task, a role, or a whole playbook) — not from the factory's internals. */
export default async function Home() {
  const c = await getContext();
  if (!c.workspace || !c.role) {
    return (
      <>
        <PageHead eyebrow="Welcome" title="Create your" em="workspace" after="." lead="A workspace holds your roles, playbooks, runs and the people who may use them. Whoever creates it becomes its administrator." />
        <div className="card card-pad" style={{ maxWidth: 560 }}>
          <ActionForm action={createWorkspace} submit="Create workspace">
            <div className="field"><label htmlFor="ws-name">Workspace name</label><input id="ws-name" name="name" className="input" required maxLength={120} placeholder="e.g. Finance Operations" /></div>
          </ActionForm>
          <p className="caption mt-4">Added to someone else&apos;s workspace? Their administrator adds you by your sign-in email ({c.user.email}).</p>
        </div>
      </>
    );
  }
  const ctx = c as WsCtx;
  const [rolesQ, agentsQ] = await Promise.all([
    ctx.supabase.from("sf_talent").select("slug").eq("workspace_id", ctx.workspace.id).eq("kind", "role"),
    ctx.supabase.from("sf_agents").select("slug, name, description").eq("workspace_id", ctx.workspace.id).order("updated_at", { ascending: false }).limit(6),
  ]);
  const haveRole = new Set((rolesQ.data ?? []).map((r) => r.slug));
  const groups = roleGroups();
  const suggestions = ["Check the RLS policies in my Supabase migration", "Is our AI chatbot high-risk under the EU AI Act?", "Estimate effort and price for this work breakdown"];
  const runnable = repoSkills.filter((s) => (s as unknown as { agent?: unknown }).agent).length;

  return (
    <>
      <PageHead eyebrow={`Skills Factory · ${ctx.workspace.name}`} title="What do you need" em="done" after="?"
        lead="Describe the work in plain words. The library finds the skill that does it, tells you what you will get and who owns that work, and runs it — on an example first, then on your own files."
        caption={ctx.memberships.length > 1 ? (
          <form action={selectWorkspace} className="flex flex-wrap items-center gap-2">
            <span>Workspace</span>
            <select name="workspace_id" className="select" style={{ width: "auto", minHeight: 36 }} defaultValue={ctx.workspace.id} aria-label="Workspace">
              {ctx.memberships.map((m) => <option key={m.workspace_id} value={m.workspace_id}>{m.workspace.name} ({m.role})</option>)}
            </select>
            <button type="submit" className="btn btn-secondary btn-sm">Switch</button>
          </form>) : undefined} />

      <TaskBox suggestions={suggestions} />

      <section className="section">
        <div className="h2 mb-2">Or start from a role</div>
        <p className="caption mb-4">Each role is a set of skills. Click any example to see that skill run, start to finish, on sample inputs.</p>
        {groups.map((g) => (
          <div key={g.title} className="fd-group">
            <div className="eyebrow mb-2">{g.title}</div>
            <div className="fd-roles">
              {g.cards.map((r) => (
                <div key={r.slug} className="card card-pad fd-role">
                  <div className="fd-role-head">
                    <b>{r.title}</b>
                    <span className="caption">{r.skills} skills</span>
                  </div>
                  <p className="caption fd-role-desc">{r.description}</p>
                  <ul className="fd-examples">
                    {r.examples.map((e) => (
                      <li key={e.skill}><Link href={tryHref(e.skill, e.prompt)} className="fd-example">“{e.prompt}”</Link></li>
                    ))}
                  </ul>
                  <div className="fd-role-foot">
                    {haveRole.has(r.slug)
                      ? <Link href={`/roles/${r.slug}`} className="link caption">Open role →</Link>
                      : <Link href="/roles" className="link caption">Add to your workspace →</Link>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      {(agentsQ.data ?? []).length > 0 && (
        <section className="section">
          <div className="h2 mb-2">Or run a whole playbook</div>
          <p className="caption mb-4">A playbook chains several skills, with approvals where a person decides.</p>
          <div className="fd-roles">
            {(agentsQ.data ?? []).map((a) => (
              <div key={a.slug} className="card card-pad fd-role">
                <b>{a.name}</b>
                <p className="caption fd-role-desc">{a.description}</p>
                <div className="fd-role-foot"><Link href={`/agents/${a.slug}/run`} className="btn btn-secondary btn-sm">Run it</Link> <Link href={`/agents/${a.slug}`} className="link caption">See how it is configured</Link></div>
              </div>
            ))}
          </div>
        </section>
      )}

      <p className="caption section">
        The library has <Link href="/repo/" className="link">{runnable} runnable skills</Link> across {STAGES.length} stages of building AI and {SHELVES.length} business shelves.
        Publishing, evaluations and approvals live under <Link href="/admin" className="link">Admin</Link>.
      </p>
    </>
  );
}

import Link from "next/link";
import { providerKeyPresent, providerEnvKey, DEFAULT_COMPAT_BASE_URL, DEFAULT_COMPAT_MODEL } from "@/lib/factory/providers";
import { getContext, fmtDate } from "@/lib/factory/db";
import { loadAdminData, EMPTY_ADMIN_DATA } from "@/lib/db/admin";
import { can, ROLES, ROLE_HELP } from "@/lib/factory/roles";
import { addMember, removeMember, revokeInvitation, createApiKey, revokeApiKey, savePolicy, saveConnection, signOut, createWorkspace, useCompatForDrafts } from "@/app/actions";
import { ActionForm } from "@/components/factory/ActionForm";
import { PageHead, SectionHead } from "@/components/PageHead";
import { RolePill } from "@/components/factory/Pills";
import { RuntimeStatus } from "@/components/factory/RuntimeStatus";

export const metadata = { title: "Administration · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function AdminPage() {
  const ctx = await getContext();
  const admin = can(ctx.role, "admin.members");
  const ws = ctx.workspace;
  const data = ws ? await loadAdminData(ctx.supabase, ws.id, admin) : EMPTY_ADMIN_DATA;
  const memberRows = data.members;
  const invites = data.invites;
  const keyRows = data.keys;
  const connRows = data.connections;
  const pol = data.policy;
  const auditRows = data.audit;
  const anthropicPresent = providerKeyPresent("anthropic");
  const compatPresent = providerKeyPresent("openai_compat");

  return (
    <>
      <PageHead eyebrow={`Administration${ws ? ` · ${ws.name}` : ""}`} title="Access, connections," em="limits" after="."
        lead={ws ? (admin ? "Members and roles, API keys for applications, provider connections, spending and concurrency limits, and the audit log." : `You are ${ctx.role} here. Only administrators can change members, keys, connections and policies; you can see the audit log and your account.`) : "You are not in a workspace yet."} />

      <section className="card card-pad mb-6">
        <div className="h3">Behind the scenes</div>
        <p className="caption">For people who publish and govern skills. Nothing here is needed to use a skill.</p>
        <div className="chip-group mt-3">
          <Link href="/pipeline" className="chip">Release pipeline — versions, evidence, approvals</Link>
          <Link href="/evaluations" className="chip">Evaluations</Link>
          <Link href="/activity" className="chip">Activity — every run</Link>
          <Link href="/upstream/" className="chip">Reference skills from GitHub</Link>
        </div>
      </section>

      <section id="account" className="card card-pad mb-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><div className="h3">Your account</div><p className="caption">{ctx.user.email} · {ws ? <>{ctx.role} in {ws.name}</> : "no workspace"}{ctx.memberships.length > 1 && <> · member of {ctx.memberships.length} workspaces (switch on Home)</>}</p></div>
          <form action={signOut}><button type="submit" className="btn btn-secondary">Sign out</button></form>
        </div>
        {!ws && <div className="mt-4" style={{ maxWidth: 480 }}><ActionForm action={createWorkspace} submit="Create workspace"><div className="field"><label htmlFor="ws-name">Workspace name</label><input id="ws-name" name="name" className="input" required maxLength={120} /></div></ActionForm></div>}
      </section>

      {ws && (
        <>
          <section className="section" id="members">
            <SectionHead title="Members and" em="roles" caption="Roles are enforced on the server and in the database for every action." />
            <div className="card card-pad">
              <div className="tablewrap"><table className="mini"><thead><tr><th>Email</th><th>Role</th><th>Since</th>{admin && <th></th>}</tr></thead>
                <tbody>{memberRows.map((m) => <tr key={m.user_id}><td>{m.email}{m.user_id === ctx.user.id && <span className="caption"> (you)</span>}</td><td><RolePill role={m.role} /></td><td className="muted">{fmtDate(m.created_at)}</td>{admin && <td>{m.user_id !== ctx.user.id && <ActionForm action={removeMember} submit="Remove" submitClass="btn btn-danger btn-sm" confirm={`Remove ${m.email} from ${ws.name}?`} hidden={{ user_id: m.user_id }} />}</td>}</tr>)}</tbody></table></div>
              {admin && (
                <div className="mt-5">
                  <div className="h3" style={{ fontSize: 14 }}>Add or change a member</div>
                  <p className="caption mb-3">Setting a role for an existing member changes it. Someone without an account gets an invitation: they join with that role when they first sign in with the email (it expires in 14 days).</p>
                  {invites.length > 0 && (
                    <div className="mb-4"><div className="h3" style={{ fontSize: 14 }}>Pending invitations</div>
                      <div className="tablewrap"><table className="mini"><thead><tr><th>Email</th><th>Role</th><th>Expires</th><th></th></tr></thead>
                        <tbody>{invites.map((i) => <tr key={i.id}><td>{i.email}</td><td><RolePill role={i.role} /></td><td className="muted">{fmtDate(i.expires_at)}</td>
                          <td><ActionForm action={revokeInvitation} submit="Revoke" submitClass="btn btn-secondary btn-sm" hidden={{ id: i.id }} /></td></tr>)}</tbody></table></div></div>)}
                  <ActionForm action={addMember} submit="Save or invite">
                    <div className="form-grid form-grid-2">
                      <div className="field"><label htmlFor="m-email">Email</label><input id="m-email" name="email" className="input" type="email" required /></div>
                      <div className="field"><label htmlFor="m-role">Role</label><select id="m-role" name="role" className="select" defaultValue="author">{ROLES.map((r) => <option key={r} value={r}>{r} — {ROLE_HELP[r]}</option>)}</select></div>
                    </div>
                  </ActionForm>
                </div>
              )}
            </div>
          </section>

          <section className="section" id="connections">
            <SectionHead title="Connections and" em="runtime" caption="Secrets stay in server environment variables; a connection records which variable a skill needs and whether it is present. Status is checked on the server." />
            <div className="stack">
              <div className="card card-pad">
                <div className="h3 mb-2">Model providers</div>
                <dl className="kv">
                  <dt>OpenAI-compatible</dt><dd>{compatPresent ? <span className="pass">configured · {process.env.SF_LLM_BASE_URL || DEFAULT_COMPAT_BASE_URL}</span> : <span className="fail">not configured — set SF_LLM_API_KEY (Groq free tier by default)</span>}</dd>
                  <dt>Anthropic</dt><dd>{anthropicPresent ? <span className="pass">configured</span> : <span className="muted">not configured (paid; optional)</span>}</dd>
                  <dt>Without a key</dt><dd className="caption">llm steps are skipped and reported, never faked.</dd>
                  {compatPresent && <><dt>Model</dt><dd><code>{process.env.SF_LLM_MODEL || DEFAULT_COMPAT_MODEL}</code>{process.env.SF_LLM_PRICE_IN && process.env.SF_LLM_PRICE_OUT ? <span className="caption"> · ${process.env.SF_LLM_PRICE_IN} in / ${process.env.SF_LLM_PRICE_OUT} out per 1M tokens</span> : <span className="caption"> · no price set (SF_LLM_PRICE_IN/OUT) — cost and budget not tracked</span>}</dd></>}
                  <dt>Python runtime</dt><dd>{admin ? <RuntimeStatus /> : <span className="muted">admins can check the runtime here</span>}</dd>
                </dl>
                {admin && compatPresent && <div className="mt-4"><ActionForm action={useCompatForDrafts} submit="Use this model for all drafts with llm steps" submitClass="btn btn-secondary btn-sm" confirm="Switch every draft that has llm steps to this provider and model? Published versions are not changed." /></div>}
              </div>
              <div className="card card-pad">
                <div className="h3 mb-2">Declared connections <span className="muted font-normal">({connRows.length})</span></div>
                <div className="list">{connRows.map((c) => (
                  <div key={c.id} className="list-row"><span className="min-w-0"><span className="name"><code>{c.name}</code></span> <span className="caption">{c.kind}{c.secret_ref ? ` · ${c.secret_ref}` : ""}{typeof c.config.base_url === "string" && c.config.base_url ? ` · ${c.config.base_url}` : ""}</span></span>
                    <span className={c.status === "configured" || (providerEnvKey(c.name) && providerKeyPresent(c.name)) ? "pass" : c.status === "not_configured" ? "fail" : "muted"}>{providerEnvKey(c.name) ? (providerKeyPresent(c.name) ? "configured" : "not configured") : c.status.replace("_", " ")}</span></div>
                ))}{connRows.length === 0 && <p className="none">No connections declared. Manifests may still name “anthropic”, which is checked against the server key above.</p>}</div>
                {admin && (
                  <div className="mt-5"><div className="h3" style={{ fontSize: 14 }}>Add or update a connection</div>
                    <ActionForm action={saveConnection} submit="Save connection">
                      <div className="form-grid form-grid-2">
                        <div className="field"><label htmlFor="c-name">Name</label><input id="c-name" name="name" className="input" required pattern="[a-z0-9_-]{1,40}" placeholder="anthropic" /></div>
                        <div className="field"><label htmlFor="c-kind">Kind</label><select id="c-kind" name="kind" className="select" defaultValue="llm_provider"><option value="llm_provider">LLM provider</option><option value="http">HTTP service</option><option value="database">Database</option><option value="other">Other</option></select></div>
                        <div className="field"><label htmlFor="c-secret">Secret environment variable</label><input id="c-secret" name="secret_ref" className="input" placeholder="ANTHROPIC_API_KEY" pattern="[A-Za-z0-9_]{0,64}" /><span className="hint">Name only — the value is never stored here.</span></div>
                        <div className="field"><label htmlFor="c-url">Base URL (optional)</label><input id="c-url" name="base_url" className="input" placeholder="https://…" /></div>
                      </div>
                    </ActionForm></div>
                )}
              </div>
            </div>
          </section>

          <section className="section" id="keys">
            <SectionHead title="API" em="keys" caption="Applications call published skills with a key. The key is shown once at creation; only its hash is stored. See docs/API.md." />
            <div className="card card-pad">
              {admin ? (
                <>
                  <div className="tablewrap"><table className="mini"><thead><tr><th>Name</th><th>Prefix</th><th>Created</th><th>Last used</th><th>Status</th><th></th></tr></thead>
                    <tbody>{keyRows.map((k) => <tr key={k.id}><td>{k.name}</td><td className="mono-sm">{k.prefix}…</td><td className="muted">{fmtDate(k.created_at)}</td><td className="muted">{k.last_used_at ? fmtDate(k.last_used_at) : "never"}</td><td>{k.revoked_at ? <span className="fail">revoked</span> : <span className="pass">active</span>}</td><td>{!k.revoked_at && <ActionForm action={revokeApiKey} submit="Revoke" submitClass="btn btn-danger btn-sm" confirm={`Revoke key “${k.name}”? Applications using it will get 401.`} hidden={{ key_id: k.id }} />}</td></tr>)}
                      {keyRows.length === 0 && <tr><td colSpan={6} className="none">No API keys yet.</td></tr>}</tbody></table></div>
                  <div className="mt-5"><div className="h3" style={{ fontSize: 14 }}>Create a key</div>
                    <ActionForm action={createApiKey} submit="Create key" revealKey>
                      <div className="field" style={{ maxWidth: 420 }}><label htmlFor="k-name">Name</label><input id="k-name" name="name" className="input" required maxLength={80} placeholder="order-service (production)" /></div>
                    </ActionForm></div>
                </>
              ) : <p className="none">Administrators manage API keys.</p>}
            </div>
          </section>

          <section className="section" id="policies">
            <SectionHead title="Policies and" em="limits" caption="Allowlists and limits enforced before every run (server and database). Spend is estimated from provider-reported tokens; the budget compares against that estimate." />
            <div className="card card-pad">
              <ActionForm action={savePolicy} submit="Save policy" disabled={!admin}>
                <div className="form-grid form-grid-2">
                  <fieldset className="field"><legend className="field-label">Allowed tools</legend>{["script", "llm"].map((t) => <label key={t} className="check-row"><input type="checkbox" name="allowed_tools" value={t} defaultChecked={(pol?.allowed_tools ?? ["script", "llm"]).includes(t)} disabled={!admin} /> {t}</label>)}</fieldset>
                  <fieldset className="field"><legend className="field-label">Allowed providers</legend>{["none", "anthropic", "openai_compat"].map((t) => <label key={t} className="check-row"><input type="checkbox" name="allowed_providers" value={t} defaultChecked={(pol?.allowed_providers ?? ["none", "anthropic", "openai_compat"]).includes(t)} disabled={!admin} /> {t}</label>)}</fieldset>
                  <div className="field"><label htmlFor="p-budget">Monthly budget (USD, estimated spend; empty = no limit)</label><input id="p-budget" name="monthly_budget_usd" className="input" type="number" min={0} step={0.01} defaultValue={pol?.monthly_budget_usd ?? ""} disabled={!admin} /></div>
                  <div className="field"><label htmlFor="p-conc">Max concurrent runs</label><input id="p-conc" name="max_concurrency" className="input" type="number" min={1} max={50} defaultValue={pol?.max_concurrency ?? 2} disabled={!admin} /></div>
                  <div className="field span-2"><label htmlFor="p-appr">Self-service actions need a reviewer&apos;s approval</label>
                    <select id="p-appr" name="action_approval" className="select" defaultValue={pol?.action_approval ?? "model_steps"} disabled={!admin}>
                      <option value="model_steps">when the skill uses a model (default)</option>
                      <option value="always">always</option>
                      <option value="none">never</option>
                    </select>
                    <span className="hint">A reviewer or admin approves in the Inbox; nobody approves their own request. Enforced in the database.</span></div>
                </div>
              </ActionForm>
            </div>
          </section>

          <section className="section" id="audit">
            <SectionHead title="Audit" em="log" caption="Most recent 100 events in this workspace. Append-only." />
            <div className="card">
              {auditRows.length === 0 ? <div className="empty"><div className="none">No events yet.</div></div> : (
                <div className="tablewrap"><table className="tbl"><thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Entity</th><th className="col-wide">Details</th></tr></thead>
                  <tbody>{auditRows.map((a) => <tr key={a.id}><td className="muted" style={{ whiteSpace: "nowrap" }}>{fmtDate(a.created_at)}</td><td className="mono-sm">{a.actor_kind}{a.actor_id ? ` ${a.actor_id === ctx.user.id ? "(you)" : a.actor_id.slice(0, 8)}` : ""}</td><td><code>{a.action}</code></td><td className="mono-sm">{a.entity_type}{a.entity_id ? ` ${a.entity_id.slice(0, 8)}` : ""}</td><td className="col-wide mono-sm" style={{ maxWidth: 420 }}>{JSON.stringify(a.details).slice(0, 160)}</td></tr>)}</tbody></table></div>
              )}
            </div>
          </section>
          <p className="caption mt-6">Consumer API documentation: <code>studio/docs/API.md</code> in the repository (endpoints, curl examples, error codes).</p>
        </>
      )}
    </>
  );
}

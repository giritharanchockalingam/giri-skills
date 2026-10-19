"use client";
/* Role and talent-pool editors. A role is a set of skills (tailored from a template by adding/removing) plus the
 * playbooks it runs; a pool is a team of roles, checked for ADLC coverage and for whether its playbooks are staffed.
 * Validation here is the same code the server runs before publishing (lib/factory/talent.ts). */
import Link from "next/link";
import { useMemo, useState, useTransition } from "react";
import {
  validateRoleSpec, validatePoolSpec, diffFromTemplate, coverage, staffPlaybook, memberKey,
  type RoleSpec, type PoolSpec, type SkillInfo, type PlaybookInfo,
} from "@/lib/factory/talent";
import { ActionForm } from "./ActionForm";
import { saveTalentDraft, routeTask, type RouteResult } from "@/app/talentActions";

interface Stage { id: string; n?: number; name: string }
export interface PlaybookRow extends PlaybookInfo { status: string; version: number; steps: number }
const skillHref = (id: string) => `/repo/${id}`;

function Problems({ problems, okText }: { problems: string[]; okText: string }) {
  return (
    <>
      <div className="h3">{problems.length ? <span className="fail">{problems.length} problem{problems.length === 1 ? "" : "s"}</span> : <span className="pass">{okText}</span>}</div>
      {problems.length > 0 && <ul className="ab-problems">{problems.slice(0, 12).map((p) => <li key={p}>{p}</li>)}</ul>}
    </>
  );
}

function SkillPicker({ catalog, stages, exclude, onPick, onClose }: { catalog: SkillInfo[]; stages: Stage[]; exclude: Set<string>; onPick: (id: string) => void; onClose: () => void }) {
  const [q, setQ] = useState(""); const [stage, setStage] = useState("all");
  const n = q.trim().toLowerCase();
  const list = catalog.filter((c) => !exclude.has(c.id) && (stage === "all" || c.stage === stage) && (!n || c.id.includes(n) || c.description.toLowerCase().includes(n)));
  return (
    <div className="card card-pad stack-sm ab-picker" role="dialog" aria-label="Add a skill to the role">
      <div className="ab-grid">
        <input className="input" autoFocus placeholder="Search skills" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search skills" />
        <select className="select" value={stage} onChange={(e) => setStage(e.target.value)} aria-label="Stage">
          <option value="all">All stages</option>{stages.map((s) => <option key={s.id} value={s.id}>{s.n ? `${s.n} ` : ""}{s.name}</option>)}
        </select>
        <button type="button" className="btn btn-sm" onClick={onClose}>Close</button>
      </div>
      <ul className="ab-pick-list">
        {list.map((c) => (
          <li key={c.id}><button type="button" className="ab-pick" onClick={() => onPick(c.id)}>
            <b>{c.name}</b> <span className="caption">{stages.find((s) => s.id === c.stage)?.name ?? ""}</span>
            <span className="caption ab-pick-desc">{c.description.replace(/^Use when /i, "")}</span>
          </button></li>
        ))}
        {list.length === 0 && <li className="none">No skill matches.</li>}
      </ul>
    </div>
  );
}

// ---------------- role ----------------

export function RoleEditor({ initial, template, versionId, catalog, stages, playbooks, editable }: {
  initial: RoleSpec; template?: RoleSpec; versionId: string; catalog: SkillInfo[]; stages: Stage[]; playbooks: PlaybookRow[]; editable: boolean;
}) {
  const cat = useMemo(() => new Map(catalog.map((c) => [c.id, c])), [catalog]);
  const pbMap = useMemo(() => new Map(playbooks.map((p) => [p.name, p])), [playbooks]);
  const [spec, setSpec] = useState<RoleSpec>(() => ({ ...initial, skills: initial.skills ?? [], playbooks: initial.playbooks ?? [] }));
  const [saved, setSaved] = useState(JSON.stringify(initial));
  const [picker, setPicker] = useState(false);
  const dirty = JSON.stringify(spec) !== saved;
  const problems = validateRoleSpec(spec, cat, pbMap);
  const diff = diffFromTemplate(spec, template);
  const owned = new Set(spec.skills);
  const set = (p: Partial<RoleSpec>) => setSpec((s) => ({ ...s, ...p }));
  const byStage = stages.map((st) => ({ st, skills: spec.skills.filter((s) => cat.get(s)?.stage === st.id) })).filter((g) => g.skills.length);

  return (
    <div className="agent-builder">
      <div className="stack">
        <div className="card card-pad stack-sm">
          <div className="ab-grid" style={{ marginTop: 0 }}>
            <div className="field"><label htmlFor="r-title">Role title</label><input id="r-title" className="input" value={spec.title} disabled={!editable} onChange={(e) => set({ title: e.target.value })} /></div>
          </div>
          <div className="field"><label htmlFor="r-desc">Accountable for</label><textarea id="r-desc" className="textarea" rows={2} value={spec.description} disabled={!editable} onChange={(e) => set({ description: e.target.value })} /></div>
        </div>

        <div className="card card-pad">
          <div className="ab-step-head">
            <div className="h3" style={{ margin: 0 }}>Skills <span className="muted font-normal">({spec.skills.length})</span></div>
            {template && <span className="caption">tailored from <b>{template.title}</b>{diff.added.length || diff.removed.length ? ` · +${diff.added.length} added, −${diff.removed.length} removed` : " · unchanged"}</span>}
            {editable && <button type="button" className="btn btn-sm btn-primary ab-tools" onClick={() => setPicker(true)}>Add skill</button>}
          </div>
          {picker && <div className="mt-3"><SkillPicker catalog={catalog} stages={stages} exclude={owned} onPick={(id) => { set({ skills: [...spec.skills, id] }); setPicker(false); }} onClose={() => setPicker(false)} /></div>}
          <div className="tl-stages">
            {byStage.map(({ st, skills }) => (
              <div key={st.id} className="tl-stage">
                <div className="caption tl-stage-name">{st.n ? `${st.n} · ` : ""}{st.name}</div>
                <div className="chip-group">
                  {skills.map((s) => (
                    <span key={s} className={`chip tl-skill ${diff.added.includes(s) ? "tl-added" : ""}`} title={cat.get(s)?.description}>
                      <Link href={skillHref(s)} className="link">{cat.get(s)?.name ?? s}</Link>
                      {editable && <button type="button" className="tl-x" aria-label={`Remove ${s}`} onClick={() => set({ skills: spec.skills.filter((x) => x !== s) })}>×</button>}
                    </span>
                  ))}
                </div>
              </div>
            ))}
            {spec.skills.length === 0 && <p className="none">No skills yet. Add the skills this role brings.</p>}
          </div>
          {diff.removed.length > 0 && (
            <p className="caption mt-3">Removed from the template: {diff.removed.map((s, i) => (
              <span key={s}>{i ? ", " : ""}{cat.get(s)?.name ?? s}{editable && <> <button type="button" className="btn-link" onClick={() => set({ skills: [...spec.skills, s] })}>restore</button></>}</span>))}</p>
          )}
        </div>

        <div className="card card-pad">
          <div className="h3">Playbooks</div>
          <p className="caption">Agents this role runs end to end. A playbook fits only when the role has every skill it uses.</p>
          <ul className="ab-inputs">
            {playbooks.map((p) => {
              const missing = [...new Set(p.skills.filter((s) => !owned.has(s)))];
              const on = spec.playbooks.includes(p.name);
              return (
                <li key={p.name}>
                  <label className="tl-check">
                    <input type="checkbox" checked={on} disabled={!editable || (!on && missing.length > 0)}
                      onChange={(e) => set({ playbooks: e.target.checked ? [...spec.playbooks, p.name] : spec.playbooks.filter((x) => x !== p.name) })} />
                    <b>{p.name}</b> <span className="caption">{p.steps} steps · v{p.version} {p.status}</span>
                  </label>
                  {missing.length > 0 && <div className="caption">needs {missing.map((s) => cat.get(s)?.name ?? s).join(", ")}</div>}
                  {on && <Link href={`/agents/${p.name}/run?v=${p.version}`} className="link caption">Run this playbook →</Link>}
                </li>
              );
            })}
            {playbooks.length === 0 && <li className="none">No agents in this workspace yet.</li>}
          </ul>
        </div>

        <TaskRouter skills={spec.skills} catalog={cat} />
      </div>

      <aside className="ab-side stack">
        <div className="card card-pad">
          <Problems problems={problems} okText="Ready to publish" />
          {editable && <ActionForm action={async (p, fd) => { const r = await saveTalentDraft(p, fd); if (r.ok) setSaved(String(fd.get("spec"))); return r; }}
            submit={dirty ? "Save draft" : "Saved"} disabled={!dirty} hidden={{ kind: "role", version_id: versionId, spec: JSON.stringify(spec) }} />}
        </div>
        <div className="card card-pad">
          <div className="h3">Stages covered</div>
          <div className="chip-group">{stages.map((st) => {
            const n = spec.skills.filter((s) => cat.get(s)?.stage === st.id).length;
            return n ? <span key={st.id} className="chip">{st.name} · {n}</span> : null;
          })}</div>
        </div>
      </aside>
    </div>
  );
}

/** Give the role a task: it ranks its OWN skills for it (deterministic BM25 on each skill's description and
 *  "When to use"), shows the words that matched, and links straight to running the skill. */
export function TaskRouter({ skills, catalog }: { skills: string[]; catalog: Map<string, SkillInfo> }) {
  const [task, setTask] = useState("");
  const [res, setRes] = useState<RouteResult | null>(null);
  const [pending, start] = useTransition();
  return (
    <div className="card card-pad stack-sm">
      <div className="h3">Give this role a task</div>
      <p className="caption">The role picks the best of its {skills.length} skills for the task and shows why.</p>
      <textarea className="textarea" rows={3} value={task} onChange={(e) => setTask(e.target.value)} aria-label="Task"
        placeholder="e.g. How many GPUs do we need to serve a 70B model at 50 requests per second?" />
      <div className="action-row" style={{ marginTop: 0 }}>
        <button type="button" className="btn btn-primary" disabled={pending || task.trim().length < 8 || skills.length === 0}
          onClick={() => start(async () => setRes(await routeTask(skills, task)))} aria-busy={pending}>{pending ? "Routing…" : "Route task"}</button>
        {res && !res.ok && <div className="notice notice-err" role="status">{res.message}</div>}
      </div>
      {res?.ok && res.hits && (
        <ol className="tl-hits">
          {res.hits.map((h, i) => (
            <li key={h.skill} className={i === 0 ? "tl-hit tl-best" : "tl-hit"}>
              <div className="ab-step-head">
                <b>{h.name}</b>{i === 0 && <span className="pill pill-sm pill-sage">best match</span>}
                <span className="caption">score {h.score.toFixed(2)}</span>
                <span className="ab-tools"><Link href={`${skillHref(h.skill)}/test`} className="btn btn-sm btn-primary">Run this skill</Link></span>
              </div>
              <div className="caption">matched: {h.matched.join(", ")}</div>
              {i === 0 && <div className="caption tl-why">{catalog.get(h.skill)?.description.replace(/^Use when /i, "")}</div>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ---------------- pool ----------------

export function PoolEditor({ initial, versionId, roles, catalog, stages, playbooks, editable }: {
  initial: PoolSpec; versionId: string; roles: (RoleSpec & { status: string; version: number })[]; catalog: SkillInfo[]; stages: Stage[]; playbooks: PlaybookRow[]; editable: boolean;
}) {
  const cat = useMemo(() => new Map(catalog.map((c) => [c.id, c])), [catalog]);
  const roleMap = useMemo(() => new Map(roles.map((r) => [r.name, r])), [roles]);
  const pbMap = useMemo(() => new Map(playbooks.map((p) => [p.name, p])), [playbooks]);
  const [spec, setSpec] = useState<PoolSpec>(() => ({ ...initial, members: initial.members ?? [], playbooks: initial.playbooks ?? [] }));
  const [saved, setSaved] = useState(JSON.stringify(initial));
  const dirty = JSON.stringify(spec) !== saved;
  const stageOf = (id: string) => cat.get(id)?.stage;
  const problems = validatePoolSpec(spec, roleMap, pbMap, stageOf);
  const set = (p: Partial<PoolSpec>) => setSpec((s) => ({ ...s, ...p }));
  const setMember = (i: number, m: Partial<PoolSpec["members"][number]>) => set({ members: spec.members.map((x, k) => (k === i ? { ...x, ...m } : x)) });
  const members = spec.members.map((m, i) => ({ key: memberKey(m, i, spec.members), skills: roleMap.get(m.role)?.skills ?? [] }));
  // ADLC stages are scored (gaps count); business shelves are shown only when a member brings them
  const adlc = stages.filter((s) => s.n != null);
  const cov = coverage(members, cat, adlc);
  const shelves = coverage(members, cat, stages.filter((s) => s.n == null)).rows.filter((r) => r.covered);
  const shown = [...cov.rows, ...shelves];
  const seats = spec.members.reduce((a, m) => a + (m.seats ?? 1), 0);
  const unique = new Set(members.flatMap((m) => m.skills)).size;

  return (
    <div className="agent-builder">
      <div className="stack">
        <div className="card card-pad stack-sm">
          <div className="field"><label htmlFor="p-title">Pool name</label><input id="p-title" className="input" value={spec.title} disabled={!editable} onChange={(e) => set({ title: e.target.value })} /></div>
          <div className="field"><label htmlFor="p-desc">What this team delivers</label><textarea id="p-desc" className="textarea" rows={2} value={spec.description} disabled={!editable} onChange={(e) => set({ description: e.target.value })} /></div>
        </div>

        <div className="card card-pad">
          <div className="h3">Team <span className="muted font-normal">({spec.members.length} roles · {seats} seats · {unique} distinct skills)</span></div>
          <div className="tbl-scroll"><table className="tbl ab-wiring"><thead><tr><th>Role</th><th>Name in team</th><th>Seats</th><th>Skills</th>{editable && <th />}</tr></thead><tbody>
            {spec.members.map((m, i) => (
              <tr key={i}>
                <td><select className="select" value={m.role} disabled={!editable} onChange={(e) => setMember(i, { role: e.target.value })} aria-label="Role">
                  {!roleMap.has(m.role) && <option value={m.role}>{m.role} (missing)</option>}
                  {roles.map((r) => <option key={r.name} value={r.name}>{r.title}</option>)}</select>
                  {roleMap.has(m.role) && <div className="caption"><Link href={`/roles/${m.role}`} className="link">open role</Link></div>}</td>
                <td><input className="input" value={m.label ?? ""} placeholder={memberKey({ role: m.role }, i, spec.members.map((x, k) => (k === i ? { role: x.role } : x)))} disabled={!editable} onChange={(e) => setMember(i, { label: e.target.value || undefined })} aria-label="Name in team" /></td>
                <td><input className="input" type="number" min={1} max={50} style={{ width: 70 }} value={m.seats ?? 1} disabled={!editable} onChange={(e) => setMember(i, { seats: Math.max(1, Number(e.target.value) || 1) })} aria-label="Seats" /></td>
                <td className="caption">{roleMap.get(m.role)?.skills.length ?? 0}</td>
                {editable && <td><span className="ab-tools">
                  <button type="button" className="btn btn-sm" disabled={i === 0} onClick={() => { const ms = [...spec.members]; [ms[i - 1], ms[i]] = [ms[i], ms[i - 1]]; set({ members: ms }); }} aria-label="Move up">↑</button>
                  <button type="button" className="btn btn-sm btn-danger" onClick={() => set({ members: spec.members.filter((_, k) => k !== i) })} aria-label="Remove member">Remove</button></span></td>}
              </tr>
            ))}
            {spec.members.length === 0 && <tr><td colSpan={5} className="none">No members yet.</td></tr>}
          </tbody></table></div>
          {editable && (
            <div className="ab-grid">
              <select className="select" value="" aria-label="Add a role" onChange={(e) => { if (e.target.value) set({ members: [...spec.members, { role: e.target.value }] }); }}>
                <option value="">Add a role…</option>{roles.map((r) => <option key={r.name} value={r.name}>{r.title}</option>)}
              </select>
              <Link href="/roles" className="link caption">Create or tailor a role →</Link>
            </div>
          )}
        </div>

        <div className="card card-pad">
          <div className="h3">Coverage <span className="muted font-normal">({cov.covered} of {cov.rows.length} stages)</span></div>
          <p className="caption">Which member brings a skill for each stage. A gap means nobody on this team can do that work.</p>
          <div className="tbl-scroll"><table className="tbl tl-cov"><thead><tr><th>Stage</th>{members.map((m) => <th key={m.key}>{m.key}</th>)}</tr></thead><tbody>
            {shown.map((r) => (
              <tr key={r.stage.id} className={r.covered ? "" : "tl-gap"}>
                <td>{r.stage.n ? `${r.stage.n} · ` : ""}{r.stage.name}{!r.covered && <span className="pill pill-sm pill-rust" style={{ marginLeft: 6 }}>gap</span>}</td>
                {r.by.map((b) => <td key={b.key} title={b.skills.map((s) => cat.get(s)?.name ?? s).join(", ")}>{b.skills.length ? b.skills.length : ""}</td>)}
              </tr>
            ))}
          </tbody></table></div>
        </div>

        <div className="card card-pad">
          <div className="h3">Playbooks</div>
          <p className="caption">Agents this team runs. Each step goes to the member who has its skill and is most specialised in that stage (ties: team order).</p>
          <ul className="ab-inputs">
            {playbooks.map((p) => {
              const on = spec.playbooks.includes(p.name);
              const staffing = staffPlaybook(p, members, stageOf);
              const gaps = staffing.filter((x) => !x.member).length;
              return (
                <li key={p.name}>
                  <label className="tl-check">
                    <input type="checkbox" checked={on} disabled={!editable} onChange={(e) => set({ playbooks: e.target.checked ? [...spec.playbooks, p.name] : spec.playbooks.filter((x) => x !== p.name) })} />
                    <b>{p.name}</b> <span className="caption">{p.steps} steps · v{p.version} {p.status}{gaps ? ` · ${gaps} unstaffed` : " · fully staffed"}</span>
                  </label>
                  {on && (
                    <>
                      <ol className="tl-handoff">{staffing.map((x, k) => (
                        <li key={k}><span>{cat.get(x.skill)?.name ?? x.skill}</span> <span className={x.member ? "caption" : "fail caption"}>→ {x.member ?? "nobody"}</span></li>))}</ol>
                      <Link href={`/agents/${p.name}/run?v=${p.version}`} className="link caption">Run this playbook →</Link>
                    </>
                  )}
                </li>
              );
            })}
            {playbooks.length === 0 && <li className="none">No agents in this workspace yet.</li>}
          </ul>
        </div>
      </div>

      <aside className="ab-side stack">
        <div className="card card-pad">
          <Problems problems={problems} okText="Ready to publish" />
          {editable && <ActionForm action={async (p, fd) => { const r = await saveTalentDraft(p, fd); if (r.ok) setSaved(String(fd.get("spec"))); return r; }}
            submit={dirty ? "Save draft" : "Saved"} disabled={!dirty} hidden={{ kind: "pool", version_id: versionId, spec: JSON.stringify(spec) }} />}
        </div>
        {cov.gaps.length > 0 && (
          <div className="card card-pad">
            <div className="h3">Gaps</div>
            <p className="caption">Stages no member covers: {cov.gaps.map((g) => stages.find((s) => s.id === g)?.name ?? g).join(", ")}. Add a role that has those skills, or tailor a member.</p>
          </div>
        )}
      </aside>
    </div>
  );
}

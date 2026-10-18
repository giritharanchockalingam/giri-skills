import Link from "next/link";
import { loadSkillPage } from "@/lib/factory/skillPage";
import { can } from "@/lib/factory/roles";
import { evalGate, approvalGate, nextAction } from "@/lib/factory/release";
import { fmtDate, type ApprovalRow } from "@/lib/factory/db";
import { requestReview, withdrawReview, reviewVersion, publishVersion, retireVersion, createDraft, reopenVersion } from "@/app/actions";
import { ActionForm } from "@/components/factory/ActionForm";
import { VersionBar } from "@/components/factory/VersionBar";
import { GateList } from "@/components/factory/GateList";

export const dynamic = "force-dynamic";

export default async function ReleasePage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ v?: string }> }) {
  const { slug } = await params; const { v } = await searchParams;
  const d = await loadSkillPage(slug, v ?? null);
  const s = d.state;
  const { data: approvalsQ } = await d.ctx.supabase.from("sf_approvals").select("*").eq("version_id", d.version.id).order("created_at", { ascending: false });
  const approvals = (approvalsQ ?? []) as ApprovalRow[];
  const gates = s ? [evalGate(s), approvalGate(s)] : [];
  const na = s ? nextAction(s, d.runCount > 0) : null;
  const st = d.version.status;
  const hidden = { version_id: d.version.id, slug };
  const isAuthorOfVersion = d.version.created_by === d.ctx.user.id;

  return (
    <>
      <VersionBar slug={slug} view="release" versions={d.versions} current={d.version} />
      <div className="two-col">
        <div className="stack min-w-0">
          <div className="card card-pad">
            <div className="h3 mb-1">Release readiness — v{d.version.version}</div>
            <p className="caption mb-2">Both gates are re-checked by the database when you publish; this page explains them. Manifest hash <code>{d.version.manifest_hash.slice(0, 16)}…</code>.</p>
            <GateList gates={gates} />
            {na && <p className="caption mt-3">Next: <b>{na.label}</b> ({na.who}).</p>}
          </div>

          {(st === "draft" || st === "in_review" || st === "approved") && (
            <div className="card card-pad">
              <div className="h3 mb-3">Lifecycle</div>
              <div className="stack">
                {st === "draft" && (can(d.ctx.role, "version.request_review") ? (
                  <div><p className="sub mb-2">Request review when the contract is final and the evaluation evidence is in place. Reviewers approve the exact manifest hash above; any later edit makes the approval stale.</p>
                    <ActionForm action={requestReview} submit="Request review" hidden={hidden} /></div>
                ) : <p className="notice notice-info">Draft — an author requests review when the version is ready.</p>)}
                {st === "in_review" && (
                  <>
                    {can(d.ctx.role, "version.review") ? (
                      isAuthorOfVersion && d.ctx.role !== "admin" ? <div className="notice notice-hold">You created this version; a different reviewer (or an admin) must decide.</div> : (
                        <div>
                          <p className="sub mb-2">Review the evidence (Summary, Evaluations, Activity) and decide on this exact version.</p>
                          <ActionForm action={reviewVersion} submit="Approve version" hidden={{ ...hidden, decision: "approve" }}>
                            <div className="field"><label htmlFor="rv-note">Reviewer note</label><textarea id="rv-note" name="note" className="textarea" style={{ minHeight: 64 }} maxLength={2000} placeholder="What you checked and why it is acceptable (or not)." /></div>
                          </ActionForm>
                          <ActionForm action={reviewVersion} submit="Reject and return to draft" submitClass="btn btn-danger" hidden={{ ...hidden, decision: "reject" }} confirm="Reject this version and return it to draft?">
                            <div className="field"><label htmlFor="rj-note">Rejection reason</label><input id="rj-note" name="note" className="input" maxLength={2000} placeholder="What must change" /></div>
                          </ActionForm>
                        </div>
                      )
                    ) : <div className="notice notice-hold">Waiting for a reviewer or admin to decide.</div>}
                    {can(d.ctx.role, "version.request_review") && <ActionForm action={withdrawReview} submit="Withdraw to draft" submitClass="btn btn-secondary" hidden={hidden} />}
                  </>
                )}
                {st === "approved" && can(d.ctx.role, "version.edit") && (
                  <div><p className="sub mb-2">Need a change before publishing? Reopen as a draft. The approval remains pinned to the current manifest hash — any edit makes it stale and a new review is required.</p>
                    <ActionForm action={reopenVersion} submit="Reopen for editing" submitClass="btn btn-secondary" hidden={hidden} /></div>
                )}
                {(st === "approved" || st === "draft" || st === "in_review") && can(d.ctx.role, "version.publish") && (
                  <div>
                    <p className="sub mb-2">Publishing makes v{d.version.version} the version consumers and the API run, supersedes the current published version, and freezes it forever.</p>
                    <ActionForm action={publishVersion} submit="Publish version" hidden={hidden} disabled={!s?.publishable} confirm={`Publish v${d.version.version}? This supersedes any published version and cannot be edited afterwards.`} />
                    {!s?.publishable && <p className="caption mt-2">Disabled until both gates are met. The server enforces the same rule.</p>}
                  </div>
                )}
              </div>
            </div>
          )}

          {st === "published" && (
            <div className="card card-pad">
              <div className="h3 mb-1">Published {fmtDate(d.version.published_at)}</div>
              <p className="sub mb-3">This version is immutable. Improve it by creating a new draft (a copy of its manifest, files and cases); the published version keeps serving until the new one is published.</p>
              <div className="flex flex-wrap gap-3">
                {can(d.ctx.role, "version.create") && <ActionForm action={createDraft} submit="Create improved draft" hidden={{ from_version_id: d.version.id }} />}
                {can(d.ctx.role, "version.retire") && <ActionForm action={retireVersion} submit="Retire version" submitClass="btn btn-danger" hidden={hidden} confirm={`Retire v${d.version.version}? Consumers and the API will no longer be able to run it.`} />}
              </div>
            </div>
          )}
          {(st === "superseded" || st === "retired") && <div className="card card-pad"><div className="h3 mb-1">{st === "superseded" ? "Superseded" : "Retired"}</div><p className="sub">This version is frozen and cannot be run. {can(d.ctx.role, "version.create") && <>Start from it: </>}</p>{can(d.ctx.role, "version.create") && <div className="mt-3"><ActionForm action={createDraft} submit="Create draft from this version" submitClass="btn btn-secondary" hidden={{ from_version_id: d.version.id }} /></div>}</div>}
        </div>
        <aside className="sidebar">
          <div className="card card-pad">
            <div className="h3 mb-2">Approval history</div>
            <div className="list">{approvals.map((a) => (
              <div key={a.id} className="list-row" style={{ display: "block" }}>
                <span className={a.decision === "approve" ? "pass" : "fail"}>{a.decision === "approve" ? "Approved" : "Rejected"}</span> <span className="caption">{fmtDate(a.created_at)}</span>
                <div className="caption">manifest {a.manifest_hash.slice(0, 12)}… {a.manifest_hash === d.version.manifest_hash ? "(current)" : "(stale — manifest changed since)"}</div>
                {a.note && <div className="caption" style={{ overflowWrap: "anywhere" }}>“{a.note}”</div>}
              </div>
            ))}{approvals.length === 0 && <p className="none">No decisions yet.</p>}</div>
          </div>
          <div className="card card-pad">
            <div className="h3 mb-2">Evidence links</div>
            <ul className="stack-sm" style={{ fontSize: 14 }}>
              <li><Link href={`/skills/${slug}/evaluations?v=${d.version.version}`} className="link">Evaluation cases and results</Link></li>
              <li><Link href={`/skills/${slug}/activity?v=${d.version.version}`} className="link">Runs of this version ({d.runCount})</Link></li>
              <li><Link href={`/skills/${slug}/authoring?v=${d.version.version}`} className="link">Contract (manifest)</Link></li>
            </ul>
          </div>
        </aside>
      </div>
    </>
  );
}

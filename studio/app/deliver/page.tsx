import Link from "next/link";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead, SectionHead } from "@/components/PageHead";
import { LocalTime } from "@/components/LocalTime";
import { DeliverForm, type PipelineOption } from "@/components/factory/DeliverForm";
import { ComposeDelivery } from "@/components/factory/ComposeDelivery";
import { REQUEST_KIND_OPTIONS } from "@/lib/delivery/composeData";
import { DeliveryPill } from "@/components/factory/DeliveryPills";
import { PIPELINES } from "@/lib/delivery/pipelines";
import { canStartPipeline } from "@/lib/delivery/core";
import { githubDispatchConfigured } from "@/lib/delivery/config";
import { listDeliveryRuns, listPipelineAccess, listUserRoleSlugs } from "@/lib/db/delivery";
import { loadCatalog } from "@/lib/db/catalog";

export const metadata = { title: "Deliver · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function DeliverPage() {
  const ctx = await requireWorkspace();
  const [runs, access, job, catalog] = await Promise.all([
    listDeliveryRuns(ctx.supabase, ctx.workspace.id), listPipelineAccess(ctx.supabase, ctx.workspace.id),
    listUserRoleSlugs(ctx.supabase, ctx.workspace.id, ctx.user.id), loadCatalog(ctx.supabase, ctx.workspace.id),
  ]);
  const pipelines: PipelineOption[] = PIPELINES.map((p) => ({ name: p.name, title: p.title, version: p.version, mode: p.mode, description: p.description,
    stages: p.stages.map((s) => ({ id: s.id, role: s.role })), allowed: canStartPipeline({ member: ctx.role, job }, access.get(p.name) ?? []) }));
  const repos = catalog.entities.filter((e) => !e.archived).map((e) => ({ key: e.key, title: e.title }));
  const open = runs.filter((r) => ["queued", "running", "awaiting_approval"].includes(r.status)).length;

  return (
    <>
      <PageHead eyebrow={`Build · deliver · ${ctx.workspace.name}`} title="Deliver" em="software" after="."
        lead={<>A request enters a pipeline and leaves it as a pull request carrying gate evidence: stack profile, per-stage verdicts, file hashes, who approved what. {runs.length ? <><b>{runs.length} run{runs.length === 1 ? "" : "s"}</b>, {open} in flight.</> : "No runs yet."}</>}
        caption={<>Templates come from the library (<code>pipelines/*.json</code>); roles own stages; the executor runs on GitHub Actions or your IDE. <Link className="link" href="/glossary#delivery-pipeline">What a delivery pipeline is</Link>.</>} />
      <DeliverForm pipelines={pipelines} repos={repos} githubConfigured={githubDispatchConfigured()} />
      <SectionHead title="No template fits? Compose one" caption="A pipeline assembled from the catalog for the repository's stack and the kind of request (docs/DELIVERY-PIPELINES.md → When no template fits). The decision table says what was chosen, rejected or dropped, and why." />
      <ComposeDelivery repos={repos} kinds={REQUEST_KIND_OPTIONS} githubConfigured={githubDispatchConfigured()} />
      <SectionHead title="Runs" caption="Newest first. Open a run for its stages, evidence and approvals." />
      {runs.length === 0 ? <p className="caption">Nothing delivered through a pipeline yet.</p> : (
        <div className="card tablewrap">
          <table className="tbl">
            <thead><tr><th>Request</th><th>Pipeline</th><th>Repository</th><th>Status</th><th>Stage</th><th>Runs on</th><th>PR</th><th>Started</th></tr></thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td><Link className="link" href={`/deliver/${r.id}`}>{r.request.length > 90 ? `${r.request.slice(0, 90)}…` : r.request}</Link></td>
                  <td className="mono-sm">{r.pipeline} v{r.pipeline_version}</td>
                  <td className="mono-sm">{r.repo}{r.ref ? `@${r.ref}` : ""}</td>
                  <td><DeliveryPill status={r.status} small /></td>
                  <td className="mono-sm">{r.stage ?? "—"}</td>
                  <td className="mono-sm">{r.executor}</td>
                  <td>{r.pr?.url ? <a className="link" href={r.pr.url} target="_blank" rel="noreferrer">#{r.pr.number ?? "PR"}</a> : "—"}</td>
                  <td><LocalTime iso={r.created_at} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

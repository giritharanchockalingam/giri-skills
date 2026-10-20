import Link from "next/link";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { ActionForm } from "@/components/factory/ActionForm";
import { requestAccess } from "@/app/accessActions";
import { loadAccessData } from "@/lib/db/access";
import { allowedKeysFor, rolesCovering } from "@/lib/access";
import { skillFor } from "@/lib/data";
import { humanName } from "@/lib/names";

export const metadata = { title: "Request access · Skills Factory" };
export const dynamic = "force-dynamic";

/** Ask for a job role that covers a skill you cannot run. An admin decides in the Inbox. */
export default async function RequestAccessPage({ searchParams }: { searchParams: Promise<{ skill?: string }> }) {
  const sp = await searchParams;
  const ctx = await requireWorkspace();
  const access = await loadAccessData(ctx.supabase, ctx.workspace.id);
  const id = (sp.skill ?? "").slice(0, 200);
  const lib = id ? skillFor(id) : null;
  const ws = access.skills.find((s) => s.repoSkill === id || s.slug === id);
  const keys = [id, ws?.slug].filter((x): x is string => !!x);
  const title = ws?.title ?? (lib ? humanName(lib.id.split("/")[1]) : id);
  const mine = allowedKeysFor(ctx.user.id, access.roles, access.assignments);
  const held = new Set(access.assignments.filter((a) => a.user_id === ctx.user.id).map((a) => a.talent_id));
  const options = rolesCovering(access.roles, keys).filter((r) => !held.has(r.id));
  const already = keys.some((k) => mine.has(k)) || !access.enabled || ctx.role !== "consumer";

  return (
    <>
      <PageHead eyebrow="Govern · Request access" title="Ask for" em="access" after="."
        lead={<>Job roles decide which approved skills you can run. Ask for one that includes <b>{title || "this skill"}</b>; any admin decides in the Inbox, and the decision is recorded.</>} />
      <section className="card card-pad" style={{ maxWidth: 640 }}>
        {already ? <p className="none" style={{ margin: 0 }}>You can already run this skill. <Link className="link" href={id ? `/repo/${id}/` : "/repo/"}>Open it</Link>.</p>
          : options.length === 0 ? <p className="none" style={{ margin: 0 }}>No published job role includes this skill yet. Ask an admin to add it to one on <Link className="link" href="/roles">Roles</Link>.</p>
          : <ActionForm action={requestAccess} submit="Send request" hidden={{ skill: id }}>
              <div className="field"><label htmlFor="ra-role">Job role</label>
                <select id="ra-role" name="talent_id" className="select" required defaultValue={options.length === 1 ? options[0].id : ""}>
                  {options.length > 1 && <option value="" disabled>Choose…</option>}
                  {options.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.skills.length} skills)</option>)}
                </select></div>
              <div className="field"><label htmlFor="ra-note">Why (optional)</label><input id="ra-note" name="note" className="input" maxLength={1000} placeholder="e.g. month-end close for EMEA" /></div>
            </ActionForm>}
      </section>
      <p className="caption mt-4"><Link className="link" href="/inbox">Your requests are in the Inbox →</Link></p>
    </>
  );
}

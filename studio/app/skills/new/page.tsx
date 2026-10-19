import Link from "next/link";
import { requireWorkspace } from "@/lib/factory/db";
import { can } from "@/lib/factory/roles";
import { createSkill } from "@/app/actions";
import { ActionForm } from "@/components/factory/ActionForm";
import { PageHead } from "@/components/PageHead";

export const metadata = { title: "New skill · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function NewSkillPage() {
  const ctx = await requireWorkspace();
  if (!can(ctx.role, "skill.create")) return <PageHead eyebrow="Skills" title="Authors" em="only" after="." lead={`Your role (${ctx.role}) cannot create skills. Ask an administrator for the author role.`} />;
  return (
    <>
      <PageHead eyebrow="Skills · new" title="Describe the" em="capability" after="." lead="Start with what the skill does and who it is for. The contract (inputs, outputs, steps, limits) comes next in Instructions; nothing runs or publishes until it is defined and tested."
        note={<Link href="/pipeline?import=1" className="link-flame">← Or import a repository skill instead</Link>} />
      <div className="card card-pad" style={{ maxWidth: 720 }}>
        <ActionForm action={createSkill} submit="Create skill">
          <div className="form-grid form-grid-2">
            <div className="field"><label htmlFor="name">Name</label><input id="name" name="name" className="input" required maxLength={160} placeholder="Invoice vs PO check" /></div>
            <div className="field"><label htmlFor="slug">Slug <span className="muted font-normal">(optional)</span></label><input id="slug" name="slug" className="input" maxLength={80} pattern="[a-z0-9-]*" placeholder="invoice-po-check" /><span className="hint">Lowercase letters, digits and dashes. Used in URLs and the API.</span></div>
            <div className="field span-2"><label htmlFor="purpose">Purpose</label><textarea id="purpose" name="purpose" className="textarea" maxLength={2000} placeholder="Validates an invoice against its purchase order and reports every mismatch with a reason." /></div>
            <div className="field"><label htmlFor="intended_users">Intended users</label><textarea id="intended_users" name="intended_users" className="textarea" maxLength={2000} style={{ minHeight: 80 }} placeholder="Accounts-payable analysts" /></div>
            <div className="field"><label htmlFor="usage_guidance">When to use it</label><textarea id="usage_guidance" name="usage_guidance" className="textarea" maxLength={4000} style={{ minHeight: 80 }} placeholder="Before approving an invoice above the auto-approval threshold." /></div>
          </div>
        </ActionForm>
      </div>
    </>
  );
}

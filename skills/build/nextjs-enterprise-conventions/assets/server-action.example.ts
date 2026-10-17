// server/actions/invoice.ts — thin: parse → auth → service → map → revalidate.
"use server";
import { revalidateTag } from "next/cache";
import { createInvoiceSchema } from "@/server/validators/invoice";
import { requireRole } from "@/server/auth";
import * as invoiceService from "@/server/services/invoice.service";
import { fail, toActionState, type ActionState } from "@/lib/result";
import type { InvoiceDto } from "@/server/services/invoice.service";

export async function createInvoiceAction(
  _prev: ActionState<InvoiceDto>,
  formData: FormData,
): Promise<ActionState<InvoiceDto>> {
  // 1. parse
  const parsed = createInvoiceSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) {
    return toActionState(fail("VALIDATION_FAILED", "Check the highlighted fields", { fieldErrors: parsed.error.flatten().fieldErrors }));
  }
  // 2. auth (tenant and user come from the session, never from the form)
  const auth = await requireRole("member");
  if (!auth.ok) return toActionState(auth);
  // 3. service
  const result = await invoiceService.createInvoice(auth.value, parsed.data);
  // 4. revalidate scoped by tenant
  if (result.ok) revalidateTag(`invoices:${auth.value.tenantId}`);
  // 5. serializable state
  return toActionState(result);
}

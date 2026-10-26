// server/services/invoice.service.ts — business rules; returns Result; no HTTP/React knowledge.
import "server-only";
import { ok, fail, type Result } from "@/lib/result";
import { log } from "@/lib/logger";
import * as invoicesDb from "@/lib/db/invoices";
import { writeAudit } from "@/lib/db/audit";
import type { CreateInvoiceInput } from "@/server/validators/invoice";
import type { SessionUser } from "@/server/auth";

export type InvoiceDto = { id: string; number: string; amountCents: number; status: string; createdAt: string };

export async function createInvoice(user: SessionUser, input: CreateInvoiceInput): Promise<Result<InvoiceDto>> {
  const started = Date.now();
  if (user.role === "viewer") return fail("AUTH_FORBIDDEN", "Viewers cannot create invoices");

  const existing = await invoicesDb.findByNumber(user.tenantId, input.number);
  if (!existing.ok) return existing;
  if (existing.value) return fail("CONFLICT", `Invoice ${input.number} already exists`);

  const inserted = await invoicesDb.insert({ ...input, tenantId: user.tenantId, createdBy: user.id });
  if (!inserted.ok) return inserted;

  await writeAudit({ actor: user.id, tenantId: user.tenantId, entity: "invoice", entityId: inserted.value.id, action: "create", after: inserted.value });
  log.info({ action: "invoice.create", invoiceId: inserted.value.id, durationMs: Date.now() - started }, "invoice created");
  return ok(toDto(inserted.value));
}

function toDto(row: invoicesDb.InvoiceRow): InvoiceDto {
  return { id: row.id, number: row.number, amountCents: row.amount_cents, status: row.status, createdAt: row.created_at };
}

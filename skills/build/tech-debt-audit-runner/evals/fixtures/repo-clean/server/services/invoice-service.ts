// Fictional fixture (tech-debt-audit-runner evals): a service composing lib/db.
import { listInvoiceRows, type Invoice } from "@/lib/db/invoices";

export async function listInvoices(tenantId: string): Promise<Invoice[]> {
  const rows = await listInvoiceRows(tenantId);
  return rows.sort((a, b) => (a.issuedAt < b.issuedAt ? 1 : -1));
}

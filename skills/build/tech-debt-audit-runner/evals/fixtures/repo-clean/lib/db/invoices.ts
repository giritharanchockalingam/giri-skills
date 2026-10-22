// Fictional fixture (tech-debt-audit-runner evals): the only place that talks to the database.
import { getClient } from "@/lib/db/client";

export type Invoice = {
  id: string;
  number: string;
  amountCents: number;
  currency: string;
  issuedAt: string;
};

export async function listInvoiceRows(tenantId: string): Promise<Invoice[]> {
  const db = getClient();
  const { data, error } = await db.from("invoices").select("*").eq("tenant_id", tenantId);
  if (error) {
    return [];
  }
  return (data ?? []) as Invoice[];
}

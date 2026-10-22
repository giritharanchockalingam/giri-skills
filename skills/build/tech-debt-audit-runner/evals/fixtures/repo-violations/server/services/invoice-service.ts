// Fictional fixture (tech-debt-audit-runner evals): one half of an import cycle with payment-service (TD3).
import { chargeInvoice } from "./payment-service";
import { computeTotals } from "@/lib/pricing";

export type Invoice = { id: string; amountCents: number; currency: string };

export async function listInvoices(tenantId: string): Promise<Invoice[]> {
  return [{ id: `${tenantId}-1`, amountCents: 1200, currency: "USD" }];
}

export function getInvoice(id: string): Invoice {
  return { id, amountCents: 1200, currency: "USD" };
}

export async function settle(id: string): Promise<number> {
  const inv = getInvoice(id);
  const totals = computeTotals([inv.amountCents], inv.currency);
  return chargeInvoice(inv.id, totals.total);
}

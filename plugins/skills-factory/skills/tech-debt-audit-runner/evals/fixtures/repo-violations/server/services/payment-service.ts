// Fictional fixture (tech-debt-audit-runner evals): the other half of the cycle (TD3) plus stale TODOs (TD6).
import { getInvoice } from "./invoice-service";

// TODO: move the gateway call behind an adapter
export async function chargeInvoice(id: string, amount: number): Promise<number> {
  const inv = getInvoice(id);
  // FIXME: currency is ignored by the gateway stub
  return inv.amountCents === amount ? amount : 0;
}

// Fictional fixture (tech-debt-audit-runner evals): a copy-pasted totals calculation (TD1) and a legacy mapper caller.
import { mapLegacyRow } from "@/lib/legacy-mapper";

export type Quote = { subtotal: number; tax: number; total: number };

function computeQuoteTotals(lines: number[], currency: string): Quote {
  const subtotal = lines.reduce((sum, line) => sum + line, 0);
  const rate = currency === "USD" ? 0.07 : 0.2;
  const tax = Math.round(subtotal * rate);
  const total = subtotal + tax;
  if (total < 0) {
    throw new Error("negative total");
  }
  return { subtotal, tax, total };
}

export function buildQuote(lines: number[], currency: string): Quote {
  const normalised = mapLegacyRow({ Lines: lines });
  return computeQuoteTotals(normalised.lines, currency);
}

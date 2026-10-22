// Fictional fixture (tech-debt-audit-runner evals): the canonical totals calculation — duplicated in quote-service (TD1); untested (TD8).
type Totals = { subtotal: number; tax: number; total: number };

export function computeTotals(lines: number[], currency: string): Totals {
  const subtotal = lines.reduce((sum, line) => sum + line, 0);
  const rate = currency === "USD" ? 0.07 : 0.2;
  const tax = Math.round(subtotal * rate);
  const total = subtotal + tax;
  if (total < 0) {
    throw new Error("negative total");
  }
  return { subtotal, tax, total };
}

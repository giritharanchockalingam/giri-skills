// Fictional fixture (tech-debt-audit-runner evals): small, tested formatting helpers.
export function formatMoney(amountCents: number, currency: string): string {
  const amount = amountCents / 100;
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amount);
}

export function formatDate(iso: string): string {
  return new Date(iso).toISOString().slice(0, 10);
}

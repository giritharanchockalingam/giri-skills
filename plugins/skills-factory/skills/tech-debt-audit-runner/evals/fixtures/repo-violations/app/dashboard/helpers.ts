// Fictional fixture (tech-debt-audit-runner evals): a route-local helper that the reports route also reaches into.
export function summarise(amounts: number[]): { count: number; total: number } {
  return { count: amounts.length, total: amounts.reduce((a, b) => a + b, 0) };
}

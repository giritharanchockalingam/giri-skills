// fictional fixture — a clean helper: must produce no findings (perf-review-runner evals)
export function money(n: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
}

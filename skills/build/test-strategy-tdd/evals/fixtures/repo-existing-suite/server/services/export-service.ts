// FICTIONAL example source for evals.
export function toCsv(rows: { id: string; number: string }[]): string {
  return ["id,number", ...rows.map((r) => `${r.id},${r.number}`)].join("\n");
}

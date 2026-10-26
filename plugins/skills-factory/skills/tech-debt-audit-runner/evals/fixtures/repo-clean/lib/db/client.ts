// Fictional fixture (tech-debt-audit-runner evals): a thin client factory.
type Query = { select: (cols: string) => Query; eq: (col: string, v: string) => Promise<{ data: unknown[]; error: null | Error }> };
type Client = { from: (table: string) => Query };

export function getClient(): Client {
  const query: Query = {
    select: () => query,
    eq: async () => ({ data: [], error: null }),
  };
  return { from: () => query };
}

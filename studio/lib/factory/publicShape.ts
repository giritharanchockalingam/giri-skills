/* What the consumer API exposes. Workspace ids, policy settings and runtime file paths are internal: an
 * application calling a skill needs the contract and its results, not how the workspace is configured. */

const INTERNAL_KEYS = new Set(["workspace_id", "policy", "skill_id"]);

/** Contract response: drop internal keys at the top level. */
export function publicContract(data: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(data).filter(([k]) => !INTERNAL_KEYS.has(k)));
}

/** Replace runtime paths like /tmp/sf/<run>/out/x.json with x.json (and /tmp/sf/<run>/inputs/… with inputs/…). */
export function stripRuntimePaths<T>(value: T): T {
  const fix = (s: string) => s.replace(/\/tmp\/sf\/[0-9a-f-]+\/out\//g, "").replace(/\/tmp\/sf\/[0-9a-f-]+\//g, "").replace(/\/var\/lang\/bin\/python/g, "python");
  const walk = (v: unknown): unknown =>
    typeof v === "string" ? fix(v) : Array.isArray(v) ? v.map(walk) : v && typeof v === "object" ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, walk(x)])) : v;
  return walk(value) as T;
}

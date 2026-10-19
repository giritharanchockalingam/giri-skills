/* What a repository is, from its file paths (+ root manifests when present), and which skills apply to it.
 * Pure and deterministic: the same tree always gives the same answer. Every match carries the evidence (the paths
 * that triggered it) so the catalog can show WHY a skill applies — nothing is inferred without a file behind it. */

export interface Signal { id: string; label: string; evidence: string[] }
export interface Applicable { skill: string; why: string; evidence: string[]; input: { name: string; path: string } | null }
export interface Detection { stack: Signal[]; applicable: Applicable[]; counts: { files: number; tests: number; migrations: number; workflows: number } }

const MAX_EVIDENCE = 3;
const has = (paths: string[], re: RegExp) => paths.filter((p) => re.test(p));
const deps = (pkg: string | null): Record<string, string> => {
  if (!pkg) return {};
  try { const j = JSON.parse(pkg) as { dependencies?: Record<string, string>; devDependencies?: Record<string, string> }; return { ...j.dependencies, ...j.devDependencies }; }
  catch { return {}; }
};

/** Common prefix directory of a set of paths (e.g. "supabase/migrations"). */
const dirOf = (paths: string[]) => {
  if (!paths.length) return "";
  const parts = paths[0].split("/").slice(0, -1);
  let n = parts.length;
  for (const p of paths) { const q = p.split("/"); while (n && q.slice(0, n).join("/") !== parts.slice(0, n).join("/")) n--; }
  return parts.slice(0, n).join("/");
};

export function detect(paths: string[], manifests: { packageJson?: string | null; requirements?: string | null; pyproject?: string | null } = {}): Detection {
  const ignore = /(^|\/)(node_modules|\.next|dist|build|vendor|\.venv|__pycache__)\//;
  const P = paths.filter((p) => !ignore.test(p));
  const d = deps(manifests.packageJson ?? null);
  const py = `${manifests.requirements ?? ""}\n${manifests.pyproject ?? ""}`.toLowerCase();
  const stack: Signal[] = [];
  const add = (id: string, label: string, evidence: string[]) => { if (evidence.length) stack.push({ id, label, evidence: evidence.slice(0, MAX_EVIDENCE) }); };

  const migrations = has(P, /(^|\/)supabase\/migrations\/[^/]+\.sql$/);
  const workflows = has(P, /^\.github\/workflows\/[^/]+\.ya?ml$/);
  const tests = has(P, /(^|\/)(tests?|__tests__|e2e)\/|\.(test|spec)\.[jt]sx?$|(^|\/)test_[^/]+\.py$|_test\.(py|go)$/);
  const nextCfg = has(P, /(^|\/)next\.config\.(js|mjs|ts|cjs)$/);

  add("nextjs", "Next.js", [...nextCfg, ...(d.next ? ["package.json: next"] : [])]);
  add("react", "React", d.react ? ["package.json: react"] : []);
  add("typescript", "TypeScript", has(P, /(^|\/)tsconfig\.json$/));
  add("supabase", "Supabase", [...migrations, ...has(P, /(^|\/)supabase\/config\.toml$/), ...(d["@supabase/supabase-js"] ? ["package.json: @supabase/supabase-js"] : [])]);
  add("python", "Python", [...has(P, /(^|\/)(requirements[^/]*\.txt|pyproject\.toml|setup\.py)$/), ...has(P, /\.py$/).slice(0, 1)]);
  add("langgraph", "LangGraph", [...(d["@langchain/langgraph"] ? ["package.json: @langchain/langgraph"] : []), ...(/\blanggraph\b/.test(py) ? ["python deps: langgraph"] : [])]);
  add("langchain", "LangChain", [...(d.langchain || d["@langchain/core"] ? ["package.json: langchain"] : []), ...(/\blangchain\b/.test(py) ? ["python deps: langchain"] : [])]);
  add("mcp", "MCP server", [...(d["@modelcontextprotocol/sdk"] ? ["package.json: @modelcontextprotocol/sdk"] : []), ...(/\bmcp\b|fastmcp/.test(py) ? ["python deps: mcp"] : [])]);
  add("llm", "LLM SDK", Object.keys(d).filter((k) => /^(openai|@anthropic-ai\/sdk|ai|@ai-sdk\/.+)$/.test(k)).map((k) => `package.json: ${k}`)
    .concat(/\b(openai|anthropic)\b/.test(py) ? ["python deps: openai/anthropic"] : []));
  add("github-actions", "GitHub Actions", workflows);
  add("vercel", "Vercel", has(P, /(^|\/)vercel\.json$/));
  add("docker", "Docker", has(P, /(^|\/)(Dockerfile|docker-compose\.ya?ml|compose\.ya?ml)$/));
  add("terraform", "Terraform", has(P, /\.tf$/));
  add("tests", "Tests", tests);
  add("agent-skills", "Agent skills", has(P, /(^|\/)SKILL\.md$/));
  add("prd", "Product docs", has(P, /(^|\/)(docs\/)?(prd|PRD|spec|SPEC)[^/]*\.md$|(^|\/)docs\/prd\//));

  const s = new Set(stack.map((x) => x.id));
  const ev = (id: string) => stack.find((x) => x.id === id)?.evidence ?? [];
  const applicable: Applicable[] = [];
  const app = (skill: string, why: string, evidence: string[], input: Applicable["input"] = null) => applicable.push({ skill, why, evidence: evidence.slice(0, MAX_EVIDENCE), input });

  if (migrations.length) {
    app("build/supabase-schema-rls", `${migrations.length} Supabase migration${migrations.length === 1 ? "" : "s"} to check for row-level security`, migrations, { name: "migrations", path: dirOf(migrations) });
    app("build/multi-tenant-saas-patterns", "Supabase schema: check tenant isolation, roles and plan checks", migrations, { name: "migrations", path: dirOf(migrations) });
  }
  if (s.has("nextjs")) app("build/nextjs-enterprise-conventions", "Next.js app: check against enterprise conventions", ev("nextjs"));
  if (workflows.length || s.has("vercel")) app("build/ci-cd-vercel-github", workflows.length ? "Existing CI workflows to review and harden" : "Deployed on Vercel without CI workflows", [...workflows, ...ev("vercel")]);
  if (!workflows.length && (s.has("nextjs") || s.has("python"))) app("build/ci-cd-vercel-github", "No CI workflow found", ["no .github/workflows/*.yml"]);
  if (!tests.length && P.length > 5) app("build/test-strategy-tdd", "No tests found", ["no test files"]);
  if (s.has("langgraph")) app("ai-platform/langgraph-runner", "LangGraph agent: validate the graph", ev("langgraph"));
  if (s.has("langchain")) app("ai-platform/langchain-rag-runner", "LangChain code: RAG plan against what exists", ev("langchain"));
  if (s.has("mcp")) app("ai-platform/mcp-server-builder", "MCP server: check tool contracts, auth and errors", ev("mcp"));
  if (s.has("llm")) {
    app("ai-platform/guardrails-config", "Calls an LLM: input/output guardrails", ev("llm"));
    app("ai-platform/llm-eval-harness", "Calls an LLM: golden set and regression gate", ev("llm"));
  }
  if (s.has("prd")) app("build/product-spec-prd", "Product docs to redline", ev("prd"));
  if (P.length) app("build/security-review", "Every codebase: security review of changes", P.slice(0, 1));
  // one entry per skill (first reason wins)
  const seen = new Set<string>();
  const unique = applicable.filter((a) => (seen.has(a.skill) ? false : (seen.add(a.skill), true)));
  return { stack, applicable: unique, counts: { files: P.length, tests: tests.length, migrations: migrations.length, workflows: workflows.length } };
}

/** The owner a CODEOWNERS file assigns to the whole repository (the last `*` rule wins, as GitHub applies it). */
export function defaultOwner(codeowners: string | null): string | null {
  if (!codeowners) return null;
  let owner: string | null = null;
  for (const raw of codeowners.split(/\r?\n/)) {
    const line = raw.replace(/#.*$/, "").trim();
    if (!line) continue;
    const [pattern, ...owners] = line.split(/\s+/);
    if ((pattern === "*" || pattern === "/*" || pattern === "/") && owners.length) owner = owners.join(" ");
  }
  return owner;
}

export const CODEOWNERS_PATHS = [".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"];

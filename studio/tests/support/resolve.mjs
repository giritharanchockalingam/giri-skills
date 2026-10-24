import { statSync } from "node:fs";
import { fileURLToPath } from "node:url";

const ROOT = new URL("../../", import.meta.url);
const isFile = (u) => { try { return statSync(fileURLToPath(u)).isFile(); } catch { return false; } };
function withExt(url) {
  if (isFile(url)) return url;
  for (const ext of [".ts", ".tsx", ".json", "/index.ts"]) { const u = new URL(url.href + ext); if (isFile(u)) return u; }
  return null;
}
export async function resolve(specifier, context, next) {
  if (specifier === "server-only") return { url: "data:text/javascript,", shortCircuit: true };
  let base = null;
  if (specifier.startsWith("@/")) base = new URL(specifier.slice(2), ROOT);
  else if ((specifier.startsWith("./") || specifier.startsWith("../")) && context.parentURL?.startsWith("file:") && !/\.[cm]?[jt]sx?$|\.json$/.test(specifier)) base = new URL(specifier, context.parentURL);
  if (base) { const u = withExt(base); if (u) return { url: u.href, shortCircuit: true, ...(u.href.endsWith(".json") ? { importAttributes: { type: "json" } } : {}) }; }
  const r = await next(specifier, context);
  // Next/tsconfig let `import x from "./y.json"` stand without an attribute; Node's loader wants `type: "json"`
  if (r.url?.endsWith(".json") && !context.importAttributes?.type) return { ...r, importAttributes: { type: "json" } };
  return r;
}


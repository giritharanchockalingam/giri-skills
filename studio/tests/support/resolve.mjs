import { statSync } from "node:fs";
import { fileURLToPath } from "node:url";

const ROOT = new URL("../../", import.meta.url);
const isFile = (u) => { try { return statSync(fileURLToPath(u)).isFile(); } catch { return false; } };
function withExt(url) {
  if (isFile(url)) return url;
  for (const ext of [".ts", ".tsx", "/index.ts"]) { const u = new URL(url.href + ext); if (isFile(u)) return u; }
  return null;
}
export async function resolve(specifier, context, next) {
  if (specifier === "server-only") return { url: "data:text/javascript,", shortCircuit: true };
  let base = null;
  if (specifier.startsWith("@/")) base = new URL(specifier.slice(2), ROOT);
  else if ((specifier.startsWith("./") || specifier.startsWith("../")) && context.parentURL?.startsWith("file:") && !/\.[cm]?[jt]sx?$|\.json$/.test(specifier)) base = new URL(specifier, context.parentURL);
  if (base) { const u = withExt(base); if (u) return { url: u.href, shortCircuit: true }; }
  return next(specifier, context);
}


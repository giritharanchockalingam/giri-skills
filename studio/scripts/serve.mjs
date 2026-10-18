// Zero-dependency static server for the exported site (out/). Usage: npm run start [-- PORT]
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { join, extname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..", "out");
const port = Number(process.argv[2] || process.env.PORT || 4173);
const types = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
  ".woff2": "font/woff2", ".txt": "text/plain", ".wasm": "application/wasm", ".mjs": "text/javascript", ".zip": "application/zip",
  ".md": "text/markdown; charset=utf-8", ".csv": "text/csv; charset=utf-8", ".py": "text/plain; charset=utf-8",
};

createServer(async (req, res) => {
  let path = decodeURIComponent(new URL(req.url, "http://x").pathname);
  const candidates = [path, join(path, "index.html"), `${path.replace(/\/$/, "")}.html`, "/404.html"];
  for (const c of candidates) {
    const file = join(root, c);
    try {
      const s = await stat(file);
      if (!s.isFile()) continue;
      res.writeHead(c === "/404.html" ? 404 : 200, { "content-type": types[extname(file)] || "application/octet-stream" });
      res.end(await readFile(file));
      return;
    } catch { /* try next */ }
  }
  res.writeHead(404); res.end("not found");
}).listen(port, () => console.log(`serving ${root} on http://localhost:${port}`));

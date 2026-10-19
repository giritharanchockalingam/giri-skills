import { readFileSync } from "node:fs";
import { join } from "node:path";
import Link from "next/link";
import { PageHead } from "@/components/PageHead";
import { mdToHtml } from "@/lib/markdown.mjs";

export const metadata = { title: "API reference · Connect · Skills Factory" };
export const dynamic = "force-static";   // rendered from docs/API.md at build time: the page and the repository never disagree

/** The consumer API reference, in the portal (source of truth: studio/docs/API.md). */
export default function ApiDocsPage() {
  const md = readFileSync(join(process.cwd(), "docs", "API.md"), "utf8").replace(/^# .*\n/, "");
  return (
    <>
      <PageHead eyebrow="Connect · API reference" title="Call published skills over" em="HTTP" after="."
        lead="Endpoints, authentication, request and response shapes, error codes and curl examples. The same runs, limits and records as the portal and MCP." />
      <p className="caption mb-4"><Link className="link" href="/connect">← Connect</Link> · Create an API key in <Link className="link" href="/admin#keys">Admin</Link>.</p>
      <article className="card card-pad prose" dangerouslySetInnerHTML={{ __html: mdToHtml(md) }} />
    </>
  );
}

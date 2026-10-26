import { siteUrl } from "@/lib/format";

export default function robots() {
  return { rules: [{ userAgent: "*", allow: "/", disallow: ["/api"] }], sitemap: `${siteUrl()}/sitemap.xml` };
}

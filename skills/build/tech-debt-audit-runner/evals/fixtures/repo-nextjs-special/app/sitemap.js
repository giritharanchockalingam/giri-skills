import { siteUrl } from "@/lib/format";

export async function generateSitemaps() {
  return [{ id: 0 }];
}

export default function sitemap() {
  return [{ url: siteUrl(), lastModified: new Date("2026-01-01") }];
}

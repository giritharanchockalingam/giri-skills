export function formatDate(iso) {
  return new Date(iso).toISOString().slice(0, 10);
}

export function siteUrl() {
  return process.env.SITE_URL || "https://example.com";
}

/* Where the factory tells Port to find it, and which GitHub repository Port's Skills registry scanned. */
export const portalBase = (req: { url: string; headers: { get(n: string): string | null } }) => {
  const h = req.headers;
  const proto = h.get("x-forwarded-proto") ?? "https", host = h.get("x-forwarded-host") ?? h.get("host");
  return process.env.SF_RUNTIME_URL?.trim() || (host ? `${proto}://${host}` : new URL(req.url).origin);
};
/** `<owner>/<repo>` whose SKILL.md files Port's registry (`skill` blueprint) lists; unset → no registry relation is written. */
export const registryRepo = () => process.env.PORT_REGISTRY_REPO?.trim() || null;

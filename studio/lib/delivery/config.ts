/* Server-side facts about the executor configuration (env names in ./dispatch) and this deployment's own address. */
import { headers } from "next/headers";
import { DELIVERY_ENV } from "./dispatch";

export const githubDispatchConfigured = (): boolean => Boolean(process.env[DELIVERY_ENV.token]);

/** The portal's public origin for callbacks and IDE commands (request headers; SF_RUNTIME_URL as the fallback). */
export async function portalUrl(): Promise<string> {
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "";
  if (!host) return (process.env.SF_RUNTIME_URL ?? "http://localhost:3000").replace(/\/+$/, "");
  const proto = h.get("x-forwarded-proto") ?? (/^(localhost|127\.)/.test(host) ? "http" : "https");
  return `${proto}://${host}`;
}

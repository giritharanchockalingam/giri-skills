/* Port webhook signatures (docs.port.io → Validate webhook signatures): HMAC-SHA256 over `${timestamp}.${rawBody}` with
 * the Port client secret, Base64, header `x-port-signature: v1,<sig>`, plus `x-port-timestamp` (seconds). Pure. */
import { createHmac, timingSafeEqual } from "node:crypto";

export function portSignature(secret: string, timestamp: string, rawBody: string): string {
  return createHmac("sha256", secret).update(`${timestamp}.${rawBody}`).digest("base64");
}

/** null when valid; otherwise why not. Rejects stale timestamps (replay) beyond `toleranceSec`. */
export function verifyPortSignature(opts: { secret: string; timestamp: string | null; signature: string | null; rawBody: string; nowSec: number; toleranceSec?: number }): string | null {
  const { secret, timestamp, signature, rawBody, nowSec, toleranceSec = 300 } = opts;
  if (!timestamp || !signature) return "missing x-port-timestamp or x-port-signature";
  if (!/^\d{9,11}$/.test(timestamp)) return "bad timestamp";
  if (Math.abs(nowSec - Number(timestamp)) > toleranceSec) return "timestamp outside the allowed window";
  const given = signature.includes(",") ? signature.split(",")[1] : signature;
  const want = portSignature(secret, timestamp, rawBody);
  const a = Buffer.from(given), b = Buffer.from(want);
  return a.length === b.length && timingSafeEqual(a, b) ? null : "signature mismatch";
}

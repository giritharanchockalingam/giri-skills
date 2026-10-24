/* Bearer check for the operator-only Port routes (sync drain, reconcile). Accepts the operator token
 * (HEALTH_CHECK_TOKEN, the same one the deep health check uses) or Vercel's cron secret. Constant-time compare. */
import { timingSafeEqual } from "node:crypto";

const same = (a: string, b: string) => a.length === b.length && timingSafeEqual(Buffer.from(a), Buffer.from(b));

export function operatorAuthorized(authorization: string | null, env: Record<string, string | undefined> = process.env): { ok: true } | { ok: false; status: number; message: string } {
  const presented = authorization?.match(/^Bearer\s+(\S+)$/i)?.[1] ?? "";
  const tokens = [env.HEALTH_CHECK_TOKEN, env.CRON_SECRET].map((t) => t?.trim()).filter((t): t is string => !!t);
  if (!tokens.length) return { ok: false, status: 401, message: "set HEALTH_CHECK_TOKEN (or CRON_SECRET) to enable operator routes" };
  return presented && tokens.some((t) => same(t, presented)) ? { ok: true } : { ok: false, status: 401, message: "unauthorized" };
}

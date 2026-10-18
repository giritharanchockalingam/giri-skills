/* Hashing (server only: node:crypto). manifestHash is what sf_skill_versions.manifest_hash stores and what
 * approvals pin to — any change to the canonical manifest changes it and makes the approval stale. */
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { canonicalJson } from "./manifest.ts";

export const sha256 = (s: string | Uint8Array) => createHash("sha256").update(s).digest("hex");
export const manifestHash = (manifest: unknown) => sha256(canonicalJson(manifest));

/** API keys: `sf_live_` + 32 random bytes (base64url). Only the sha256 is stored; the prefix is shown in lists. */
export const API_KEY_PREFIX = "sf_live_";
export function generateApiKey(): { key: string; hash: string; prefix: string } {
  const key = API_KEY_PREFIX + randomBytes(32).toString("base64url");
  return { key, hash: sha256(key), prefix: key.slice(0, API_KEY_PREFIX.length + 6) };
}
export const looksLikeApiKey = (s: string) => s.startsWith(API_KEY_PREFIX) && s.length >= API_KEY_PREFIX.length + 40 && /^[A-Za-z0-9_-]+$/.test(s.slice(API_KEY_PREFIX.length));
export const apiKeyHash = (key: string) => sha256(key);

export function secretsEqual(a: string, b: string): boolean {
  const ba = Buffer.from(a), bb = Buffer.from(b);
  return ba.length === bb.length && timingSafeEqual(ba, bb);
}

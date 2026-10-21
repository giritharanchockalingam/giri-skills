import { test } from "node:test";
import assert from "node:assert/strict";
import { classifyAuthError, authMessage } from "../lib/authError.ts";

test("sign-in failures become a friendly message; raw provider text is never shown", () => {
  assert.equal(classifyAuthError("PKCE code verifier not found in storage. This can happen if the auth flow was initiated in another browser or device, or the storage was cleared. For SSR frameworks (Next.js, SvelteKit, etc.), use @supabase/ssr on both the server and client to store the code verifier in cookies."), "other_browser");
  assert.equal(classifyAuthError("Email link is invalid or has expired"), "expired");
  assert.equal(classifyAuthError("something odd"), "failed");
  for (const code of ["other_browser", "expired", "failed", "PKCE code verifier not found <script>"]) {
    const m = authMessage(code)!;
    assert.doesNotMatch(m, /pkce|verifier|supabase|auth_error|<script>/i);
    assert.match(m, /link|set up/);
  }
  assert.equal(authMessage(null), null);
});

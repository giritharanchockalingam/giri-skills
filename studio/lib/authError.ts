/* Sign-in link failures, for people: the raw provider message is logged on the server and never shown. Pure. */
export type AuthFailure = "other_browser" | "expired" | "not_configured" | "failed";

export function classifyAuthError(raw: string): AuthFailure {
  if (/code verifier|pkce|both auth code and code verifier/i.test(raw)) return "other_browser";
  if (/expired|invalid|already been used|otp|not found/i.test(raw)) return "expired";
  if (/not configured/i.test(raw)) return "not_configured";
  return "failed";
}

export const AUTH_MESSAGE: Record<AuthFailure, string> = {
  other_browser: "That sign-in link didn't complete: it was opened in a different browser (or app) from the one that asked for it. Request a fresh link below and open it in this browser.",
  expired: "That sign-in link has expired or was already used. Request a fresh link below.",
  not_configured: "Sign-in is not set up on this deployment yet.",
  failed: "That sign-in link didn't complete. Request a fresh link below.",
};

export const authMessage = (code: string | null | undefined) => (code ? AUTH_MESSAGE[(code in AUTH_MESSAGE ? code : "failed") as AuthFailure] : null);

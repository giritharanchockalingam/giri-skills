"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { createBrowserSupabase } from "@/lib/supabase/client";

type Mode = "signin" | "signup" | "magic";

export function LoginForm({ next }: { next: string }) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setMsg(null);
    const sb = createBrowserSupabase();
    try {
      if (mode === "magic") {
        const { error } = await sb.auth.signInWithOtp({ email, options: { emailRedirectTo: `${window.location.origin}${next}` } });
        if (error) throw error;
        setMsg({ ok: true, text: "Check your inbox for the sign-in link." });
      } else if (mode === "signup") {
        const { data, error } = await sb.auth.signUp({ email, password, options: { emailRedirectTo: `${window.location.origin}${next}` } });
        if (error) throw error;
        if (data.session) { router.push(next); router.refresh(); }
        else setMsg({ ok: true, text: "Account created. Confirm the email we sent, then sign in." });
      } else {
        const { error } = await sb.auth.signInWithPassword({ email, password });
        if (error) throw error;
        router.push(next); router.refresh();
      }
    } catch (err) {
      setMsg({ ok: false, text: (err as Error).message });
    } finally { setBusy(false); }
  };

  return (
    <form className="card card-pad stack" onSubmit={submit} aria-describedby="login-msg">
      <div className="chip-group" role="group" aria-label="Sign-in method">
        {([["signin", "Password"], ["magic", "Email link"], ["signup", "Create account"]] as [Mode, string][]).map(([k, l]) => (
          <button key={k} type="button" className="chip" aria-pressed={mode === k} onClick={() => { setMode(k); setMsg(null); }}>{l}</button>
        ))}
      </div>
      <div className="field">
        <label htmlFor="email">Email</label>
        <input id="email" className="input" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </div>
      {mode !== "magic" && (
        <div className="field">
          <label htmlFor="password">Password</label>
          <input id="password" className="input" type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
          {mode === "signup" && <span className="hint">At least 8 characters. Your administrator then adds you to a workspace with a role.</span>}
        </div>
      )}
      <div className="action-row" style={{ marginTop: 0 }}>
        <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "Working…" : mode === "signup" ? "Create account" : mode === "magic" ? "Send sign-in link" : "Sign in"}</button>
      </div>
      <div id="login-msg" role="status" aria-live="polite">{msg && <div className={`notice ${msg.ok ? "notice-ok" : "notice-err"}`}>{msg.text}</div>}</div>
    </form>
  );
}

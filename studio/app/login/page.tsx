import { LoginForm } from "@/components/factory/LoginForm";
import { supabaseConfigured } from "@/lib/supabase/env";

export const metadata = { title: "Sign in · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string; setup?: string; auth_error?: string }> }) {
  const sp = await searchParams;
  const configured = supabaseConfigured();
  return (
    <div style={{ maxWidth: 440, margin: "0 auto" }}>
      <div className="page-head">
        <div className="eyebrow">Skills Factory</div>
        <h1 className="h1">Sign <em>in</em>.</h1>
        <p className="lead">Skills, versions, evaluations and runs live in your workspace. Sign in with the account your administrator added, or create one.</p>
        <p className="caption"><a className="link-flame" href="/start">New to the portal? How it fits together →</a></p>
      </div>
      {sp.auth_error && <div className="notice notice-err" role="alert" style={{ marginBottom: 16 }}>Sign-in link failed: {sp.auth_error}. Request a new link and open it once, in this browser.</div>}
      {configured ? (
        <LoginForm next={sp.next && sp.next.startsWith("/") ? sp.next : "/"} />
      ) : (
        <div className="card card-pad">
          <div className="h3">Setup required</div>
          <p className="sub mt-2">Authentication is not configured on this deployment. Set <code>NEXT_PUBLIC_SUPABASE_URL</code> and <code>NEXT_PUBLIC_SUPABASE_ANON_KEY</code> (see README → Setup), redeploy, then sign in.</p>
        </div>
      )}
    </div>
  );
}

"use client";
/* What a person sees when the page throws in the browser: what happened, that a submitted change is safe if the
 * server confirmed it, and how to recover. The error is reported to the server log once. */
import { useEffect } from "react";

export function reportClientError(error: Error & { digest?: string }) {
  try {
    const body = JSON.stringify({ message: error.message, digest: error.digest, stack: error.stack, path: location.pathname });
    if (!navigator.sendBeacon?.("/api/client-error", new Blob([body], { type: "application/json" })))
      void fetch("/api/client-error", { method: "POST", body, headers: { "content-type": "application/json" }, keepalive: true });
  } catch { /* reporting must never throw */ }
}

export function ErrorRecovery({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { reportClientError(error); }, [error]);
  return (
    <div className="page-head" role="alert">
      <div className="eyebrow">Something went wrong</div>
      <h1 className="h1">This page hit an <em>error</em>.</h1>
      <p className="sub">It happened in your browser, after the page loaded. Anything you submitted that the server confirmed is saved; reload to see the current state. The error has been recorded for us.</p>
      <div className="action-row mt-3">
        <button type="button" className="btn btn-primary" onClick={() => location.reload()}>Reload the page</button>
        <button type="button" className="btn btn-secondary" onClick={() => reset()}>Try again without reloading</button>
        <a className="link" href="/">Home</a>
      </div>
      {error.digest && <p className="caption mt-3">Reference: <code>{error.digest}</code></p>}
    </div>
  );
}

"use client";
/* Last resort when the root layout itself fails: a self-contained page (its own html/body) with the same recovery. */
import "./globals.css";
import { ErrorRecovery } from "@/components/ErrorRecovery";
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <html lang="en"><body><main className="wrap"><ErrorRecovery error={error} reset={reset} /></main></body></html>;
}

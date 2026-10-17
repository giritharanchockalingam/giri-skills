"use client";
import { useState } from "react";

export function CopyButton({ text }: { text: string }) {
  const [state, setState] = useState<"idle" | "ok" | "err">("idle");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setState("ok");
    } catch {
      setState("err");
    }
    setTimeout(() => setState("idle"), 1500);
  };
  return (
    <button type="button" className={`btn btn-secondary ${state === "ok" ? "is-ok" : state === "err" ? "is-err" : ""}`} onClick={copy} aria-live="polite">
      {state === "ok" ? "Copied" : state === "err" ? "Copy failed" : "Copy"}
    </button>
  );
}

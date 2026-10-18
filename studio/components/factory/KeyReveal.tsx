"use client";
import { CopyButton } from "@/components/CopyButton";

/** Shown exactly once, right after creation. */
export function KeyReveal({ value }: { value: string }) {
  return (
    <div className="notice notice-hold mt-3">
      <div><b>Copy this key now.</b> It will not be shown again; only its hash is stored.</div>
      <div className="key-reveal mt-2">{value}</div>
      <div className="mt-2"><CopyButton text={value} /></div>
    </div>
  );
}

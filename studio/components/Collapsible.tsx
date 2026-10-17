"use client";
import { useState } from "react";

export function Collapsible({ title, defaultOpen = false, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="card">
      <button type="button" className="flex w-full items-center gap-3 px-6 py-4 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className={`caret ${open ? "open" : ""}`} aria-hidden="true">▶</span>
        <span className="card-title">{title}</span>
      </button>
      {open && <div className="border-t border-rule-soft px-6 py-5">{children}</div>}
    </div>
  );
}

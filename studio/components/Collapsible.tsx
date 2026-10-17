"use client";
import { useState } from "react";

export function Collapsible({ title, caption, defaultOpen = false, children }: { title: string; caption?: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="card">
      <button type="button" className="collapsible-btn" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className={`caret ${open ? "open" : ""}`} aria-hidden="true">▶</span>
        <span className="min-w-0">
          <span className="card-title block">{title}</span>
          {caption && <span className="caption block">{caption}</span>}
        </span>
      </button>
      {open && <div className="border-t border-rule-soft px-6 py-5 max-md:px-[18px]">{children}</div>}
    </div>
  );
}

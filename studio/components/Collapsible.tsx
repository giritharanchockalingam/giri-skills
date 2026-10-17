"use client";
import { useState } from "react";

export function Collapsible({ title, defaultOpen = false, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="panel">
      <button type="button" className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12.5px] font-semibold" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="muted">{open ? "▾" : "▸"}</span>{title}
      </button>
      {open && <div className="border-t border-line">{children}</div>}
    </div>
  );
}

"use client";
import { useEffect, useRef, useState } from "react";

/** One paragraph clamped to `lines`; a "more" control appears only when the text actually overflows. */
export function ClampText({ text, lines = 2, className = "" }: { text: string; lines?: number; className?: string }) {
  const ref = useRef<HTMLParagraphElement>(null);
  const [open, setOpen] = useState(false);
  const [overflows, setOverflows] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const check = () => setOverflows(el.scrollHeight > el.clientHeight + 1);
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, [text, open]);
  return (
    <div className={`detail-desc-wrap ${className}`}>
      <p ref={ref} className={`detail-desc ${open ? "" : "is-clamped"}`} style={open ? undefined : { WebkitLineClamp: lines }}>{text}</p>
      {(overflows || open) && (
        <button type="button" className="btn-link btn-more" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "less" : "more"}</button>
      )}
    </div>
  );
}

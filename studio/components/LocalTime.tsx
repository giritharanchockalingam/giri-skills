"use client";
/* A timestamp in the viewer's own time zone. The server (UTC) cannot know the viewer's zone, so its render holds the
 * space but stays invisible until the browser formats it: no wrong (UTC) first paint, no layout shift. */
import { useEffect, useState } from "react";

const OPTS: Intl.DateTimeFormatOptions = { dateStyle: "medium", timeStyle: "short" };
export function LocalTime({ iso, empty = "—" }: { iso: string | null | undefined; empty?: string }) {
  const [local, setLocal] = useState<{ text: string; zone: string } | null>(null);
  useEffect(() => {
    if (!iso) return;
    setLocal({ text: new Date(iso).toLocaleString("en-US", OPTS), zone: Intl.DateTimeFormat().resolvedOptions().timeZone });
  }, [iso]);
  if (!iso) return <>{empty}</>;
  // placeholder text has the same shape as the real value, so nothing moves when it appears
  const text = local?.text ?? new Date(iso).toLocaleString("en-US", { ...OPTS, timeZone: "UTC" });
  return <time dateTime={iso} title={local ? `${local.zone} · ${iso}` : iso} className={local ? undefined : "lt-pending"} suppressHydrationWarning>{text}</time>;
}

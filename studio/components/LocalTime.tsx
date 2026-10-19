"use client";
/* A timestamp in the viewer's own time zone. The server (which runs in UTC) renders it labelled "UTC" so the first
 * paint is never wrong; the browser then shows local time, with the zone in the tooltip. */
import { useEffect, useState } from "react";

const OPTS: Intl.DateTimeFormatOptions = { dateStyle: "medium", timeStyle: "short" };
export function LocalTime({ iso, empty = "—" }: { iso: string | null | undefined; empty?: string }) {
  const [text, setText] = useState(() => (iso ? `${new Date(iso).toLocaleString("en-US", { ...OPTS, timeZone: "UTC" })} UTC` : empty));
  const [zone, setZone] = useState("UTC");
  useEffect(() => {
    if (!iso) return;
    setText(new Date(iso).toLocaleString("en-US", OPTS));
    setZone(Intl.DateTimeFormat().resolvedOptions().timeZone);
  }, [iso]);
  return iso ? <time dateTime={iso} title={`${zone} · ${iso}`} suppressHydrationWarning>{text}</time> : <>{empty}</>;
}

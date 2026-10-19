"use client";
/* Score repositories one by one (each a separate request, within the server's time limit), showing progress. */
import { useState } from "react";
import { useRouter } from "next/navigation";
import { scoreRepository } from "@/app/catalog/actions";

export function ScoreAll({ entities, label = "Run scorecards" }: { entities: { id: string; key: string }[]; label?: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const go = async () => {
    setBusy(true); setLog([]);
    for (const [i, e] of entities.entries()) {
      setLog((l) => [...l, `${i + 1}/${entities.length} ${e.key}: scoring…`]);
      const r = await scoreRepository(e.id);
      setLog((l) => [...l.slice(0, -1), `${i + 1}/${entities.length} ${e.key}: ${r.message}`]);
    }
    setBusy(false);
    router.refresh();
  };
  return (
    <div>
      <button type="button" className="btn btn-primary btn-sm" disabled={busy || !entities.length} aria-busy={busy} onClick={go}>{busy ? "Scoring…" : label}</button>
      {log.length > 0 && <ul className="caption" role="status" style={{ margin: "6px 0 0 18px" }}>{log.map((l, i) => <li key={i}>{l}</li>)}</ul>}
    </div>
  );
}

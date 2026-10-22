import { DELIVERY_LABEL, DELIVERY_TONE, STAGE_LABEL, STAGE_TONE, type DeliveryStatus, type StageStatus } from "@/lib/delivery/core";

export function DeliveryPill({ status, small }: { status: DeliveryStatus; small?: boolean }) {
  return <span className={`pill pill-${DELIVERY_TONE[status] ?? "none"} ${small ? "pill-sm" : ""}`}>{DELIVERY_LABEL[status] ?? status}</span>;
}
export function StagePill({ status, small }: { status: StageStatus; small?: boolean }) {
  return <span className={`pill pill-${STAGE_TONE[status] ?? "none"} ${small ? "pill-sm" : ""}`}>{STAGE_LABEL[status] ?? status}</span>;
}
const VERDICT_TONE: Record<string, string> = { pass: "sage", fail: "rust", pending: "hold" };
export function VerdictPill({ verdict }: { verdict: string | null | undefined }) {
  if (!verdict) return <span className="caption">—</span>;
  return <span className={`pill pill-sm pill-${VERDICT_TONE[verdict] ?? "none"}`}>{verdict}</span>;
}

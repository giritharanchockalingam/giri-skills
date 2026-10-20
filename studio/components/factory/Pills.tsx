import { STATUS_LABEL, STATUS_TONE, type VersionStatus } from "@/lib/factory/release";
import type { RunStatus, SkillStatus } from "@/lib/factory/db";
import { GATE_LABEL, GATE_HELP, type Gate } from "@/lib/factory/funnel";

export function VersionPill({ status, small }: { status: VersionStatus; small?: boolean }) {
  return <span className={`pill pill-${STATUS_TONE[status]} ${small ? "pill-sm" : ""}`}>{STATUS_LABEL[status]}</span>;
}
const SKILL_TONE: Record<SkillStatus, string> = { draft: "none", published: "sage", retired: "rust" };
export function SkillPill({ status, small }: { status: SkillStatus; small?: boolean }) {
  return <span className={`pill pill-${SKILL_TONE[status]} ${small ? "pill-sm" : ""}`}>{status[0].toUpperCase() + status.slice(1)}</span>;
}
const RUN_TONE: Record<RunStatus, string> = { queued: "none", running: "hold", succeeded: "sage", failed: "rust", needs_input: "hold", timeout: "rust", cancelled: "none" };
const RUN_LABEL: Record<RunStatus, string> = { queued: "Queued", running: "Running", succeeded: "Succeeded", failed: "Failed", needs_input: "Needs input", timeout: "Timed out", cancelled: "Cancelled" };
export function RunPill({ status, small }: { status: RunStatus; small?: boolean }) {
  return <span className={`pill pill-${RUN_TONE[status] ?? "none"} ${small ? "pill-sm" : ""}`}>{RUN_LABEL[status] ?? status}</span>;
}
export function RolePill({ role }: { role: string }) {
  return <span className="pill pill-sm pill-none">{role}</span>;
}

const GATE_TONE: Record<Gate, string> = { published: "ink", ready: "sage", needs_approval: "hold", below_bar: "rust", needs_eval: "hold", draft: "none" };   // same tones as the funnel strip
/** The one status a workspace skill shows: its stage in the publishing funnel (same words as the funnel counts). */
export function GatePill({ gate, small }: { gate: Gate; small?: boolean }) {
  return <span className={`pill pill-${GATE_TONE[gate]} ${small ? "pill-sm" : ""}`} title={GATE_HELP[gate]}>{GATE_LABEL[gate]}</span>;
}

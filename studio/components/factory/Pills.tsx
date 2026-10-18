import { STATUS_LABEL, STATUS_TONE, type VersionStatus } from "@/lib/factory/release";
import type { RunStatus, SkillStatus } from "@/lib/factory/db";

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

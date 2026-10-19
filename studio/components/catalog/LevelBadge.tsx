import { LEVEL_LABEL, type LevelOrNone } from "@/lib/scorecards/levels";

/** A scorecard level as a medal-coloured pill; text always carries the meaning (colour is decoration only). */
export function LevelBadge({ level, large }: { level: LevelOrNone; large?: boolean }) {
  return <span className={`level level-${level === "n/a" ? "na" : level}${large ? " level-lg" : ""}`}>{LEVEL_LABEL[level]}</span>;
}

import { ClampText } from "./ClampText";
import { StatStrip } from "./PageHead";

/** One-screen header for a skill detail page: breadcrumb · name · status pills · one-sentence description (2 lines,
 *  "more" expands) · meta line · compact stat strip · one primary action (+ at most one secondary). ≤ 220 px tall. */
export function DetailHead({ crumbs, title, pills, description, meta, stats, primary, secondary }: {
  crumbs: React.ReactNode; title: string; pills?: React.ReactNode; description?: string; meta?: React.ReactNode;
  stats: { label: string; value: React.ReactNode; title?: string }[]; primary?: React.ReactNode; secondary?: React.ReactNode;
}) {
  return (
    <header className="detail-head">
      <nav className="caption" aria-label="Breadcrumb">{crumbs}</nav>
      <div className="detail-row">
        <div className="min-w-0 flex-1">
          <div className="detail-title-row">
            <h1 className="h1 detail-h1">{title}</h1>
            {pills}
          </div>
          {description ? <ClampText text={description} lines={2} /> : null}
          {meta && <div className="caption detail-meta">{meta}</div>}
        </div>
        {(primary || secondary) && <div className="detail-actions">{primary}{secondary}</div>}
      </div>
      <StatStrip stats={stats} compact />
    </header>
  );
}

/* Shown the moment a link is clicked while the next page loads its data (every page reads live records), so a click
 * never looks like it did nothing. */
export default function Loading() {
  return (
    <div className="page-loading" role="status" aria-live="polite">
      <span className="page-loading-bar" aria-hidden="true" />
      <div className="skel skel-eyebrow" /><div className="skel skel-title" /><div className="skel skel-line" /><div className="skel skel-line short" />
      <div className="skel skel-card" />
      <span className="sr-only">Loading…</span>
    </div>
  );
}

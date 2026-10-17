import Link from "next/link";
export default function NotFound() {
  return (
    <div className="page-head">
      <div className="eyebrow">404</div>
      <h1 className="h1">Nothing <em>here</em>.</h1>
      <p className="sub">That page is not in the catalog. <Link href="/" className="link-flame">Back to skills →</Link></p>
    </div>
  );
}

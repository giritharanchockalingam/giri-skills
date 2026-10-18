import Link from "next/link";

/** Honest empty state: what is missing and the one action that creates it. */
export function EmptyState({ title, detail, action, href }: { title: string; detail?: string; action?: string; href?: string }) {
  return (
    <div className="empty">
      <div className="none">{title}</div>
      {detail && <p className="caption">{detail}</p>}
      {action && href && <Link href={href} className="btn btn-primary">{action}</Link>}
    </div>
  );
}

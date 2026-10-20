/* Delivery notes come one per repository ("Deploys: successful Vercel production deployments of acme-web."); shown
 * as-is they are a wall of near-identical lines. Notes that share a lead-in collapse into one line naming the count. Pure. */
const LEAD = /^(.*?\bof)\s+(.+?)\.?$/;

export function collapseNotes(notes: string[]): string[] {
  const groups = new Map<string, string[]>();
  const order: string[] = [];
  for (const n of notes) {
    const m = LEAD.exec(n);
    const key = m ? m[1] : n;
    if (!groups.has(key)) { groups.set(key, []); order.push(key); }
    if (m) for (const x of m[2].split(/,\s*/)) if (!groups.get(key)!.includes(x)) groups.get(key)!.push(x);
  }
  return order.map((k) => {
    const items = groups.get(k)!;
    if (!items.length) return k;
    return items.length === 1 ? `${k} ${items[0]}.` : `${k} ${items.length} services (${items.slice(0, 3).join(", ")}${items.length > 3 ? `, and ${items.length - 3} more` : ""}).`;
  });
}

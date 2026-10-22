// Fictional fixture (tech-debt-audit-runner evals): a server component that only formats data.
import { formatDate, formatMoney } from "@/lib/format";
import type { Invoice } from "@/lib/db/invoices";

export function InvoiceList({ invoices }: { invoices: Invoice[] }) {
  if (invoices.length === 0) {
    return <p>No invoices yet.</p>;
  }
  return (
    <table>
      <tbody>
        {invoices.map((inv) => (
          <tr key={inv.id}>
            <td>{inv.number}</td>
            <td>{formatMoney(inv.amountCents, inv.currency)}</td>
            <td>{formatDate(inv.issuedAt)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// Fictional fixture (tech-debt-audit-runner evals): a clean slice of a Next.js App Router repo.
import { InvoiceList } from "@/components/InvoiceList";
import { listInvoices } from "@/server/services/invoice-service";

export const metadata = { title: "Dashboard" };

export default async function DashboardPage() {
  const invoices = await listInvoices("tenant-demo");
  return (
    <main>
      <h1>Invoices</h1>
      <InvoiceList invoices={invoices} />
    </main>
  );
}

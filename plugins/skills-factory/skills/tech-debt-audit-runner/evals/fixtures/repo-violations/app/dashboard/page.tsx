// Fictional fixture (tech-debt-audit-runner evals): the dashboard route of a legacy Next.js repo.
import { listInvoices, type Invoice } from "@/server/services/invoice-service";
import { summarise } from "./helpers";

export default async function DashboardPage() {
  const invoices: Invoice[] = await listInvoices("tenant-demo");
  const summary = summarise(invoices.map((i) => i.amountCents));
  return <main>{summary.count} invoices, {summary.total} cents</main>;
}

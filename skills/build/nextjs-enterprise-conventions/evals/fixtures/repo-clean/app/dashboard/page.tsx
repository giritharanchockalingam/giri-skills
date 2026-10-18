import { listInvoices } from "@/server/services/invoice-service";

export default async function DashboardPage() {
  const invoices = await listInvoices();
  return <main>{invoices.length} invoices</main>;
}

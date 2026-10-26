import { exportInvoices } from "@/server/services/export-service";
export async function GET() { return new Response(await exportInvoices("t1")); }

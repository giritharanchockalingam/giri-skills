"use server";
// NX3: server action without zod parse
import { createInvoice } from "@/server/services/invoice-service";

export async function createInvoiceAction(input: { number: string; amount: number }) {
  return createInvoice(input);
}

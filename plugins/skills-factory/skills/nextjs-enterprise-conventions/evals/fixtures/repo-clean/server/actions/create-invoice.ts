"use server";
import { z } from "zod";
import { requireUser } from "@/lib/auth";
import { createInvoice } from "@/server/services/invoice-service";

const Input = z.object({ number: z.string().min(1), amount: z.number().int().positive() });

export async function createInvoiceAction(raw: unknown) {
  const input = Input.parse(raw);
  await requireUser();
  return createInvoice(input);
}

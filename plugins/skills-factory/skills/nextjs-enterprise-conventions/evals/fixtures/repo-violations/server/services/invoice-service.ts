// clean: service layer returns Result<T,E>
import { ok, err, type Result } from "@/lib/result";
import { insertInvoice } from "@/lib/db/invoices";

export async function createInvoice(input: { number: string; amount: number }): Promise<Result<{ id: string }, "DB_ERROR">> {
  try {
    const id = await insertInvoice(input);
    return ok({ id });
  } catch {
    return err("DB_ERROR");
  }
}

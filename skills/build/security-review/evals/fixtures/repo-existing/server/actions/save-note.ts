"use server";
// fictional fixture — existing server action with an auth check
import { requireRole } from "@/lib/auth";
import { insertNote } from "@/lib/db/notes";

export async function saveNote(text: string) {
  const user = await requireRole("member");
  return insertNote(user.tenantId, text);
}

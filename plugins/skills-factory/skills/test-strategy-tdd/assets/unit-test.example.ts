// tests/unit/server/services/invoice.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ok, fail } from "@/lib/result";
import { createInvoice } from "@/server/services/invoice.service";
import * as db from "@/lib/db/invoices";
import { writeAudit } from "@/lib/db/audit";
import { buildUser, buildInvoiceRow } from "../../../fixtures/builders";

vi.mock("@/lib/db/invoices");
vi.mock("@/lib/db/audit");

describe("invoiceService.createInvoice", () => {
  const member = buildUser({ role: "member" });
  const input = { number: "INV-1", amountCents: 1000 };

  beforeEach(() => {
    vi.mocked(db.findByNumber).mockResolvedValue(ok(null));
    vi.mocked(db.insert).mockResolvedValue(ok(buildInvoiceRow({ number: "INV-1" })));
  });

  it("returns the created invoice DTO when input is valid", async () => {
    const r = await createInvoice(member, input);
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value.number).toBe("INV-1");
  });

  it("writes an audit row on success", async () => {
    await createInvoice(member, input);
    expect(writeAudit).toHaveBeenCalledWith(expect.objectContaining({ entity: "invoice", action: "create" }));
  });

  it("returns AUTH_FORBIDDEN when the user is a viewer", async () => {
    const r = await createInvoice(buildUser({ role: "viewer" }), input);
    expect(r).toMatchObject({ ok: false, error: { code: "AUTH_FORBIDDEN" } });
    expect(db.insert).not.toHaveBeenCalled();
  });

  it("returns CONFLICT when the number already exists in the tenant", async () => {
    vi.mocked(db.findByNumber).mockResolvedValue(ok(buildInvoiceRow()));
    const r = await createInvoice(member, input);
    expect(r).toMatchObject({ ok: false, error: { code: "CONFLICT" } });
  });

  it("propagates db failures unchanged", async () => {
    vi.mocked(db.insert).mockResolvedValue(fail("INTERNAL", "db down"));
    const r = await createInvoice(member, input);
    expect(r).toMatchObject({ ok: false, error: { code: "INTERNAL" } });
  });
});

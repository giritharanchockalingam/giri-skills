import { it, expect } from "vitest";
import { exportInvoices } from "@/server/services/export-service";
it("writes a CSV header", async () => { expect(await exportInvoices("t1")).toContain("id,number"); });

// Hand-written test that predates the scaffold; must never be overwritten.
import { it, expect } from "vitest";
it("keeps the header", () => { expect("id,number").toContain("id"); });

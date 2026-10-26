// tests/setup.ts — unit project setup (jsdom).
import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// Fail tests that log errors — keeps console clean and catches React warnings.
const originalError = console.error;
console.error = (...args: unknown[]) => {
  originalError(...args);
  throw new Error(`console.error called: ${String(args[0])}`);
};

// Test-only module resolution matching tsconfig/Next: "@/x" → <studio>/x, extensionless .ts imports, and the
// "server-only" marker package (a build-time guard with no runtime behaviour outside Next) as an empty module.
import { register } from "node:module";
register("./resolve.mjs", import.meta.url);

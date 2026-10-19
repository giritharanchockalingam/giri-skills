/* Workspace roles and what each may do. Enforced in RLS/RPCs on the database AND here in route handlers
 * and server actions (the UI never decides on its own). */
export type Role = "consumer" | "author" | "reviewer" | "admin";
export const ROLES: readonly Role[] = ["consumer", "author", "reviewer", "admin"];

export type Action =
  | "skill.create" | "skill.edit" | "version.create" | "version.edit" | "version.request_review" | "version.review"
  | "version.publish" | "version.retire" | "eval.edit" | "eval.run" | "run.any_version" | "run.published"
  | "admin.members" | "admin.keys" | "admin.connections" | "admin.policies" | "audit.read"
  | "agent.edit" | "agent.publish" | "agent.approve" | "talent.edit" | "talent.publish";

const ALLOW: Record<Action, readonly Role[]> = {
  "skill.create": ["author", "admin"], "skill.edit": ["author", "admin"],
  "version.create": ["author", "admin"], "version.edit": ["author", "admin"], "version.request_review": ["author", "admin"],
  "version.review": ["reviewer", "admin"], "version.publish": ["author", "admin"], "version.retire": ["author", "admin"],
  "eval.edit": ["author", "admin"], "eval.run": ["author", "reviewer", "admin"],
  "run.any_version": ["author", "reviewer", "admin"], "run.published": ["consumer", "author", "reviewer", "admin"],
  "admin.members": ["admin"], "admin.keys": ["admin"], "admin.connections": ["admin"], "admin.policies": ["admin"],
  "audit.read": ["consumer", "author", "reviewer", "admin"],
  "agent.edit": ["author", "admin"], "agent.publish": ["reviewer", "admin"], "agent.approve": ["reviewer", "admin"],
  "talent.edit": ["author", "admin"], "talent.publish": ["reviewer", "admin"],
};

export const can = (role: Role | null | undefined, action: Action): boolean => !!role && ALLOW[action].includes(role);
export const isRole = (s: unknown): s is Role => typeof s === "string" && (ROLES as readonly string[]).includes(s);

export const ROLE_HELP: Record<Role, string> = {
  consumer: "Runs published versions and reads results.",
  author: "Creates skills, edits drafts, runs tests and evaluations, requests review, publishes approved versions.",
  reviewer: "Inspects evidence and approves or rejects versions in review; may run evaluations.",
  admin: "Everything, plus members, API keys, connections and policies.",
};

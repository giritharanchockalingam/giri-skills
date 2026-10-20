# Design: roles decide who can run which skill

Status: approved 20 Oct 2026 (authors and reviewers unrestricted; any admin approves access requests). PR 1 shipped: schema, enforcement, audit.

## Problem

Today every member and every API key can run every published skill. Roles (for example "Solution architect") are only lists of skills; a role-scoped MCP URL filters the tool list but grants or denies nothing. An enterprise needs to say, for example, that "only Finance can run the chargeback model", and to prove it in the audit log.

## Proposal

| | Behaviour |
|---|---|
| **Policy** | A workspace setting, *Restrict skills by role*. It is **off by default**, so today's behaviour is unchanged until an admin turns it on. |
| **Assignment** | Admins give each member and each API key one or more published roles. A key for an app, or for Port, gets the roles of the job it does. |
| **Rule when on** | A consumer, or an API key, may run a published skill only if one of its roles includes that skill. Authors, reviewers and admins stay unrestricted, because they must test before release. |
| **Enforced where** | In the database: the run functions check the assignment, so the API, MCP, playbooks, Port and the portal all hit the same check. Route handlers check again. The interface never decides on its own. |
| **MCP / API** | `tools/list` shows only skills the caller may run. `find_skill` still finds the others but says "not in your roles — request access". |
| **Request access** | A "Request access" button goes to the Inbox. An admin approves or declines it, the role is granted, and the decision is audited. |
| **Audit** | Every run records which role allowed it. Every refusal is logged as `run.denied`, with the skill and the caller. |
| **Visible** | The Library labels each skill "Available to you" or "Not in your roles". Each role page shows how many people and keys hold it. |

## Data

- Migration `0019_sf_role_access.sql` (with RLS and a rollback block):
  - **New table `sf_role_assignments`:** `workspace_id`, `talent_id` (kind `role`), exactly one of `user_id` / `api_key_id`, `granted_by`, `created_at`. It is unique per role and holder.
  - **New column:** `sf_workspaces.skills_by_role boolean not null default false`.
  - **Changed runs:** `sf_runs.granted_by_role uuid null`.
  - **Changed RPC:** the published-run function refuses with `not_in_role` when the policy is on and no assigned role covers the skill.
- Roles use their **published** version only, so a draft role grants nothing.

## Delivery (three PRs, each shippable)

| PR | Contents | Risk control |
|---|---|---|
| 1 | Schema, enforcement in the run functions, `run.denied` audit | SQL tests cover each caller type × policy on/off. With the policy off, behaviour is unchanged (tested). |
| 2 | Admin: assign roles to members and keys; the policy toggle with a preview ("12 people would lose access to 5 skills") | The preview comes from the same function the database uses |
| 3 | Library and MCP views; "Request access" through the Inbox | Unit tests for tool filtering |

## Decisions needed

1. Keep authors and reviewers unrestricted? (Recommended: yes, they test before release.)
2. Access requests: approved by any admin, or by the role's owner? (Recommended: any admin now; role owner later.)

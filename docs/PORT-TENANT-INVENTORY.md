# Port tenant inventory (WP0)

Generated 2026-10-23T23:53:07.768Z by `studio/scripts/port-inventory.mts` against `https://api.port.io`. Read-only; no credentials or tokens appear in this file.

## Organization

- name: giritharanC
- identifier: org_bAav62aTcjp5QCsv
- region (API base): https://api.port.io
- plan (as the API states it): FREEMIUM

## Blueprints

_/v1/blueprints → HTTP 200_

| identifier | title | kind | properties | relations | notes |
|---|---|---|---|---|---|
| `_ai_agent` | AI Agent | system | 10 | 1 |  |
| `_ai_conversation` | AI Conversation | system | 4 | 2 |  |
| `_ai_invocations` | AI Invocation | system | 16 | 4 |  |
| `_ai_plan` | AI Plan | system | 6 | 1 |  |
| `_mcp_server` | MCP Server | system | 6 | 0 | built-in MCP registry — register the factory MCP server as an entity here (§5.4) |
| `_rule` | Scorecard Rule | system | 3 | 1 |  |
| `_rule_result` | Scorecard Rule Result | system | 3 | 4 |  |
| `_scorecard` | Scorecard | system | 3 | 0 |  |
| `_team` | Team | system | 2 | 2 |  |
| `_user` | User | system | 4 | 1 |  |
| `_workflow` | Workflow | system | 6 | 0 |  |
| `aiSkill` | AI Skill | custom | 13 | 0 | factory's existing AI Skill blueprint (studio/docs/PORT.md, live since 2026-10-20) |
| `deployment` | Deployment | custom | 3 | 2 |  |
| `environment` | Environment | custom | 0 | 0 |  |
| `githubOrganization` | GitHub Organization | custom | 9 | 1 |  |
| `githubPullRequest` | GitHub Pull Request | custom | 12 | 8 |  |
| `githubRepository` | GitHub Repository | custom | 10 | 1 |  |
| `githubTeam` | GitHub Team | custom | 4 | 1 |  |
| `githubUser` | GitHub User | custom | 2 | 1 |  |
| `githubWorkflow` | GitHub Workflow | custom | 7 | 1 |  |
| `githubWorkflowRun` | GitHub Workflow Run | custom | 11 | 4 |  |
| `organization` | Organization | custom | 0 | 0 |  |
| `service` | Service | custom | 1 | 1 |  |
| `skill` | Skill | custom | 6 | 1 | name contains 'skill' — candidate native skill blueprint (§4.0: extend, don't duplicate) |
| `workload` | Workload | custom | 1 | 2 |  |

### §4.0 checks

- Built-in `_mcp_server` blueprint present: **yes**
- Native Port skill blueprint present: **candidate(s): `skill` — confirm in Port UI whether Port-managed**
- Factory `aiSkill` blueprint present: **yes**
- Custom blueprints in use: **14** (plan-gated — compare with the plan limit above).

## Entity counts (skill / MCP / repository blueprints)

- `_mcp_server`: 1 entities
- `aiSkill`: 23 entities
- `githubRepository`: 7 entities
- `service`: 4 entities
- `skill`: 83 entities

## Self-service actions and automations

_/v1/actions → HTTP 200_


_Port Workflows (the newer builder) are not listed by `/v1/actions`; record any existing workflow (e.g. the 2026-10-20 "Run governed skill" workflow) from the Port UI below._

- Workflows seen in UI: _to be recorded by owner_

## Scorecards

_/v1/scorecards → HTTP 200_

| blueprint | identifier | title | levels | rules |
|---|---|---|---|---|
| `_team` | `team_reliability_health` | Reliability Health | Basic → Bronze → Silver → Gold | 5 |
| `_team` | `team_dora_lead_time` | Lead Time for Changes | Basic → Bronze → Silver → Gold | 3 |
| `organization` | `org_delivery_performance` | Delivery Performance | Basic → Bronze → Silver → Gold | 9 |
| `service` | `delivery_performance` | Delivery Performance | Basic → Bronze → Silver → Gold | 14 |
| `service` | `reliability_health` | Reliability Health | Basic → Bronze → Silver → Gold | 5 |
| `service` | `production_readiness` | Production Readiness | Basic → Bronze → Silver → Gold | 11 |
| `service` | `dora_deploy_freq` | Deployment Frequency | Basic → Bronze → Silver → Gold | 3 |
| `_team` | `group_reliability_health` | Reliability Health (Group) | Basic → Bronze → Silver → Gold | 4 |
| `_team` | `team_dora_deploy_freq` | Deployment Frequency | Basic → Bronze → Silver → Gold | 3 |
| `organization` | `org_reliability_health` | Reliability Health | Basic → Bronze → Silver → Gold | 4 |
| `_team` | `group_delivery_performance` | Delivery Performance (Group) | Basic → Bronze → Silver → Gold | 9 |
| `_team` | `team_delivery_performance` | Delivery Performance | Basic → Bronze → Silver → Gold | 14 |
| `service` | `dora_lead_time` | Lead Time for Changes | Basic → Bronze → Silver → Gold | 3 |

## Credentials and secrets (locations only)

- `PORT_CLIENT_ID`, `PORT_CLIENT_SECRET`: Vercel project `giri-skills-studio`, production, type *sensitive* (not readable after creation).
- `PORT_SF_API_KEY`: same place — the factory workspace key Port's webhook runs under.
- `PORT_API_URL`: set only for a non-default region.
- Port-side secret `SF_API_KEY` (Settings → Secrets): the workspace key the MCP connector and workflow use.
- Spec §11 (token single-flight): confirm these Port credentials are **dedicated to the factory** and not shared with any other integration — _owner to confirm_.

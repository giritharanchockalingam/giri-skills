# Port tenant inventory (WP0)

Generated 2026-10-24T00:08:44.180Z by `studio/scripts/port-inventory.mts` against `https://api.port.io`. Read-only; no credentials or tokens appear in this file.

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

## Blueprint schemas (skill / MCP / repository / service)

### `_mcp_server`

- created: 2026-10-20T18:40:29.613Z by user_UmOD07zpION0dKZ0; updated: 2026-10-20T18:40:29.613Z by user_UmOD07zpION0dKZ0
- required: ["url"]

| property | type | format | enum | title |
|---|---|---|---|---|
| `url` | string | url |  | URL |
| `description` | string |  |  | Description |
| `allowed_tools` | array |  |  | Allowed Tools |
| `oauth_config` | object |  |  | OAuth Config |
| `headers` | object |  |  | Headers |
| `exposed` | boolean |  |  | Expose As Port Connector |

### `aiSkill`

- created: 2026-10-20T19:19:52.911Z by rH2QsFsSpXo2E9Kfwtkqfkn4Owns3meV; updated: 2026-10-20T19:19:52.911Z by rH2QsFsSpXo2E9Kfwtkqfkn4Owns3meV
- required: []

| property | type | format | enum | title |
|---|---|---|---|---|
| `purpose` | string | markdown |  | Purpose |
| `version` | number |  |  | Live version |
| `published_at` | string | date-time |  | Published |
| `eval_pass_rate` | number |  |  | Eval pass rate (%) |
| `eval_cases` | number |  |  | Eval cases |
| `approved` | boolean |  |  | Approved |
| `library_status` | string |  | current, library_updated, blocked | Library status |
| `stage` | string |  |  | Lifecycle stage |
| `inputs` | array |  |  | Inputs |
| `uses_model` | boolean |  |  | Uses a model |
| `manifest_hash` | string |  |  | Manifest hash |
| `portal_url` | string | url |  | Skills Factory page |
| `mcp_tool` | string |  |  | MCP tool name |

Sample identifiers (first 3): `infra-gpu-sizing`, `effort-estimator`, `ai-incident-runbook`
First entity: created 2026-10-20T19:19:53.536Z by rH2QsFsSpXo2E9Kfwtkqfkn4Owns3meV; property keys present: `purpose`, `version`, `published_at`, `eval_pass_rate`, `eval_cases`, `approved`, `library_status`, `stage`, `inputs`, `uses_model`, `manifest_hash`, `portal_url`, `mcp_tool`

### `githubRepository`

- created: 2026-10-20T18:45:26.552Z by rH2QsFsSpXo2E9Kfwtkqfkn4Owns3meV; updated: 2026-10-20T18:48:38.349Z by rH2QsFsSpXo2E9Kfwtkqfkn4Owns3meV
- required: []

| property | type | format | enum | title |
|---|---|---|---|---|
| `readme` | string | markdown |  | README |
| `codeowners` | string | markdown |  | CODEOWNERS |
| `url` | string | url |  | Repository URL |
| `defaultBranch` | string |  |  | Default branch |
| `description` | string |  |  | Description |
| `visibility` | string |  |  | Visibility |
| `language` | string |  |  | Language |
| `last_push` | string | date-time |  | Last Repository Push |
| `gitignore` | string |  |  | Git Ignore |
| `pr_template` | string |  |  | PR Template |

| relation | target | required | many |
|---|---|---|---|
| `githubTeams` | `githubTeam` | false | true |

Sample identifiers (first 3): `elastic-agent-local`, `intelliops-platform`, `touchstone-showcase`
First entity: created 2026-10-20T18:46:46.004Z by github-ocean; property keys present: `readme`, `codeowners`, `url`, `defaultBranch`, `description`, `visibility`, `language`, `last_push`, `gitignore`, `pr_template`, `cycle_time_trend`, `failure_rate_trend`, `monthly_workflow_failure_rate`, `stale_pr_share_percent`, `throughput_trend`, `weekly_workflow_failure_rate`, `failed_workflow_runs_30d`, `failed_workflow_runs_7d`, `merged_prs_last_month`, `merged_prs_last_week`, `open_prs`, `pr_cycle_time`, `pr_cycle_time_weekly`, `stale_prs_7d`, `workflow_runs_30d`, `workflow_runs_7d`

### `service`

- created: 2026-10-20T18:40:40.765Z by rH2QsFsSpXo2E9Kfwtkqfkn4Owns3meV; updated: 2026-10-20T18:48:42.729Z by rH2QsFsSpXo2E9Kfwtkqfkn4Owns3meV
- required: []

| property | type | format | enum | title |
|---|---|---|---|---|
| `criticality` | string |  | low, medium, high, critical | Criticality |

| relation | target | required | many |
|---|---|---|---|
| `github_repository` | `githubRepository` | false | false |

Sample identifiers (first 3): `giri-skills`, `agentic-stack`, `vibe-shield`
First entity: created 2026-10-20T18:54:15.840Z by rH2QsFsSpXo2E9Kfwtkqfkn4Owns3meV; property keys present: `criticality`, `github_repository_id`, `github_codeowners`, `github_default_branch`, `github_description`, `github_gitignore`, `github_language`, `github_last_push`, `github_pr_template`, `github_readme`, `github_url`, `github_visibility`, `deploy_freq_tier`, `github_days_since_last_push`, `github_stale_pr_share_percent`, `github_cycle_time_trend`, `github_throughput_trend`, `github_weekly_workflow_failure_rate`, `github_monthly_workflow_failure_rate`, `github_failure_rate_trend`, `github_lead_time_tier`, `deployment_frequency`, `total_deployments`, `github_failed_workflow_runs_30d`, `github_failed_workflow_runs_7d`, `github_lead_time_for_change`, `github_merged_prs_last_month`, `github_merged_prs_last_week`, `github_open_prs`, `github_pr_cycle_time`, `github_pr_cycle_time_weekly`, `github_stale_prs_7d`, `github_workflow_runs_30d`, `github_workflow_runs_7d`

### `skill`

- created: 2026-10-20T18:49:46.863Z by user_UmOD07zpION0dKZ0; updated: 2026-10-20T18:49:46.863Z by user_UmOD07zpION0dKZ0
- required: ["description"]

| property | type | format | enum | title |
|---|---|---|---|---|
| `description` | string |  |  | Description |
| `instructions` | string | markdown |  | Instructions |
| `fileUrl` | string | url |  | Skill file URL |
| `version` | string |  |  | Version |
| `location` | string |  | global, project | Location |
| `publish_status` | string |  | pending, published, not published, deprecated | Publish status |

| relation | target | required | many |
|---|---|---|---|
| `group` | `_team` | false | true |

Sample identifiers (first 3): `giritharanchockalingam/giri-skills/skills/ai-platform/ai-use-case-canvas/SKILL.md`, `giritharanchockalingam/giri-skills/skills/ai-platform/data-contract-validator/SKILL.md`, `giritharanchockalingam/giri-skills/skills/ai-platform/ai-vendor-assessment/SKILL.md`
First entity: created 2026-10-20T18:53:19.826Z by github-ocean; property keys present: `description`, `instructions`, `fileUrl`, `version`, `location`, `publish_status`, `group_identifiers`, `cliInstall`


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

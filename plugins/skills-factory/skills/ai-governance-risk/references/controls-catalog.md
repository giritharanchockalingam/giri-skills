# Controls Catalog

Select per risk. Each control needs an owner, a status (in place / planned / gap), and evidence.

| ID | Control | Addresses | Evidence expected |
|---|---|---|---|
| C01 | Use-case intake and risk tiering recorded in the AI inventory | All | Inventory entry with tier and owner |
| C02 | Data classification and minimization: only required fields enter prompts; PII redaction where feasible | Privacy | Data-flow diagram; redaction tests |
| C03 | Vendor data terms: no training on inputs; retention limits; residency | Privacy, IP | Contract clause references |
| C04 | Access control at retrieval and tool layers (RLS, scopes, tenant isolation) | Privacy, Security | AuthZ tests; RLS policies |
| C05 | Logging with retention policy; PII-safe logs; audit trail of prompts, outputs, approvals | Privacy, Transparency, Operational | Log schema; retention config |
| C06 | Grounding and citation requirement; abstention on low confidence | Hallucination | Eval faithfulness scores; abstention tests |
| C07 | Evaluation harness with golden set and CI gate; zero-tolerance safety checks | Hallucination, Misuse, Operational | Scorecard; CI job |
| C08 | Bias testing: disaggregated performance by relevant groups; proxy-variable review | Bias | Disaggregated eval table; review notes |
| C09 | Human-in-the-loop for consequential or irreversible actions; appeal/contest path | Bias, Safety, Transparency | HITL design; appeal procedure |
| C10 | Prompt-injection defenses: untrusted content delimiting, least-privilege tools per phase, deny-list in code, injection test corpus | Security | Test results; tool scopes |
| C11 | Secrets management; no credentials in prompts or state | Security | Config review |
| C12 | Output filtering: PII, toxicity, policy violations; blocklists where appropriate | Misuse, Privacy | Filter config; test cases |
| C13 | Scope limitation in system prompt and router; out-of-scope refusal; disclosure that the user is interacting with AI | Misuse, Transparency | Prompt; UI text |
| C14 | IP controls: provenance of training/fine-tuning data; output similarity checks for published content; license review of open-weights models | IP | License register; similarity check process |
| C15 | Model and prompt versioning; change management; rollback | Operational | Version registry; release notes |
| C16 | Monitoring: quality sampling, drift alerts, cost and latency SLOs, incident process | Operational, Hallucination | Dashboards; runbook |
| C17 | Vendor/model fallback and exit plan | Operational | Documented fallback; tested |
| C18 | Training for users and reviewers; acceptable-use policy acknowledgment | Misuse | Training records |
| C19 | Model card and user-facing documentation maintained | Transparency | Model card version |
| C20 | DPIA or equivalent privacy assessment for high-tier cases | Privacy | Signed assessment |
| C21 | Periodic review (quarterly for high tier) and re-tiering on scope change | All | Review log |
| C22 | Red-teaming before launch for customer-facing or high-tier cases | Security, Misuse, Safety | Red-team report and fixes |

## Minimum control sets by tier (assumption; adjust to policy)
| Tier | Required controls |
|---|---|
| Low | C01, C03, C05, C13, C15 |
| Medium | Low + C02, C04, C06, C07, C09, C10, C12, C16, C18, C19 |
| High | Medium + C08, C11, C14, C17, C20, C21, C22 and executive sign-off |

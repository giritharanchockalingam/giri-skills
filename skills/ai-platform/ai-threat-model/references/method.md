# Method — ai-threat-model

## 1. Element types (STRIDE per element)
| Component kind | DFD element type | STRIDE categories |
|---|---|---|
| user, external_api | external entity | S, R |
| app, llm, retriever, tool, agent | process | S, T, R, I, D, E |
| vector_store, data_store | data store | T, I, D |
| every flow | data flow | T, I, D |

Source: Microsoft STRIDE-per-element table (Hernan, Lambert, Ostwald, Shostack, MSDN Magazine, Nov 2006, Figure 5). The table gives data stores no R; if a store is an audit log, add its repudiation threat by hand.

## 2. OWASP Top 10 for LLM Applications 2025 rules
| Id | Applies to kinds | Extra condition |
|---|---|---|
| LLM01 Prompt Injection | llm, agent | reachable via flows from an untrusted origin: kind user, external_api, retriever or vector_store (indirect injection through stored content), or any internet_facing component |
| LLM02 Sensitive Information Disclosure | llm, agent, app, retriever, vector_store | handles_pii = yes |
| LLM03 Supply Chain | llm, agent, tool | — |
| LLM04 Data and Model Poisoning | llm, vector_store | — |
| LLM05 Improper Output Handling | app, agent, tool, data_store | has an incoming flow from an llm or agent |
| LLM06 Excessive Agency | llm, agent, tool, app | write_actions = yes |
| LLM07 System Prompt Leakage | llm, agent | — |
| LLM08 Vector and Embedding Weaknesses | vector_store, retriever | — |
| LLM09 Misinformation | llm | — |
| LLM10 Unbounded Consumption | llm, agent | — |

## 3. Severity
- Likelihood (1–3) = 1 + **exposed** + **boundary**.
  - Component: exposed = internet_facing; boundary = it is an end of any boundary-crossing flow.
  - Flow: exposed = either end internet_facing; boundary = the flow crosses a trust boundary (declared, or ends in different zones).
- Impact (1–3) = 1 + **PII** + **write**, capped at 3.
  - PII adds 1 for S, T, I, E, LLM01, LLM02, LLM03, LLM04, LLM07, LLM08 when handles_pii = yes (flow: either end).
  - Write adds 1 for S, T, R, E, LLM01, LLM03, LLM05, LLM06, LLM09 when write_actions = yes (flow: the receiving end).
  - D and LLM10 are fixed at 2 (availability and cost affect the whole service).
- Severity from L × I: **high** ≥ 6, **medium** 3–4, **low** ≤ 2 (5 cannot occur).

Worked example (Northwind fixture, fictional): `orchestrator` is not internet-facing but sends and receives boundary-crossing flows, so L = 2; it handles PII and has write actions, so LLM01 impact = 3; 2 × 3 = 6 → high.

## 4. Status and owner
- Control rows match by `threat_id`, or by `mitigation_id` (that row then covers every threat listing the mitigation).
- **mitigated**: a threat-level `in_place` row, or every mitigation id the threat lists has an `in_place` row.
- **planned**: any other matching row (planned, or only some mitigations in place).
- **open**: no matching row.
- Owner: the matched rows' owners (sorted, `;`-joined); none → `[TO BE BASELINED — owner: Security architect]`.
- Control rows that match nothing are listed in the report, not dropped silently.

## 5. Gate
`max_open_high` = N: the run exits 1 when open high threats > N. Exit 0 when equal.

## 6. Limits
Rule-based enumeration from the declared DFD. It does not find business-logic abuse, multi-step attack chains, implementation bugs or threats in elements missing from the inputs. Severity rules are a consistent triage, not a quantitative risk estimate. Not a penetration test or a security sign-off.

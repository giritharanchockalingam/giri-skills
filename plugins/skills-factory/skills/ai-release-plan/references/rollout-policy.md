# Rollout policy (the skill's policy)

This is **the skill's policy**, not an industry standard. It fixes the *shape* of the rollout by
risk tier; the *thresholds* (gates) always come from the release owner's gates CSV and are never
defaulted.

## Stage sequence
| Order | Stage | Traffic | Served to users | Leaves the stage when |
|---|---|---|---|---|
| 1 | Offline eval | none (eval set) | no | every `offline_eval` gate is met and the Eval lead signs off |
| 2 | Shadow | 100 % mirrored | no | `min_observed_requests` observed and every `shadow` gate holds |
| 3..k | Canary steps | policy % below | yes | `min_observed_requests` observed at that % and every `canary` gate holds |
| last | GA | 100 % | yes | every `ga` gate holds; Product owner approves |

## Canary steps by risk tier
| risk_tier | Canary steps (% of live traffic) | Rationale |
|---|---|---|
| low | 10, 50 | small blast radius; two observation points |
| medium | 5, 25, 50 | one low-exposure step before a quarter of traffic |
| high | 1, 5, 10, 25, 50 | exposure grows slowly; each step must observe the same request count |

Override: an owner may set the `canary_steps` fact (ascending percentages, e.g. `1;5;25`); the plan
then states "canary_steps fact (owner override)" as the basis.

## Owner per step
| Step | Accountable role | Fact key |
|---|---|---|
| Offline eval | Eval lead | `owner_eval_lead` |
| Shadow | SRE on-call | `owner_sre_oncall` |
| Canary steps | Release manager | `owner_release_manager` |
| GA | Product owner | `owner_product_owner` |
| Rollback | SRE on-call | `owner_sre_oncall` |

A missing owner is written `[TO BE BASELINED — owner: Release manager]`: the Release manager is
accountable for naming one before the stage starts.

## Related public practice (by name)
- Google SRE Workbook, "Canarying Releases" — staged exposure and canary evaluation.
- NIST AI RMF 1.0, *Manage* function — deployment decisions tied to measured risk.

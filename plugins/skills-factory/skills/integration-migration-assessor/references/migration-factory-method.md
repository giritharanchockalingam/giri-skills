# Migration Factory Method

## 1. Principles
| Principle | Practice |
|---|---|
| Inventory before estimate | No effort or price without a scored inventory |
| Retire before migrate | Cheapest interface is the one you delete |
| Patterns before interfaces | Build target-pattern templates (sync API, async event, batch, file) in wave 0; interfaces then follow templates |
| Prove the factory on simples | Wave 1 validates tooling, tests, and cutover before complexity arrives |
| Parallel run governs cutover | Legacy and target run side by side; variance log decides go/no-go |
| Decommission is a deliverable | Savings start when the old platform is switched off, not when the new one is switched on |

## 2. Approach by band
| Band | Approach | Team | Test | Review |
|---|---|---|---|---|
| Simple | Tool-assisted conversion (spec extraction → target config generation); developer verifies | Core engineers, high leverage | Templated contract tests, auto-generated from spec; parallel-run comparison | Peer |
| Medium | Factory: template selection, mapping completion, custom logic ported | Core + senior | Contract + integration tests; parallel run | Tech lead |
| Complex | Design-led: re-express orchestration/transformation in target patterns; may split into several interfaces | Senior + architect | Full integration and NFR tests; extended parallel run | Architect |
| Very complex | Spike first (time-boxed); decide redesign / retire / keep on legacy longer / re-platform | Architect + business owner | Per decision | ARB and business sponsor |

## 3. Factory operating model
| Station | Input | Output | Exit check |
|---|---|---|---|
| Intake | Scored inventory row, source artifacts | Migration ticket with pattern template assigned | Owner confirmed; test data available |
| Convert | Ticket | Target implementation in repo | Lint/build passes; config generated |
| Test | Implementation | Contract + integration test results | Pass thresholds met |
| Parallel run | Deployed to target in shadow | Variance log over N days | Variance within tolerance; sign-off |
| Cutover | Sign-off | Traffic switched; legacy route disabled | Monitoring green for hypercare window |
| Decommission | Cutover complete for all interfaces on a legacy component | Component removed; licence/infra released | Finance confirms cost release |

Throughput is measured per station; bottlenecks (usually test data and client sign-off) are managed as dependencies with dates.

## 4. Wave rules
| Rule | Detail |
|---|---|
| Wave 0 | Target platform foundation, CI/CD, observability, security baseline, pattern templates, conversion tooling, test harness, parallel-run comparison tool. No business cutovers |
| Wave 1 | 10–20% of interfaces, Simple band, covering each pattern at least once; proves the factory |
| Middle waves | Mixed bands; dependencies resolved within or before the wave; the most complex items in a middle wave with the most attention, never last |
| Final wave | Long tail, stragglers, decommission |
| Sizing | Balance by weighted score sum, not by count |
| Dependencies | Interfaces sharing an endpoint under change migrate together; consumers after providers |
| Constraints | Freeze windows exclude cutovers; dependent programs (ERP go-live) fix wave boundaries |
| Entry criteria | Wave scope frozen; test data ready; owners confirmed; environments available |
| Exit criteria | All interfaces cut over; hypercare complete; no open P1; variance logs signed; runbooks delivered |
| Rollback | Per interface: route switch back to legacy within <n> minutes; legacy retained until wave exit + buffer |

## 5. Cutover and parallel run
| Element | Default | Adjust when |
|---|---|---|
| Parallel-run duration | 5 business days (Simple/Medium), 10 (Complex) | Monthly batch → one full cycle |
| Variance tolerance | 0 functional variance; timing within SLA | Known legacy defects documented as accepted variance |
| Cutover window | Off-peak, outside freeze | Client calendar |
| Hypercare | 10 business days per wave | Peak proximity |
| Go/no-go | Variance log, test results, rollback rehearsed, owner sign-off | — |

## 6. Decommission
| Step | Owner | Evidence |
|---|---|---|
| Confirm no traffic on legacy routes (30 days) | Platform team | Metrics |
| Remove legacy deployments | Platform team | Change record |
| Terminate licences / infrastructure | Client procurement | Contract notice |
| Release run team capacity | Client IT | Org change |
| Record savings start date | Finance | Ledger |

TCO savings lines reference these dates. Without a decommission date, savings are `[TO BE BASELINED — owner: ___]`.

## 7. Risks specific to migration
| Risk | Mitigation |
|---|---|
| Connector gaps on target discovered late | F3 scoring; spike in wave 0 for any F3 = 5 |
| Endpoint systems change during migration | Change freeze on in-flight endpoints; or re-score and re-wave |
| Dual-run cost longer than planned | Decommission as milestone with owner; licence notice dates tracked |
| Test data unavailable | Data provisioning as client dependency with date |
| Skills on target platform | Wave 0 enablement; pairing; named onshore leads |
| Unknown-heavy inventory | Provisional assessment; inventory completion phase |

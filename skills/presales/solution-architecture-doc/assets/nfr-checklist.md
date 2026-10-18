# NFR Checklist

For every applicable row: target (number + unit + condition), measurement method, source of the target (client statement / regulation / SLA / `[TO BE BASELINED — owner: <role>]`), and design response. Mark non-applicable rows N/A with reason. Adjectives are not targets.

| ID | Category | NFR | Target pattern | Measurement method | Typical source | Design response examples |
|---|---|---|---|---|---|---|
| NFR-01 | Performance | API latency | p95 ≤ <n> ms at <n> req/s for <endpoint class> | Gateway analytics / load test | Client SLA, user-journey analysis | Caching, async for long ops, connection pooling |
| NFR-02 | Performance | Batch window | <job> completes within <n> h for <n> records | Scheduler logs | Operations calendar | Partitioning, parallelism, incremental loads |
| NFR-03 | Performance | Event latency | Producer-to-consumer ≤ <n> s at p95 | Trace timestamps | Business process need | Partition sizing, consumer scaling |
| NFR-04 | Scalability | Peak capacity | Sustain <n>× average (peak = <value>) for <duration> | Load test to peak + 20% | Peak season data | Horizontal autoscaling, rate limiting, back-pressure |
| NFR-05 | Scalability | Growth | Support <n>% annual growth for 3 years without re-architecture | Capacity model | Business plan | Partitioned stores, stateless services |
| NFR-06 | Availability | Service availability | ≥ <99.9>% monthly measured at <point>, excluding planned windows ≤ <n> h/month | Synthetic checks + SLO dashboard | Client SLA / business criticality | Multi-AZ, health checks, graceful degradation |
| NFR-07 | Resilience | Recovery | RTO ≤ <n> h, RPO ≤ <n> min for <data class> | DR test (annual) | BIA / regulation | Replication, backups with PITR, runbooks |
| NFR-08 | Resilience | Fault tolerance | No single point of failure in <tier>; dependency failure degrades, does not cascade | Chaos/failover test | Architecture principle | Retries with backoff, circuit breakers, bulkheads, DLQ |
| NFR-09 | Resilience | Idempotency | Duplicate delivery of <message class> produces no duplicate side effects | Integration tests | Integration principle | Idempotency keys, outbox pattern |
| NFR-10 | Security | Authentication | All external calls authenticated via <OIDC/OAuth2>; service-to-service via <mTLS/workload identity> | Config review, pen test | Security policy | Central IdP, short-lived tokens |
| NFR-11 | Security | Authorization | RBAC/ABAC enforced at gateway and service; least privilege | Authorization tests | Security policy | Policy engine, scopes per API |
| NFR-12 | Security | Data protection | Encryption in transit (TLS ≥1.2) and at rest (<KMS>); PII fields <masked/tokenized> | Config scan | Regulation (GDPR/FERPA/PCI/HIPAA) | Field-level encryption, tokenization |
| NFR-13 | Security | Secrets | No secrets in code/config repos; rotation ≤ <n> days | Secret scanning in CI | Security policy | Vault/KMS, workload identity |
| NFR-14 | Security | Vulnerability management | No critical/high open > <n> days; dependency and container scanning in CI | Scanner reports | Security policy | SCA, image scanning, patch SLAs |
| NFR-15 | Security | Audit | All admin and data-access actions logged, immutable, retained <n> months | Log review | Regulation / audit | Central audit log, WORM storage |
| NFR-16 | Compliance | Data residency | <data class> stored and processed in <region/country> incl. backups and DR | Config and contract review | Regulation / client policy | Region pinning, residency-aware DR |
| NFR-17 | Compliance | Retention and deletion | <data class> retained <n> years; deletion on request within <n> days | Process test | Regulation | Retention policies, deletion workflows |
| NFR-18 | Compliance | Standards | <SOC 2 / ISO 27001 / PCI DSS / HECVAT / WCAG 2.x AA> evidence available | Certification / audit | Procurement requirement | Controls mapping |
| NFR-19 | Operability | Observability | Logs, metrics, traces with correlation ID for 100% of requests; dashboards per service; alerts routed to <on-call> | Observability review | Operations standard | Structured logging, OpenTelemetry |
| NFR-20 | Operability | Deployability | Zero-downtime deploys; rollback ≤ <n> min; IaC for 100% of infrastructure | Deployment logs | Engineering standard | Blue/green or canary, IaC pipelines |
| NFR-21 | Operability | Supportability | Runbook per container/interface; on-call model defined; MTTR target <n> h for P1 | Incident records | Operations SLA | Runbooks, alert quality |
| NFR-22 | Maintainability | Change lead time | Change from merge to production ≤ <n> days; test automation coverage ≥ <n>% on <scope> | CI metrics | Engineering standard | Trunk-based, automated tests |
| NFR-23 | Interoperability | Standards | APIs follow <OpenAPI 3.x / AsyncAPI>; event schemas versioned with compatibility rules | Linting in CI | API governance | Schema registry, API style guide |
| NFR-24 | Data | Quality | <entity> completeness ≥ <n>%; reconciliation variance ≤ <n>% | Data quality jobs | Data owner | Validation at ingress, reconciliation reports |
| NFR-25 | Usability / accessibility | Accessibility | WCAG 2.x AA for all user-facing UI | Automated + manual audit | Regulation / policy | Accessible components, testing |
| NFR-26 | Capacity / cost | Run cost | Monthly run cost ≤ <amount> at <volume>; cost per transaction tracked | Cloud billing tags | Budget | Right-sizing, autoscaling floors, reserved capacity |
| NFR-27 | Portability | Exit | Data exportable in <open format> within <n> days; no proprietary-only interfaces for core flows | Export test | Procurement / risk | Open standards, abstraction layers |
| NFR-28 | Localization | Time zones and locales | Timestamps in UTC with locale rendering; <n> locales supported | UI tests | Business footprint | i18n framework |

## NFR table layout for the document
| ID | NFR | Target | Measurement | Source | Design response | Test in phase |
|---|---|---|---|---|---|---|

# SPEC — {{PROJECT_NAME}}

| Field | Value |
|---|---|
| Status | Draft |
| Owner | [TO BE BASELINED — owner: <role>] |
| Last updated | {{DATE}} |
| Tenancy | {{TENANCY}} |

## 1. Purpose (one paragraph)
{{PURPOSE}}

## 2. Users and jobs to be done
| Persona | Job to be done | Frequency | Success looks like |
|---|---|---|---|
| | | | |

## 3. Scope
### In scope (v1)
| # | Capability | Acceptance criterion |
|---|---|---|
| 1 | | |

### Out of scope (explicit)
| Item | Reason | Revisit when |
|---|---|---|
| | | |

## 4. Non-functional requirements
| NFR | Target | How verified |
|---|---|---|
| Availability | [TO BE BASELINED — owner: <role>] | uptime monitor |
| p95 latency (page) | ≤ 500 ms | Vercel Speed Insights |
| p95 latency (API) | ≤ 300 ms | logs / tracing |
| Data isolation | RLS on every tenant table | `rls_lint.py` in CI |
| Auth | Supabase Auth; MFA for admin roles | e2e |
| Audit | Every write to tenant data logged with actor + before/after | audit_log table |
| Backup / RPO / RTO | [TO BE BASELINED — owner: <role>] | restore drill |
| Accessibility | WCAG 2.2 AA on critical paths | axe in e2e |
| Observability | Structured logs, error tracking, health endpoints | observability-setup |

## 5. Architecture (summary; detail in ADRs)
| Layer | Choice | ADR |
|---|---|---|
| Frontend | Next.js App Router, React Server Components | 0001 |
| Backend | Server actions + route handlers; services in `server/services` | 0001 |
| Data | Supabase Postgres, RLS, migrations in repo | 0001 |
| Hosting | Vercel (preview per PR, prod by tag) | 0001 |
| CI | GitHub Actions | 0001 |

## 6. Data model (high level)
| Entity | Tenant-scoped | Owner column | Notes |
|---|---|---|---|
| | | | |

## 7. Integrations
| System | Direction | Auth | Owner |
|---|---|---|---|
| | | | |

## 8. Risks
| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| | | | | |

## 9. Open questions
| # | Question | Owner | Due |
|---|---|---|---|
| 1 | | [TO BE BASELINED — owner: <role>] | |

## 10. Milestones
| Milestone | Scope | Target |
|---|---|---|
| M0 Bootstrapped | CI green, docs in place | |
| M1 | | |

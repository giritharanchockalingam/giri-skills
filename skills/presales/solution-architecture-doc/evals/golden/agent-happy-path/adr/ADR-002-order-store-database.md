# ADR-002: Order store database

- **System:** Order Hub
- **Status:** accepted
- **Owner:** Lead engineer, Order service
- **Source:** Architecture workshop 2026-10-07

## Context
Order state changes must be transactional across order lines and fulfilment steps.

## Options considered
| Option | Transactional integrity (40) | Team skills (30) | Cost (30) | Weighted |
|---|---|---|---|---|
| PostgreSQL 16 | 5 | 5 | 4 | 4.7 |
| Cloud Spanner | 5 | 2 | 2 | 3.2 |
| MongoDB Atlas | 3 | 3 | 3 | 3.0 |

## Decision
PostgreSQL 16. Meets transactional needs at the stated peak with the skills the team already has.

## Consequences
- Read replicas serve status queries at peak
- Partitioning by order month is planned before wave 2

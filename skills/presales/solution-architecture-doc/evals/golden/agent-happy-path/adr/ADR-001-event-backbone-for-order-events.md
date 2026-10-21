# ADR-001: Event backbone for order events

- **System:** Order Hub
- **Status:** proposed
- **Owner:** Head of Integration, Northwind
- **Source:** Architecture workshop 2026-10-07

## Context
Pick queues must be rebuilt from order events after a warehouse system outage; events must be replayable for 7 days (CTO statement 2026-09-02).

## Options considered
| Option | Replay and ordering (35) | Operational effort (25) | Ecosystem fit (20) | Cost (20) | Weighted |
|---|---|---|---|---|---|
| Kafka (managed) | 5 | 3 | 4 | 3 | 3.9 |
| Cloud Pub/Sub | 2 | 5 | 4 | 4 | 3.55 |
| IBM MQ | 3 | 3 | 2 | 3 | 2.8 |

## Decision
Kafka (managed). Only option that meets the 7-day replay requirement natively, with per-key ordering for order lifecycles.

## Consequences
- The platform team operates a managed Kafka cluster with a schema registry
- Every consumer must be idempotent

# ADR-003: API entry point for stores and partners

- **System:** Order Hub
- **Status:** accepted
- **Owner:** Enterprise architect, Northwind
- **Source:** EA standards v3 §4

## Context
Marketplace partners and store systems need one governed, rate-limited entry point.

## Options considered
| Option | Security and policy (50) | Standards compliance (30) | Latency (20) | Weighted |
|---|---|---|---|---|
| Apigee X | 5 | 5 | 3 | 4.6 |
| Direct service exposure | 2 | 1 | 5 | 2.3 |

## Decision
Apigee X. The enterprise API standard; partner keys, quotas and threat protection come with it.

## Consequences
- One extra network hop on every call; measured against the p95 target once it is set

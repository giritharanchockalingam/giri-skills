# Demo Spec — Support triage showroom — v0.2 — 2026-10-15

**Decision the demo makes easier:** whether an SLM can triage tickets on-prem without customer data leaving the tenant

## 1. Audience and persona
| Item | Value |
|---|---|
| Audience | COO and Head of Support (fictional Northwind) |
| On-screen persona and goal | Support lead clearing the morning queue |

## 7. Synthetic data plan
| Entity | Volume | Planted cases | Generator |
|---|---|---|---|
| customers | 50 | C00008 the clear win | gen_synthetic.py |
| tickets | 150 | T000017 ambiguous; T000042 out of scope | gen_synthetic.py |
| kb_articles | 20 | KB0003 answers T000017 | gen_synthetic.py |

### customers
| Field | Type | Example | Constraints |
|---|---|---|---|
| customer_id | id | C00001 | prefix=C; width=5 |
| name | name | Priya Okafor | |
| email | email | priya.okafor1@example.com | |
| segment | enum | mid | values=enterprise|mid|small; weights=1|3|6 |
| created | date | 2025-11-02 | within_days=900 |
| active | bool | true | p_true=0.8 |

### tickets
| Field | Type | Example | Constraints |
|---|---|---|---|
| ticket_id | id | T000001 | prefix=T; width=6 |
| customer_id | ref | C00008 | entity=customers; field=customer_id |
| status | enum | open | values=open|pending|closed |
| priority | int | 2 | min=1; max=4 |
| opened | date | 2026-01-03 | within_days=90 |
| subject | text | Order shipment pending review. | words=6 |
| channel | enum | email | values=email|chat|phone-transcript; weights=5|3|2 |

### kb_articles
| Field | Type | Example | Constraints |
|---|---|---|---|
| article_id | id | KB0001 | prefix=KB; width=4 |
| title | text | Renewal invoice status update. | words=5 |
| updated | date | 2025-12-20 | within_days=180 |

## 8. UI stub
| Screen | Inputs | Outputs | States (loading/empty/error) | Mocked vs live |
|---|---|---|---|---|

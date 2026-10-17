# Technology-Signal Playbook

Goal: infer the client's platform estate, integration approach, cloud posture, and team shape from public signals, with honest confidence ratings.

## 1. Where signals live
| Signal source | What it reveals | Typical confidence | How to read it |
|---|---|---|---|
| Job postings (careers page, aggregators) | Named platforms (ERP, iPaaS, API gateway, cloud, data stack), team size (number of similar reqs), seniority mix, locations (onshore/offshore), migration language ("experience migrating from X to Y") | Med (High if 3+ postings over 6 months agree) | Required skills = current stack; "nice to have" or "experience with" = target stack. A posting for "Platform X migration lead" is a program signal |
| Engineering / tech blog, conference talks | Architecture decisions, platform choices, scale figures, team names | High for what is stated; dates matter | Quote the talk title and date |
| Vendor case studies and press releases | Confirmed vendor relationships, scope of use, go-live year | High for relationship; Med for current scope | Vendors overstate; check the date |
| Open-source repos / GitHub org | Languages, frameworks, CI tooling, API styles | Med | May be side projects |
| Public API developer portals | API gateway product (visible in URL patterns, headers, portal branding), API maturity, versioning | High for gateway product | Look at docs footer, auth flow, base URLs |
| Status pages, incident posts | Platform components, cloud provider regions, outage patterns | Med | Dates of incidents feed urgency |
| DNS / MX / TLS (only if user provides lookup output) | Email provider, CDN, hosting | Med | Do not run lookups from this skill; use provided data |
| Earnings calls / filings | Named transformation programs, cloud commitments, platform consolidations | High | Tier 1–2 |
| Partner ecosystem pages (vendor "customers" lists) | Vendor relationships | Med | Lists go stale |
| Analyst reports (if provided) | Strategy context | Med–High | Cite the report |
| LinkedIn titles of staff (public) | Team structure, platform specialists on staff | Low–Med | Titles lag reality |

## 2. Confidence rubric
| Rating | Rule |
|---|---|
| High | Stated by the company itself (filing, blog, talk, developer portal) or confirmed by two independent Tier 3–5 sources within 18 months |
| Med | One Tier 3–5 source within 18 months, or two older sources |
| Low | One source older than 18 months, or inferred from indirect evidence (e.g., a single job posting) |

Never write "they use X" at Low confidence. Write "signal suggests X (Low: single posting, 2024)".

## 3. Signal-to-hypothesis patterns
| Signal pattern | Likely situation | Our angle |
|---|---|---|
| Postings for both legacy iPaaS and a newer API gateway | Migration under way or planned; licensing-cost driver | Migration factory, TCO case (`integration-migration-assessor`) |
| Many postings for integration developers over 12 months, no architect postings | Sprawl without governance; key-person risk | Integration assessment, platform standards |
| ERP upgrade posting + "data migration" + "testing" roles | ERP program in flight; integration re-platform rides along | Integration workstream, test automation |
| "AI engineer" postings but no data-engineering postings | AI ambition ahead of data readiness | Data foundation first, use-case canvas |
| Multiple cloud providers in postings | Multi-cloud by acquisition; consolidation opportunity | Platform rationalization |
| Offshore locations appearing in postings for the first time | Building captive offshore; partner competition or opportunity to run it | Managed service / build-operate-transfer |
| Status page shows repeated incidents on one component | Operational pain with a visible date trail | Resilience, observability, modernization |
| Developer portal on a known gateway product with few APIs | Platform bought, not adopted | API program acceleration |

## 4. Recording signals
Table columns in the brief:
`Area | Signal (what you saw) | Source (URL/doc, date) | Confidence | Inference | Confirming question`

Areas to cover: ERP/core, integration/API platform, cloud and infrastructure, data and analytics, AI/ML, security/compliance, customer-facing digital, engineering practices (CI/CD, SRE), sourcing model (captive, partners named).

## 5. What not to do
- Do not scrape, log in, or access anything non-public. Public pages and user-provided material only.
- Do not infer vendor relationships from a logo on a slide at a conference.
- Do not assume a posting means a funded program; it may be backfill.
- Do not present a stack diagram as fact. Label it "inferred from public signals; to be confirmed in discovery".

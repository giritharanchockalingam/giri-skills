# Question Bank — EdTech / Higher Education

Scope: universities, online-program providers, workforce-education companies, K-12 platform vendors. Buyer personas: CIO, Provost / Chief Academic Officer, VP Enrollment, Registrar, CFO, Head of Financial Aid, VP Student Success, Head of Data.

## Typical pains (hypothesis seeds)
| Area | Pattern seen repeatedly | Usually owned by |
|---|---|---|
| Student lifecycle integration | SIS, LMS, CRM, financial aid, payments stitched with point-to-point jobs; enrollment-period failures | VP Apps / Registrar |
| Financial aid compliance | Title IV / federal and state reporting cycles long, manual, audit exposure | Head of Financial Aid / CFO |
| Enrollment funnel | Lead-to-enrolled conversion opaque across CRM, call center, admissions | VP Enrollment |
| Learner data | No single learner record; retention analytics late or untrusted | Head of Data / VP Student Success |
| Platform aging | Legacy SIS or custom portals near end of support; vendor roadmap risk | CIO |
| Seasonal load | Term start spikes, waitlist/registration outages | CIO / Infra |
| AI | Pressure to deploy advisors/tutors/bots; policy and academic-integrity concerns unresolved | Provost / CIO |
| Accessibility and privacy | WCAG, FERPA, state privacy laws; procurement blocks on vendor compliance | General Counsel / CIO |

## Questions by funnel stage
### Situation
| # | Question | Persona | Listen for |
|---|---|---|---|
| E1 | Walk me through a learner's journey from inquiry to first-term census — which systems touch them and where does a human re-key something? | VP Enrollment / Registrar | Re-keying points, system count, ownership gaps |
| E2 | Which platforms are core today (SIS, LMS, CRM, aid, payments, identity), and which are on a contract or support cliff in the next 24 months? | CIO | Named platforms, renewal dates, EOL |
| E3 | How are integrations built and maintained — a platform, scripts, vendor connectors? Who owns them? | VP Apps | Integration platform, key-person dependency |
| E4 | How many programs, modalities (campus/online/hybrid), and term structures do you run? | Provost / Registrar | Complexity drivers for any estimate |

### Pain
| # | Question | Persona | Listen for |
|---|---|---|---|
| E5 | What broke during the last term start, and what did it take to recover? | CIO / Registrar | Outage pattern, manual recovery effort |
| E6 | Where does financial-aid processing stall, and what does the audit team say about it? | Head of Financial Aid | Cycle time, findings, manual reconciliation |
| E7 | Which reports does leadership not trust, and why? | Head of Data | Data lineage, conflicting sources |
| E8 | When a student calls with a problem that spans admissions, aid, and billing, how many people touch the case? | VP Student Success | Case handoffs, CRM gaps |
| E9 | What do faculty or advisors complain about most in the tools they use daily? | Provost | Adoption friction, shadow tools |

### Impact
| # | Question | Persona | Listen for |
|---|---|---|---|
| E10 | How many enrollments or how much aid disbursement was delayed or lost in the last cycle because of system or process failure? Is that figure from a report? | VP Enrollment / CFO | A number and its source |
| E11 | How much staff time per term goes to manual reconciliation across aid, billing, and SIS? | CFO / Registrar | FTE-equivalents |
| E12 | What has a compliance finding cost you — remediation effort, fines, reputational exposure? | CFO / Counsel | Risk quantification |
| E13 | What is your retention or persistence rate, and what does one point of improvement equal in revenue? | Provost / CFO | Value lever for the business case |

### Urgency
| # | Question | Persona | Listen for |
|---|---|---|---|
| E14 | Which date matters most — a contract end, a regulatory deadline, an accreditation visit, a new program launch? | CIO / Provost | Forcing event |
| E15 | What is the board or president expecting to see this year on this topic? | CIO | Executive commitment |

### Decision and constraints
| # | Question | Persona | Listen for |
|---|---|---|---|
| E16 | Does this go through IT governance, a procurement RFP, or a sponsor's discretionary budget? | CIO / CFO | Procurement path and length |
| E17 | What vendor-compliance requirements must any partner meet — FERPA, SOC 2, HECVAT, VPAT, state data-residency? | Counsel / CISO | Hard gates |
| E18 | What is your position on AI touching student data or advising? Is there a policy, or is that part of the ask? | Provost / CIO | AI governance maturity |
| E19 | Who on your team would work with us day to day, and what is their availability during term? | VP Apps | Client capacity, calendar constraints |

## Branch table (common pivots)
| If they say | Go to |
|---|---|
| "Our SIS vendor is handling the integration." | E3 + close #4; probe vendor roadmap dependence and cost |
| "We tried an integration platform and it didn't stick." | Ask what failed: skills, licensing cost, ownership? Shapes managed-service vs build |
| "We have an AI task force." | E18; ask for its charter and what it has shipped |
| "Aid is fine, it's enrollment." | E1, E8, E10; de-emphasize E6/E12 |

## Pre-reads worth requesting
Integration inventory (even a spreadsheet), last term-start incident report, aid audit summary (redacted), current platform contract end dates, org chart for IT and enrollment.

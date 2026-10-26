---
name: solution-architecture-doc
description: Use when the user asks to produce, review, or redline a target or solution architecture for a client — context and container views, integration map, non-functional requirements, decision log, or migration waves — for a proposal, assessment, or design phase. Produces a C4-style architecture document with Mermaid diagrams, an integration inventory map, an NFR table with measurable targets, ADRs for each significant decision, and a wave plan, with every quantity sourced or marked [TO BE BASELINED — owner: ___]. Do not use for effort sizing (effort-estimator), for interface complexity scoring (integration-migration-assessor), or for internal engineering ADRs unrelated to a client deliverable.
license: MIT
metadata:
  domain: presales
  adlc_stage: architecture
  version: 0.3.0
  author: giri-skills
  agent:
    inputs:
      - {name: components, type: json, required: true, from: "components.json: {system, actors, containers:[{id,name,tech,responsibility}], external_systems, integrations:[{from,to,pattern,protocol,data,wave}], nfrs:[{category,requirement,target,measure}]} (layout: evals/fixtures/components.json)"}
      - {name: client, type: string, required: false, default: "<Client>"}
      - {name: current, type: json, required: false, from: "current-state components.json (same layout); adds the change from current state and transition ADR rows"}
    run:
      - {step: arch, kind: script, cmd: "python3 -I scripts/arch_doc.py {components} --out {out}/architecture.md --nfr {out}/nfr.csv --client {client} --svg-dir {out}/diagrams --drawio {out}/architecture.drawio --html {out}/architecture.html --adr-dir {out}/adr [--current {current}]"}
    outputs:
      - {path: "{out}/architecture.md", checks: [exists, mermaid_parses, sections:["Bottom line","System context","Container view","Integration map","Non-functional requirements","Decision log","Open items"]]}
      - {path: "{out}/architecture.html", checks: [exists, contains:"<figure>"]}
      - {path: "{out}/diagrams/context.svg", checks: [exists, contains:"<svg"]}
      - {path: "{out}/diagrams/container.svg", checks: [exists, contains:"<svg"]}
      - {path: "{out}/architecture.drawio", checks: [exists, contains:"<mxfile"]}
      - {path: "{out}/nfr.csv", checks: [exists, csv:[category,requirement,target,measure], csv_rows:target!empty]}
    modes:
      new: {case: agent-happy-path, bring: "the target components, integrations and NFRs"}
      existing: {case: agent-mode-existing, bring: "the target design plus the current-state estate"}
---

# solution-architecture-doc

## In a conversation: write the document now
- **The request carries facts** (systems, interfaces, constraints, NFRs, dates, audience): write the architecture document **in this reply**. Do not ask for a file or JSON first, and never answer with only questions. Use what is given; mark each missing fact `[TO BE BASELINED — owner: <role>]`; end with the few questions that would close those gaps.
- **The request carries no client facts at all**: ask once, in one list, for current-state facts, drivers and constraints, NFR expectations and the audience. Do not draw a current state from assumptions. You may offer a generic pattern catalogue, labelled "not client-specific".
- **Asked to invent NFR numbers or to "just pick" products**: say in one line why not (unsourced targets and undecided products become contractual and credibility risk). Show each target as `[TO BE BASELINED — owner: ___]` with its measurement method and the discovery question that would set it; show products as role placeholders with `proposed` ADRs naming the client decision owner; offer the scored options table as the way to decide.

The document, in this order (CIO depth: 6–10 pages, the bottom line stands alone; ARB depth adds component, deployment and security views):
1. **Bottom line** — the target state in one paragraph, the top 3 decisions, the waves, the biggest risk, what is still open.
2. **Drivers and constraints** — each with its source.
3. **Current state** (context + container, Mermaid) from evidence only; every box source-tagged; unknown integrations dashed and listed as gaps.
4. **Options and recommendation** — at least two options scored on weighted criteria (show the arithmetic); the choice is ADR-001.
5. **Target state** (context + container, Mermaid C4) — undecided products as placeholders.
6. **Integration map** — interfaces grouped by pattern, with protocol, data, volume/SLA (sourced or marked) and wave.
7. **NFRs** — target, measurement method, source, design response; constraints such as data residency become NFRs.
8. **Security and data**, **operability and environments**.
9. **Migration waves** — goal, scope, entry and exit criteria, rollback, aligned to the stated dates.
10. **Decision log** (ADRs with owner and status), **risks** (likelihood × impact, owner, mitigation), **open items** with owners, **sources**.

## Starting points
- **New** — the target design becomes a decision-ready architecture document: bottom line, drivers, C4 context, container and deployment diagrams, integration map, migration waves (entry, exit, rollback), NFRs, security, scored options with ADRs, risks, decision log, open items and sources.
- **Existing** — add `current` (the estate as it runs today, same layout): the document gains a change view — containers kept, added, retired or re-platformed, integrations added, retired or re-patterned — and a decision-log row for every retirement and re-platform.

## When to use
- "Produce the target architecture for <client>'s <initiative>."
- "Draw the C4 context and container views for the proposal."
- "Write the NFRs and decision log for this design."
- "Review this architecture document before it goes to the client."
- NOT for: effort (`effort-estimator`), interface scoring and TCO (`integration-migration-assessor`), proposal prose (`proposal-writer`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Current-state facts: systems, platforms, integration inventory, environments, hosting | yes | discovery synthesis / assessor output / client docs |
| Drivers and constraints: objectives, compliance regimes, vendor decisions already made, budget shape, dates | yes | discovery synthesis / RFP |
| Stated NFR expectations (volumes, latency, availability, RPO/RTO, security) or "none stated" | yes | client docs / user |
| Audience: CIO deck-level vs architecture-review-board level | yes | user |
| Existing draft (review mode) | yes in review | file |

Missing facts never stop the draft: write what is evidenced, mark the rest `[TO BE BASELINED — owner: ___]`, and ask for it at the end. Never draw a current-state diagram from assumptions.

## Procedure
Read `../../shared/quality-bar.md` and `../../shared/writing-style.md` first.

1. **Fix the audience and depth** per `references/architecture-method.md` §1. CIO-level: context view + container view + decisions + waves, 6–10 pages. ARB-level: add component views for the critical containers, full NFR table, deployment view, security view.
2. **Draw the current state first** (context + container) from evidence only. Every box carries a source tag (document, slide, interview). Unknown integrations are drawn dashed with a `?` label and listed as gaps. This diagram is the baseline the client will correct; invite correction explicitly.
3. **Decision point — architecture options.** Identify the 2–3 options that the drivers permit (e.g., strangler migration vs big-bang; single API gateway vs federated; event backbone vs point-to-point API). Score each against the weighted criteria in §3 of the method (fit to drivers, risk, cost shape, time to value, operability, lock-in). Record the chosen option as ADR-001 using `assets/adr-template.md`; the others become the "alternatives considered" section. Never present a single option as inevitable.
4. **Draw the target state** (context, container; component for critical containers at ARB depth) with the Mermaid C4 templates in `assets/mermaid-c4-templates.md`. Name every container with technology placeholders only where a product decision is still open; mark those `[TO BE BASELINED — owner: ___]`.
5. **Build the integration map**: table of interfaces (source, target, pattern, protocol, data, volume, SLA, owner, wave) from the assessor output or the inventory; group by pattern (sync API, async event, batch file, managed-file transfer). Volumes and SLAs come from sources or are marked.
6. **Write the NFRs** with `assets/nfr-checklist.md`: every applicable NFR gets a measurable target, a measurement method, a source for the target (client statement, regulation, SLA), and a design response. "High availability" is not an NFR; "99.9% monthly, measured at the gateway, excluding planned windows ≤4h/month" is.
7. **Log every significant decision** as an ADR (context, options, decision, consequences, status, owner, date). Significant = changes cost, risk, vendor lock-in, or operating model. Decisions the client must make are ADRs in `proposed` status with the client owner named.
8. **Plan migration waves** per §5 of the method: wave criteria (risk, dependency, business value, freeze windows), per-wave scope, entry/exit criteria, rollback approach, parallel-run strategy. Wave membership for interfaces comes from the assessor's wave assignment when it exists.
9. **Security, data, and operability views** at the depth the audience needs: identity and access model, data classification and residency, secrets, observability, environments and promotion path, DR.
10. **Review mode**: read the draft fully; check each section against the review rubric in `references/architecture-review-rubric.md`; produce `[KEEP] [SHARPEN] [CUT] [ADD] [TBD]` findings with rewritten content; deliver the clean version.
11. Run the self-check.

## Output
- `architecture.md` (Mermaid blocks inline, for Git and Confluence) and `architecture.html` (the same document, printable, diagrams inline; Print → Save as PDF)
- `diagrams/context.svg`, `diagrams/container.svg`, `diagrams/deployment.svg` (C4 pictures for slides) and `architecture.drawio` (every view, editable in diagrams.net / Confluence)
- `adr/ADR-nnn-<slug>.md` per decision, with the weighted option scores; `nfr.csv`
- Sections: Bottom line (target state in one paragraph + top 3 decisions) · Drivers and constraints · Current state (diagrams + gaps) · Options and recommendation (scored table) · Target state (diagrams) · Integration map · NFRs · Security and data · Operability and environments · Migration waves · Decision log (ADR index) · Risks · Open items with owners
- Appendices: `adr/ADR-nnn-<slug>.md` per decision (template `assets/adr-template.md`)

## Self-check
- [ ] Current-state boxes each carry a source; unknowns dashed and listed as gaps
- [ ] ≥2 options scored on stated criteria before the recommendation
- [ ] Every NFR has target, measurement method, source, design response
- [ ] Every significant decision has an ADR with owner and status
- [ ] Every volume, SLA, count sourced or `[TO BE BASELINED — owner: ___]`
- [ ] Waves have entry/exit criteria and rollback
- [ ] Product names appear only where decided; otherwise placeholders marked
- [ ] Diagrams render (valid Mermaid); each has a one-line caption stating what it shows
- [ ] No other-client architecture details, no author history

## References
- `references/architecture-method.md` — depth by audience, current-state evidence rules, option scoring, wave planning, views
- `references/architecture-review-rubric.md` — review criteria and scoring for existing documents
- `assets/mermaid-c4-templates.md` — Mermaid C4 context/container/component/deployment templates
- `assets/nfr-checklist.md` — NFR categories with target patterns and measurement methods
- `assets/adr-template.md` — ADR template

## How to run (automation, when commands can run)
This skill is executable. When you can run commands, put the facts into `components.json` (layout: `evals/fixtures/northwind-order-hub.json`) and run `python3 scripts/run_skill.py presales/solution-architecture-doc --input components=<file> --input client=<name> --out <dir>`; report `run.json` and hand over the deliverables it writes (below) instead of re-typing them.
When you cannot run commands, **write the document yourself** following the Procedure — never answer a request that already carries facts with only a question. Draft from what is given, mark every gap `[TO BE BASELINED — owner: ___]`, and ask for the missing facts at the end.


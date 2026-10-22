---
name: domain-modeling-runner
description: Use when the team needs a checked domain model before schema or API work — "model our domain", "draw the ER diagram for these entities", "build the glossary", "validate our entities and relationships", "what invariants does this model imply". Produces model.md (Diagram with a Mermaid erDiagram, Entities, Relationships, Invariants, Glossary, Open questions) and model.json from entities and relationships CSVs plus an optional glossary, after validating undefined entities in relationships, entities without identifiers, bad cardinalities, N:M without a join note and orphan entities; undefined glossary terms are marked for the domain expert, never invented. Runnable wrapper of the vendored domain-modeling skill. Not for writing SQL migrations or RLS (use supabase-schema-rls) or for ADR writing alone.
license: MIT
metadata:
  domain: build
  adlc_stage: requirements
  version: 0.2.0
  author: giri-skills
  fits:
    stacks: [any]
    request_kinds: [feature, migration, greenfield]
  agent:
    inputs:
      - {name: entities, type: csv, required: true, from: "entities, one row per attribute (layout: assets/entities-template.csv): entity,attribute,type,required,notes"}
      - {name: relationships, type: csv, required: true, from: "relationships (layout: assets/relationships-template.csv): from,to,cardinality (1:1|1:N|N:M),name[,notes with 'join: X' for N:M]"}
      - {name: glossary, type: csv, required: false, from: "glossary (layout: assets/glossary-template.csv): term,definition[,avoid ;-separated]"}
      - {name: title, type: string, required: false, default: "Domain model", from: "context name for the diagram title and glossary heading"}
      - {name: narrative, type: flag, required: false, flag: "--narrative", from: "true to have the LLM write the modeling review (challenged terms, edge-case scenarios, ADR candidates) from the model and the upstream method"}
      - {name: baseline, type: json, required: false, from: "model.json this skill wrote for the model as it is today; adds 'Changes vs current model' with migration impact"}
    run:
      - {step: model, kind: script, cmd: "python3 -I scripts/model.py --entities {entities} --relationships {relationships} [--glossary {glossary}] [--baseline {baseline}] --title {title} --md {out}/model.md --json {out}/model.json"}
      - {step: modeling-review, kind: llm, template: assets/modeling-review-template.md, context: ["../../../vendor/domain-modeling/SKILL.md", "../../../vendor/domain-modeling/GLOSSARY-FORMAT.md", "../../../vendor/domain-modeling/ADR-FORMAT.md", "{out}/model.md", "{out}/model.json", "references/modeling-rules.md"], out: "{out}/modeling-review.md", skip_if_missing: [narrative]}
    outputs:
      - {path: "{out}/model.md", checks: [exists, sections:["Diagram","Entities","Relationships","Glossary","Open questions"], mermaid_parses, no_unowned_tbd]}
      - {path: "{out}/model.json", checks: [exists, json, cmd:"python3 -I scripts/model.py --check {path}"]}
    modes:
      new: {case: agent-happy-path, bring: "your entities, relationships and glossary terms"}
      existing: {case: agent-mode-existing, bring: "today's model plus the entities and relationships you want"}
---

# domain-modeling-runner

Wraps `domain-modeling` from mattpocock/skills (pinned in vendor/pins.json). Upstream is a conversational discipline — challenge terms against the glossary, sharpen fuzzy language, stress-test relationships with scenarios, record hard-to-reverse decisions as ADRs. This skill makes the checkable part deterministic (structure, identifiers, cardinalities, glossary gaps, invariants) and passes the upstream instructions and its glossary/ADR formats to the optional review step by path (`../../../vendor/domain-modeling/SKILL.md`), never by copy.

## In a conversation: write the model now
- **Entities, relationships and glossary are stated in the conversation** (CSV text or plain sentences): write `model.md` **in this reply** in this order — Diagram (Mermaid `erDiagram` with a title front-matter block, PK/FK markers, cardinality aliases `1 to 0+` for 1:N, `1 to 1`, `0+ to 0+`), Entities, Relationships, Invariants (a checklist to confirm: unique identifiers, required attributes, ownership for 1:N, uniqueness for 1:1 and N:M pairs), Glossary (`**Term**:` definition, `_Avoid_:` synonyms; supplied definitions kept word for word; any entity without one gets `[TO BE BASELINED — owner: Domain expert]`), Open questions (every error and warning, owned by the domain expert). An N:M relationship is drawn through its join entity (e.g. Enrollment between Student and Course).
- **Validate before drawing**: errors E1–E6 — relationship endpoint not a defined entity, entity without identifier, cardinality not `1:1`/`1:N`/`N:M` (e.g. `many`), N:M without `join: <Entity>`, duplicate attribute, bad `required` value; warnings W1–W3 — orphan entity, term without definition, glossary term that is not an entity. Any error means the run fails: say so on line 1, leave invalid relationships out of the diagram, and list each error under Open questions. Never add an undefined entity (e.g. an Instructor that has no entity rows) to make a relationship valid.
- **Existing model plus revised files**: compare and list what is added, removed or changed (entities, attributes, `required`, type changes); every breaking change gets a migration-impact line to plan before building.
- **The request says files are attached but their contents are not in the conversation**: still write every section now from whatever the request states, with each entity, attribute, cardinality or definition not given shown as `[TO BE BASELINED — owner: ___]` naming the file it comes from (entities CSV, relationships CSV, glossary CSV, baseline `model.json`). With a review request, also lay out the modeling review per `assets/modeling-review-template.md` — Challenged terms, Edge-case scenarios, Invariants to confirm, ADR candidates — per the upstream method. Never reply with only a request for files.
- **Relationships entirely missing** (entities only, "draw the ER diagram"): ask once for the relationships (`from,to,cardinality,name[,notes]`) instead of guessing how entities relate; definitions and cardinalities are never invented.

## Starting points
- **New** — entities, relationships and glossary become a validated model: Mermaid ER diagram, invariants, glossary, open questions.
- **Existing** — add `baseline` (the `model.json` of today's model): the proposed model is validated the same way and compared with it — what is added, removed or changed — and every breaking change gets a migration-impact line to plan before building.

## When to use
- Before schema, API or event design: get entities, keys and cardinalities agreed.
- When terms drift ("account" vs "customer"): build the glossary and see which terms lack a definition.
- NOT for: SQL migrations and RLS (`supabase-schema-rls`), tenancy audits (`multi-tenant-saas-patterns`), product requirements (`product-spec-prd`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| `entities` | yes | One row per attribute: `entity,attribute,type,required,notes`. Mark the identifier with an `id` / `<entity>_id` name or `PK` in notes; `FK` in notes marks a foreign key. |
| `relationships` | yes | `from,to,cardinality,name[,notes]`; cardinality `1:1`, `1:N`, `N:M`; N:M needs `join: <Entity>` in notes. |
| `glossary` | no | `term,definition[,avoid]`. Entities without a definition get `[TO BE BASELINED — owner: Domain expert]`. |
| `title` | no | Bounded-context name (default "Domain model"). |
| `narrative` | no | `true` runs the LLM modeling review. |

## Procedure
1. **Read** the CSVs (`scripts/model.py`); missing columns or files → exit 2 naming them.
2. **Validate** (errors E1–E6): undefined relationship endpoints, entities without identifier, bad cardinality, N:M without join, duplicate attributes, bad `required` values. **Warn** (W1–W3): orphan entities (join entities count as linked), terms without definitions, glossary terms that are not entities.
3. **Render the diagram**: Mermaid `erDiagram` with a title front-matter block, PK/FK markers, cardinality aliases (`1 to 0+` for 1:N, `1 to 1`, `0+ to 0+`). Invalid relationships are left out of the diagram.
4. **Derive invariants**: unique identifiers, required attributes, ownership for 1:N, uniqueness for 1:1 and N:M pairs — as a checklist to confirm, not as facts.
5. **Glossary** in the upstream GLOSSARY format (`**Term**:` definition, `_Avoid_:` synonyms).
6. **Open questions**: every error and warning, owned by the domain expert.
7. Optional: with `narrative=true` the LLM fills `assets/modeling-review-template.md`.

## Output
- `model.md` — Diagram, Entities, Relationships, Invariants, Glossary, Open questions.
- `model.json` — entities, relationships, glossary, invariants, errors, warnings; `model.py --check` fails on errors or undefined endpoints.
- `modeling-review.md` (only with `narrative=true`).

## Self-check
- [ ] Every relationship endpoint is a defined entity; every entity has an identifier
- [ ] Every N:M names its join; every cardinality is 1:1, 1:N or N:M
- [ ] The Mermaid block parses; invalid relationships are not drawn
- [ ] No definition was invented: missing ones carry `[TO BE BASELINED — owner: Domain expert]`
- [ ] Invariants are presented as a checklist to confirm

## References
- `references/modeling-rules.md` — validation rules, Mermaid mapping, invariant derivation
- `assets/entities-template.csv`, `assets/relationships-template.csv`, `assets/glossary-template.csv` — input layouts
- `assets/modeling-review-template.md` — narrative template for the optional LLM step
- `scripts/model.py` — validator, renderer and contract check (argparse; stdlib)
- Upstream method: `vendor/domain-modeling/` (SKILL.md, GLOSSARY-FORMAT.md, ADR-FORMAT.md)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/domain-modeling-runner --input <name>=<value> … --out <dir>` (see `--explain build/domain-modeling-runner`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. Validation errors fail the run (exit 1) but both outputs are still written, so the gaps are listed under Open questions.

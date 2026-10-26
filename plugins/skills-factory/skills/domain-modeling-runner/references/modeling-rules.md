# Modeling rules — what the runner checks and renders

The vendored `domain-modeling` skill (mattpocock/skills, pinned in `vendor/pins.json`) is the method: challenge language, sharpen terms, test relationships with scenarios, keep a glossary free of implementation detail, and write ADRs only for hard-to-reverse trade-offs. Read `vendor/domain-modeling/SKILL.md` and its `GLOSSARY-FORMAT.md`; this note documents the runner's deterministic rules.

## Validation
| Code | Kind | Rule |
|---|---|---|
| E1 | error | A relationship's `from` or `to` is not an entity in entities.csv (names compared case- and punctuation-insensitively) |
| E2 | error | An entity has no identifier: no attribute named `id` / `<entity>_id`, and no notes containing `PK`, `identifier` or `primary key` |
| E3 | error | Cardinality not `1:1`, `1:N` or `N:M` |
| E4 | error | `N:M` without a join: notes must contain `join: <Name>` or name another defined entity |
| E5 | error | Duplicate attribute within one entity |
| E6 | error | `required` not one of yes/no/true/false/y/n/1/0 |
| W1 | warning | Orphan entity: not an endpoint or join of any relationship |
| W2 | warning | Entity or glossary term without a definition → `[TO BE BASELINED — owner: Domain expert]` |
| W3 | warning | Glossary term that is not an entity (attribute, state, or a missing entity?) |

Errors exit 1 but both outputs are written so the gaps are visible. Missing files or columns exit 2. Rows whose first cell starts with `#` are comments.

## Mermaid mapping
| CSV cardinality | erDiagram relationship |
|---|---|
| `1:1` | `A 1 to 1 B` |
| `1:N` | `A 1 to 0+ B` (one A, zero or more B) |
| `N:M` | `A 0+ to 0+ B` (the join entity is drawn as its own entity) |

Text aliases (`1`, `0+`, `to`) are Mermaid ER syntax and avoid the brace markers (`o{`), so the diagram has balanced brackets. A front-matter title block (`---` / `title:` / `---`) names the context. Attribute types are reduced to `[A-Za-z0-9_]` (e.g. `decimal(4,1)` → `decimal_4_1_`); comments drop quotes and brackets. If your relationship is optional on the "one" side, record that in notes; the diagram shows the mandatory form.

## Invariants
Derived, not discovered: each identifier is unique; each required attribute is set; for 1:N every child belongs to exactly one parent; for 1:1 each side has at most one partner; for N:M a pair appears at most once in the join. Present them as a checklist for the domain expert to confirm and for engineering to enforce in schema or code.

## Glossary
Format per the upstream GLOSSARY format: `**Term**:` on one line, the definition on the next, `_Avoid_:` with synonyms. Every entity appears; definitions come only from glossary.csv.

# Method notes

## What a sample can and cannot tell you
- A sample proves presence of defects, not absence. A clean sample of 1,000 rows does not certify a 50M-row table; state the sample size and how it was drawn (random, latest N, filtered) beside the verdict.
- Freshness on a sample reflects the extract, not the live source. Re-run on a fresh extract when the decision depends on latency.
- Distinct counts on a sample understate cardinality; use them to spot constants and near-constant columns, not to size dimensions.

## Where the thresholds come from
The data owner (or the use-case owner with the data owner's sign-off) sets them for the specific use case. A forecasting model and a chatbot corpus need different completeness and freshness bars; this skill encodes none, so the same script serves both.

## Relation to public frameworks (by name only)
- The dimensions follow the common data-quality vocabulary (completeness, uniqueness, timeliness, validity/conformity) used in DAMA-DMBOK and ISO/IEC 25012.
- NIST AI RMF (MAP function) expects data provenance and fitness for purpose to be documented before build; `readiness.json` is that evidence for the dimensions it covers.
- Not covered here: accuracy against a source of truth, referential integrity across tables, bias/representativeness, licensing and consent. Record those separately (e.g. `ai-governance-risk`).

## Downstream
- PII present? Run `pii-data-inventory` on the same sample before any data leaves its system.
- Building a fine-tune set? `finetune-dataset-builder` after the source is Ready.

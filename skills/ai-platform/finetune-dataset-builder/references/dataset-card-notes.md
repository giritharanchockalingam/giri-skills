# Data card notes

The card is the minimum provenance record a reviewer needs before approving a fine-tune.

| Section | Answers | Filled by |
|---|---|---|
| Source | Which file (checksum), which format, what parameters, who owns it and under what licence/consent | script; owner/licence stays `[TO BE BASELINED — owner: Data owner]` until confirmed |
| Cleaning | How many records were rejected, normalised and de-duplicated, and why | script |
| Splits | Sizes per split and cross-split leakage | script |
| Length stats | Estimated token lengths per split vs the target context window | script (estimate) |
| Known limits | What this pipeline does not check | script (fixed text) |

## Public practices this follows (by name only)
- "Datasheets for Datasets" (Gebru et al.) and "Data Statements for NLP" — provenance, composition, collection and maintenance questions.
- NIST AI RMF (MAP and MEASURE functions) — document data provenance and test/train separation.
- EU AI Act (high-risk systems) — data governance obligations cover training, validation and testing sets; the card is input to that record, not proof of compliance.

## Before training
- PII: run `pii-data-inventory` on the source and apply the policy before building.
- Quality: sample-read 20–50 examples per split; this pipeline cannot judge correctness.
- Tokenizer: re-count with the target model's tokenizer and compare with its context window.

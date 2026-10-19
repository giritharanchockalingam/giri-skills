# Sources (verified 2026-10-18)

| Topic | Source | What it supports |
|---|---|---|
| SPDX ids | SPDX License List 3.29.0 (released 2026-09-16) — https://spdx.org/licenses/ ; machine-readable list https://github.com/spdx/license-list-data (`json/licenses.json`) | Every non-LicenseRef `spdx_id` in `assets/license-catalog.csv` is a current, non-deprecated id. The list has no id for OpenRAIL, Llama or Gemma licences, so they use `LicenseRef-` ids. |
| Llama 2 | Llama 2 Community License (release 2023-07-18) — https://github.com/meta-llama/llama-models/blob/main/models/llama2/LICENSE | 700M monthly-active-users clause; no use of outputs to improve other LLMs; Notice file |
| Llama 3.1 | Llama 3.1 Community License (release 2024-07-23) — https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/LICENSE | 700M MAU clause; "Built with Llama"; derived model names begin with "Llama"; Acceptable Use Policy; Notice file |
| Llama 3.3 | Llama 3.3 Community License (release 2024-12-06) — https://github.com/meta-llama/llama-models/blob/main/models/llama3_3/LICENSE | Same terms as 3.1 for the flags used |
| Gemma (to Gemma 3) | Gemma Terms of Use (last modified 2026-04-01) — https://ai.google.dev/gemma/terms | Prohibited Use Policy flows to recipients; copy of terms; Notice file; modified-file notices |
| Gemma 4 | https://ai.google.dev/gemma/apache_2 (linked as "Gemma 4 license" from https://ai.google.dev/gemma/docs/core) | Gemma 4 is under Apache-2.0, so a bare "Gemma" licence string is ambiguous and left unknown |
| CreativeML OpenRAIL-M | https://huggingface.co/spaces/CompVis/stable-diffusion-license/raw/main/license.txt | Royalty-free grant incl. hosting; para. 5 use restrictions must be enforceable downstream; Attachment A; copy of licence to recipients |
| BigScience OpenRAIL-M | https://www.licenses.ai/blog/2022/8/26/bigscience-open-rail-m-license | Behavioural-use restrictions apply to derivatives and redistribution |
| CC BY-NC 4.0 | https://creativecommons.org/licenses/by-nc/4.0/ | NonCommercial restriction; attribution |
| CycloneDX 1.6 | JSON reference https://cyclonedx.org/docs/1.6/json/ ; schema https://raw.githubusercontent.com/CycloneDX/specification/1.6/schema/bom-1.6.schema.json | Field names used: `bomFormat`, `specVersion`, `version`, `metadata.component`, `components[].type` (enum incl. `machine-learning-model`, `data`, `library`), `bom-ref`, `name`, `version`, `licenses[]` as `{license:{id|name, acknowledgement}}` or `{expression, acknowledgement}`, `externalReferences[]` (`type: website`), `properties[]` (`name`,`value`), top-level `services[]` |

Not from a source (skill convention): the alias lists; the yes/no/conditional flag summaries (short paraphrases, not licence text); the OR/AND decision rule; treating Llama's MAU clause as `conditional` commercial restriction. Generic "OpenRAIL-M" and other licence-family names without a named text stay unknown.

## Anthropic source-available skill licence (added 2026-10-19)
- LICENSE.txt shipped with anthropics/skills `skills/docx` (identical in pdf, pptx, xlsx), read from the vendored copy pinned at commit dbd4588f9e1033efb41dad4bef2f7947c8993d44: use is governed by the Anthropic agreement; additional restrictions bar extracting or retaining copies outside the Services, reproducing, derivative works, and distribution to third parties. Source: https://github.com/anthropics/skills/blob/main/skills/docx/LICENSE.txt

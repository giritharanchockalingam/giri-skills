# Interface Inventory — Column Specification (collection template)

One row per interface / API / flow. Send to the client platform team as the collection template; most columns can be exported from the platform console or repository. Factor columns accept the listed values; blank = unknown (scored mid-band with a flag).

| # | Column | Required | Values / format | Source |
|---|---|---|---|---|
| 1 | `interface_id` | yes | Unique ID (client's or `INT-nnn`) | Platform export |
| 2 | `name` | yes | Human name | Platform export |
| 3 | `source_system` | yes | System name | Platform export |
| 4 | `target_system` | yes | System name (semicolon list if fan-out) | Platform export |
| 5 | `owner` | no | Team / person | Platform team |
| 6 | `pattern` | factor F1 | `sync` / `async` / `batch` / `orchestration` | Platform export / review |
| 7 | `transformation` | factor F2 | `none` / `mapping` / `moderate` / `heavy` | Code review |
| 8 | `target_connector` | factor F3 | `native` / `partial` / `none` | Target platform catalog |
| 9 | `endpoint_count` | factor F4 | Integer | Platform export |
| 10 | `volume_class` | factor F5 | `low` / `medium` / `high` | Metrics |
| 11 | `error_handling` | factor F6 | `default` / `custom` / `compensation` | Code review |
| 12 | `security` | factor F7 | `basic` / `oauth-pii` / `regulated` | Security review |
| 13 | `test_coverage` | factor F8 | `automated` / `manual` / `none` | Repo |
| 14 | `documentation` | factor F9 | `current` / `partial` / `none` | Repo / wiki |
| 15 | `criticality` | factor F10 | `low` / `medium` / `high` | Business owner |
| 16 | `calls_90d` | no | Integer (retirement screen) | Metrics |
| 17 | `endpoint_status` | no | `active` / `decommissioning` | Architecture |
| 18 | `freeze_tag` | no | Label for a constraint (e.g., `erp-go-live`) | PMO |
| 19 | `depends_on` | no | Semicolon list of `interface_id` that must migrate first | Architecture |
| 20 | `notes` | no | Free text | — |

Value mapping to factor scores (1 / 3 / 5): first value → 1, middle → 3, last → 5; `endpoint_count`: ≤2 → 1, 3–4 → 3, ≥5 → 5. `transformation`: none → 1, mapping → 2, moderate → 3, heavy → 5.

Minimum viable inventory for a provisional assessment: columns 1–4, 6–8. Everything else improves confidence.
